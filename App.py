import streamlit as st
import pdfplumber
import pandas as pd
from io import BytesIO
from pdf2image import convert_from_bytes
from google.oauth2 import service_account
from google.cloud import vision
import json

st.set_page_config(page_title="PDF to Excel (with OCR)", layout="centered")
st.title("📄 PDF to Excel Converter with OCR")
st.write("Upload a PDF (even scanned or image-based) and download a converted Excel file.")

# Load credentials from Streamlit secrets
creds_dict = json.loads(st.secrets["GCP_SERVICE_ACCOUNT_JSON"])
credentials = service_account.Credentials.from_service_account_info(creds_dict)
vision_client = vision.ImageAnnotatorClient(credentials=credentials)

uploaded_file = st.file_uploader("Choose a PDF file", type="pdf")

def extract_text_from_image(image):
    buffered = BytesIO()
    image.save(buffered, format="JPEG")
    content = buffered.getvalue()
    image = vision.Image(content=content)
    response = vision_client.document_text_detection(image=image)
    return response.full_text_annotation.text if response.full_text_annotation.text else ""

if uploaded_file:
    output = BytesIO()
    all_texts = []
    found_tables = False

    try:
        with pdfplumber.open(uploaded_file) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                tables = page.extract_tables()
                for table_num, table in enumerate(tables, start=1):
                    if table and any(any(cell for cell in row) for row in table):
                        df = pd.DataFrame(table)
                        all_texts.append((f"Page_{page_num}_Table_{table_num}", df))
                        found_tables = True
    except Exception:
        st.warning("⚠️ Could not open PDF with pdfplumber — falling back to OCR only.")

    if not found_tables:
        st.info("🔍 No extractable tables found — using OCR to read scanned pages...")
        images = convert_from_bytes(uploaded_file.read())
        text_blocks = []
        for i, image in enumerate(images):
            ocr_text = extract_text_from_image(image)
            text_blocks.append([ocr_text])
        df = pd.DataFrame(text_blocks, columns=["Extracted Text"])
        all_texts = [("OCR_Extracted_Text", df)]

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for sheet_name, df in all_texts:
            df.to_excel(writer, sheet_name=sheet_name[:31], index=False)

    output.seek(0)
    st.success("✅ Conversion complete!")
    st.download_button(
        label="📥 Download Excel File",
        data=output,
        file_name="converted_output.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
