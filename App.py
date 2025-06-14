import streamlit as st
import pandas as pd
import pdfplumber
import re
import io
from google.oauth2 import service_account
from google.cloud import vision
import json
from pdf2image import convert_from_bytes
import pytesseract

# Authenticate with Google Vision API
creds_dict = json.loads(st.secrets["GCP_SERVICE_ACCOUNT_JSON"])
credentials = service_account.Credentials.from_service_account_info(creds_dict)
client = vision.ImageAnnotatorClient(credentials=credentials)

st.set_page_config(page_title="PDF/Text to Excel Converter", layout="centered")
st.title("📄 Smart PDF & Text to Excel Converter")

uploaded_file = st.file_uploader("Upload a PDF", type=["pdf"])
pasted_text = st.text_area("Or paste your text list here", height=200)

def extract_text_from_image(pdf_file):
    images = convert_from_bytes(pdf_file.read())
    extracted_text = ""
    for img in images:
        text = pytesseract.image_to_string(img)
        extracted_text += text + "\n"
    return extracted_text

def detect_table(pdf_file):
    try:
        with pdfplumber.open(io.BytesIO(pdf_file.read())) as pdf:
            for page in pdf.pages:
                if page.extract_table():
                    return True
    except:
        pass
    return False

def parse_award_style_text(text):
    rows = []
    section = None
    lines = text.strip().splitlines()

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Section headers like: Community Awards:
        if re.match(r".+:\s*$", line):
            section = line[:-1]
        elif "•" in line:
            current = line.replace("•", "").strip()
            next_line = lines[lines.index(line)+1].strip() if lines.index(line)+1 < len(lines) else ""
            if "," in current:
                name, title = map(str.strip, current.split(",", 1))
                org = next_line if next_line and next_line != line else ""
                rows.append([section, title, name, org])
        elif ":" in line and not line.endswith(":"):
            title, name = map(str.strip, line.split(":", 1))
            rows.append([section, title, name, ""])
    return pd.DataFrame(rows, columns=["Section", "Title", "Recipient", "Organization"])

def parse_plain_text(text):
    rows = []
    for line in text.strip().splitlines():
        if "•" in line and "," in line:
            try:
                part = line.replace("•", "").strip()
                name, title = map(str.strip, part.split(",", 1))
                rows.append([name, title])
            except:
                rows.append([line.strip(), ""])
        elif ":" in line:
            try:
                title, name = map(str.strip, line.split(":", 1))
                rows.append([name, title])
            except:
                rows.append([line.strip(), ""])
        else:
            rows.append([line.strip(), ""])
    return pd.DataFrame(rows, columns=["Name/Line", "Title/Notes"])

def parse_table_pdf(file):
    file.seek(0)
    with pdfplumber.open(io.BytesIO(file.read())) as pdf:
        dfs = [pd.DataFrame(page.extract_table()[1:], columns=page.extract_table()[0]) for page in pdf.pages if page.extract_table()]
        return pd.concat(dfs) if dfs else pd.DataFrame()

if uploaded_file:
    st.info("Processing uploaded PDF...")
    if detect_table(uploaded_file):
        uploaded_file.seek(0)
        df = parse_table_pdf(uploaded_file)
    else:
        uploaded_file.seek(0)
        text = extract_text_from_image(uploaded_file)
        df = parse_award_style_text(text) if ":" in text or "•" in text else parse_plain_text(text)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    st.success("✅ Done! Download your Excel file below.")
    st.download_button("⬇️ Download Excel", output.getvalue(), file_name="converted_output.xlsx")

elif pasted_text:
    st.info("Processing pasted text...")
    df = parse_award_style_text(pasted_text) if ":" in pasted_text or "•" in pasted_text else parse_plain_text(pasted_text)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    st.success("✅ Done! Download your Excel file below.")
    st.download_button("⬇️ Download Excel", output.getvalue(), file_name="converted_text_output.xlsx")
