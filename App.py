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

st.set_page_config(page_title="AI PDF Semantic Extractor", layout="centered")
st.title("📄 AI-Smart PDF to Excel")

uploaded_file = st.file_uploader("Upload any PDF (scanned or structured)", type="pdf")

def upload_to_bucket(bucket_name, file_data, destination_blob_name):
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)
    blob.upload_from_file(file_data, content_type="application/pdf")
    return f"gs://{bucket_name}/{destination_blob_name}"

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
    operation.result(timeout=120)
    return True

def read_ocr_output(bucket_name, prefix):
    bucket = storage_client.bucket(bucket_name)
    blobs = list(storage_client.bucket(bucket_name).list_blobs(prefix=prefix))
    full_text = ""
    for blob in blobs:
        if blob.name.endswith(".json"):
            json_data = json.loads(blob.download_as_text())
            for resp in json_data.get("responses", []):
                full_text += resp.get("fullTextAnnotation", {}).get("text", "") + "\n"
    return full_text

def smart_extract_lines(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    structured = []
    section = None

    for i, line in enumerate(lines):
        # Detect possible section headers
        if re.match(r'^[A-Z0-9].*(\d{4})?.*$', line) and ":" not in line and not line.startswith("•") and not line.endswith("."):
            section = line
            continue

        # Detect award-like structure
        if re.match(r'^•?\s?[^:]{3,40}:\s?.{2,}', line):
            match = re.search(r'^•?\s?(.*?):\s+(.*)', line)
            if match:
                title, recipient = match.groups()
                structured.append({
                    "Section": section,
                    "Type": "Award or Role",
                    "Title": title.strip(),
                    "Name/Value": recipient.strip(),
                    "Original": line
                })
                continue

        # Detect name + org structure (2-line pattern)
        if line.startswith("•") and "," in line:
            name_title = line.lstrip("• ").strip()
            name, title = [part.strip() for part in name_title.split(",", 1)]
            org = lines[i + 1] if i + 1 < len(lines) and not lines[i + 1].startswith("•") else ""
            structured.append({
                "Section": section,
                "Type": "Leadership",
                "Name": name,
                "Title": title,
                "Organization": org.strip(),
                "Original": name_title + " / " + org
            })

        # Detect name, org on single line
        elif "," in line and re.match(r'^[A-Z][a-z]+\s[A-Z][a-z]+,', line):
            parts = line.split(",", 1)
            structured.append({
                "Section": section,
                "Type": "Name + Org",
                "Name": parts[0].strip(),
                "Organization": parts[1].strip(),
                "Original": line
            })

    return pd.DataFrame(structured) if structured else pd.DataFrame({"Extracted Text": lines})

if uploaded_file:
    uid = str(uuid.uuid4())
    blob_name = f"uploads/{uid}.pdf"
    output_prefix = f"ocr_results/{uid}/"
    output_uri = f"gs://{BUCKET_NAME}/{output_prefix}"

    st.info("🧠 Processing with semantic extraction...")
    upload_to_bucket(BUCKET_NAME, uploaded_file, blob_name)
    run_ocr(f"gs://{BUCKET_NAME}/{blob_name}", output_uri)
    time.sleep(10)

    ocr_text = read_ocr_output(BUCKET_NAME, output_prefix)
    df = smart_extract_lines(ocr_text)

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name="Smart Data")
    output.seek(0)

    st.success("✅ Done! Download your smart-extracted Excel below.")
    st.download_button(
        label="📥 Download Smart Excel",
        data=output,
        file_name="semantic_parsed.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
