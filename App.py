import streamlit as st
import json
import pandas as pd
from io import BytesIO
from google.cloud import vision_v1
from google.oauth2 import service_account
from google.cloud import storage
import time
import uuid

# --- CONFIG ---
BUCKET_NAME = "pdf2excel-app-bucket"

# --- AUTH ---
creds_dict = json.loads(st.secrets["GCP_SERVICE_ACCOUNT_JSON"])
credentials = service_account.Credentials.from_service_account_info(creds_dict)

vision_client = vision_v1.ImageAnnotatorClient(credentials=credentials)
storage_client = storage.Client(credentials=credentials)

# --- UI ---
st.set_page_config(page_title="PDF to Excel OCR", layout="centered")
st.title("📄 PDF to Excel (with Google OCR)")
uploaded_file = st.file_uploader("Upload a scanned PDF", type="pdf")

# --- Function: Upload to GCS ---
def upload_to_bucket(bucket_name, file_data, destination_blob_name):
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)
    blob.upload_from_file(file_data, content_type="application/pdf")
    return f"gs://{bucket_name}/{destination_blob_name}"

# --- Function: OCR request ---
def run_ocr(pdf_gcs_uri, output_uri):
    mime_type = "application/pdf"
    feature = vision_v1.Feature(type_=vision_v1.Feature.Type.DOCUMENT_TEXT_DETECTION)
    gcs_source = vision_v1.GcsSource(uri=pdf_gcs_uri)
    input_config = vision_v1.InputConfig(gcs_source=gcs_source, mime_type=mime_type)
    gcs_destination = vision_v1.GcsDestination(uri=output_uri)
    output_config = vision_v1.OutputConfig(gcs_destination=gcs_destination, batch_size=1)

    async_request = vision_v1.AsyncAnnotateFileRequest(
        features=[feature],
        input_config=input_config,
        output_config=output_config,
    )

    operation = vision_client.async_batch_annotate_files(requests=[async_request])
    st.info("🕒 OCR processing… This may take 10–20 seconds.")
    operation.result(timeout=120)
    st.success("✅ OCR completed.")
    return True

# --- Function: Read OCR Results ---
def read_ocr_output(bucket_name, prefix):
    bucket = storage_client.bucket(bucket_name)
    blobs = list(bucket.list_blobs(prefix=prefix))
    text_output = []

    for blob in blobs:
        if blob.name.endswith('.json'):
            json_data = json.loads(blob.download_as_text())
            responses = json_data.get("responses", [])
            for resp in responses:
                full_text = resp.get("fullTextAnnotation", {}).get("text", "")
                if full_text.strip():
                    text_output.append(full_text.strip())

    return text_output

# --- Run OCR Pipeline ---
if uploaded_file:
    uid = str(uuid.uuid4())
    blob_name = f"uploads/{uid}.pdf"
    output_prefix = f"ocr_results/{uid}/"
    output_uri = f"gs://{BUCKET_NAME}/{output_prefix}"

    # Upload PDF to GCS
    upload_to_bucket(BUCKET_NAME, uploaded_file, blob_name)

    # Submit OCR request
    run_ocr(f"gs://{BUCKET_NAME}/{blob_name}", output_uri)

    # Wait for files to finalize in GCS
    time.sleep(10)

    # Read OCR results
    extracted_pages = read_ocr_output(BUCKET_NAME, output_prefix)

    if extracted_pages:
        df = pd.DataFrame({"Extracted Text": extracted_pages})
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name="Extracted Text")
        output.seek(0)

        st.download_button(
            label="📥 Download Excel File",
            data=output,
            file_name="ocr_output.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.warning("⚠️ No text was extracted from the file.")
