import streamlit as st
import pandas as pd
import tempfile
import os
from google.oauth2 import service_account
from google.cloud import vision
from PyPDF2 import PdfReader

# ---- Google Cloud Vision Setup ----
creds_dict = json.loads(st.secrets["GCP_SERVICE_ACCOUNT_JSON"])
credentials = service_account.Credentials.from_service_account_info(creds_dict)
client = vision.ImageAnnotatorClient(credentials=credentials)

# ---- Smart Line Classifier ----
def classify_line(line, next_line=""):
    line = line.strip()
    result = {
        "Section": "",
        "Type": "Unclassified",
        "Confidence": "Low",
        "Name": "",
        "Title": "",
        "Organization": "",
        "Original": line
    }

    if line.isupper() or (line.istitle() and ":" not in line and not line.startswith("•") and len(line.split()) > 2):
        result["Type"] = "Section Header"
        result["Confidence"] = "High"
        return result

    if ":" in line and not line.startswith("•"):
        parts = line.split(":", 1)
        if len(parts) == 2 and len(parts[1].strip()) > 1:
            result["Type"] = "Award Recipient"
            result["Confidence"] = "High"
            result["Title"] = parts[0].strip()
            result["Name"] = parts[1].strip()
            return result

    if line.startswith("•") and "," in line:
        name_title = line.lstrip("• ").strip()
        name, title = [part.strip() for part in name_title.split(",", 1)]
        result["Name"] = name
        result["Title"] = title
        if next_line and not next_line.startswith("•") and len(next_line.split()) > 1:
            result["Organization"] = next_line.strip()
            result["Type"] = "Board Member"
            result["Confidence"] = "High"
        else:
            result["Type"] = "Leadership Role"
            result["Confidence"] = "Medium"
        return result

    if "," in line and len(line.split()) <= 8:
        parts = line.split(",", 1)
        if len(parts) == 2:
            result["Name"] = parts[0].strip()
            result["Organization"] = parts[1].strip()
            result["Type"] = "Name + Organization"
            result["Confidence"] = "Medium"
            return result

    if "@" in line or "email:" in line.lower():
        result["Type"] = "Contact Info"
        result["Confidence"] = "High"
        return result

    if any(word in line.lower() for word in ["address", "street", "city", "zip"]):
        result["Type"] = "Address Block"
        result["Confidence"] = "Medium"
        return result

    if len(line.split()) > 10:
        result["Type"] = "Narrative Message"
        result["Confidence"] = "Medium"

    return result

# ---- OCR Function ----
def extract_text_from_pdf(uploaded_file):
    temp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    temp_pdf.write(uploaded_file.read())
    temp_pdf.close()

    reader = PdfReader(temp_pdf.name)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"

    os.unlink(temp_pdf.name)
    return text

# ---- Streamlit UI ----
st.title("🧠 Smart PDF-to-Excel Converter")

uploaded_file = st.file_uploader("Upload a PDF", type=["pdf"])

if uploaded_file:
    st.info("🔍 Extracting and analyzing text...")

    raw_text = extract_text_from_pdf(uploaded_file)
    lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
    structured = []

    for i, line in enumerate(lines):
        next_line = lines[i + 1] if i + 1 < len(lines) else ""
        structured.append(classify_line(line, next_line))

    df = pd.DataFrame(structured)

    st.success("✅ Conversion complete!")
    st.dataframe(df)

    st.download_button(
        label="📥 Download Excel File",
        data=df.to_excel(index=False, engine="openpyxl"),
        file_name="converted_output.xlsx"
    )
