import streamlit as st
import json
import pandas as pd
from io import BytesIO
from google.cloud import vision_v1
from google.oauth2 import service_account
from google.cloud import storage
import time
import uuid
import re

# --- CONFIG ---
BUCKET_NAME = "pdf2excel-app-bucket"

# --- AUTH ---
creds_dict = json.loads(st.secrets["GCP_SERVICE_ACCOUNT_JSON"])
credentials = service_account.Credentials.from_service_account_info(creds_dict)
vision_client = vision_v1.ImageAnnotatorClient(credentials=credentials)
storage_client = storage.Client(credentials=credentials)

st.set_page_config(page_title="PDF to Excel OCR", layout="centered")
st.title("📄 Smart PDF to Excel Converter")
uploaded_file = st.file_uploader("Upload a scanned PDF (awards, rosters, etc.)", type="pdf")

# --- Upload to Bucket ---
def upload_to_bucket(bucket_name, file_data, destination_blob_name):
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)
    blob.upload_from_file(file_data, content_type="application/pdf")
    return f"gs://{bucket_name}/{destination_blob_name}"

# --- OCR Processing ---
def run_ocr(pdf_gcs_uri, output_uri):
    feature = vision_v1.Feature(type_=vision_v1.Feature.Type.DOCUMENT_TEXT_DETECTION)
    gcs_source = vision_v1.GcsSource(uri=pdf_gcs_uri)
    input_config = vision_v1.InputConfig(gcs_source=gcs_source, mime_type="application/pdf")
    gcs_destination = vision_v1.GcsDestination(uri=output_uri)
    output_config = vision_v1.OutputConfig(gcs_destination=gcs_destination, batch_size=1)

    request = vision_v1.AsyncAnnotateFileRequest(
        features=[feature],
        input_config=input_config,
        output_config=output_config,
    )
    operation = vision_client.async_batch_annotate_files(requests=[request])
    st.info("🕒 Processing PDF with OCR… Please wait.")
    operation.result(timeout=120)
    st.success("✅ OCR completed.")
    return True

# --- Read OCR Output JSON ---
def read_ocr_output(bucket_name, prefix):
    bucket = storage_client.bucket(bucket_name)
    blobs = list(bucket.list_blobs(prefix=prefix))
    full_text = ""
    for blob in blobs:
        if blob.name.endswith(".json"):
            json_data = json.loads(blob.download_as_text())
            for resp in json_data.get("responses", []):
                full_text += resp.get("fullTextAnnotation", {}).get("text", "") + "\n"
    return full_text

# --- Smart Parser ---
def parse_award_sections(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    data = []
    current_section = ""
    for i, line in enumerate(lines):
        # Section headers (bolded lines with no content after ":")
        if line.endswith(":") and (i + 1 < len(lines)) and (":" not in lines[i + 1]):
            current_section = line[:-1].strip()
        elif ":" in line:
            parts = line.split(":", 1)
            title = parts[0].strip()
            value = parts[1].strip()
            data.append({
                "Section": current_section,
                "Title": title,
                "Name": value
            })
        elif "," in line:
            # Likely name + organization (e.g., Leadership grads)
            data.append({
                "Section": current_section,
                "Title": "-",
                "Name": line
            })
    return pd.DataFrame(data)

# --- MAIN FLOW ---
if uploaded_file:
    uid = str(uuid.uuid4())
    blob_name = f"uploads/{uid}.pdf"
    output_prefix = f"ocr_results/{uid}/"
    output_uri = f"gs://{BUCKET_NAME}/{output_prefix}"

    upload_to_bucket(BUCKET_NAME, uploaded_file, blob_name)
    run_ocr(f"gs://{BUCKET_NAME}/{blob_name}", output_uri)
    time.sleep(10)

    ocr_text = read_ocr_output(BUCKET_NAME, output_prefix)
    parsed_df = parse_award_sections(ocr_text)

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        parsed_df.to_excel(writer, sheet_name="Structured Data", index=False)
    output.seek(0)

    st.download_button(
        label="📥 Download Excel File",
        data=output,
        file_name="parsed_awards.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
