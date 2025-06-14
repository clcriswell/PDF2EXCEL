import streamlit as st
import pdfplumber
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="PDF to Excel Converter", layout="centered")

st.title("📄 PDF to Excel Converter")
st.write("Upload a PDF with tables. We'll convert it to an Excel file you can download.")

uploaded_file = st.file_uploader("Choose a PDF file", type="pdf")

if uploaded_file:
    output = BytesIO()
    with pdfplumber.open(uploaded_file) as pdf:
        all_tables = []
        for page_num, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables()
            for table_num, table in enumerate(tables, start=1):
                df = pd.DataFrame(table)
                all_tables.append((f"Page_{page_num}_Table_{table_num}", df))

        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            for sheet_name, df in all_tables:
                df.to_excel(writer, sheet_name=sheet_name[:31], index=False)

        output.seek(0)

    st.success("✅ Conversion complete!")
    st.download_button(
        label="📥 Download Excel File",
        data=output,
        file_name="converted.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
