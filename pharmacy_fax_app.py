import streamlit as st
import requests
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
import io
from datetime import datetime

st.set_page_config(page_title="Pharmacy Transfer Fax", layout="wide")
st.title("🧾 Pharmacy Prescription Transfer Fax Generator")
st.markdown("**Fax.Plus Fixed - Full PDF Restored**")

FAXPLUS_TOKEN = "alohi_pat_csW4VhPcKBUAEwbHuyERJJ_aMKXjvtsjJDsGnEr7rtr5QdISTGpmm2sA60uN0YJpYyDkreEXJYMR9rJDkD"

# ====================== FORM FIELDS ======================
st.header("Your Pharmacy Info (Requesting)")
col1, col2 = st.columns(2)
with col1:
    req_name = st.text_input("Pharmacy Name", "Western Drug")
    req_address = st.text_input("Address", "106 East Main Street")
    req_citystatezip = st.text_input("City, State ZIP", "Springerville, AZ 85938")
with col2:
    req_phone = st.text_input("Phone", "(928) 333-4321")
    req_fax = st.text_input("Fax", "(928) 333-4328")
    req_npi = st.text_input("NPI", "")
    req_dea = st.text_input("DEA", "")

pharmacist_name = st.text_input("Supervising Pharmacist", "Craig Mathews, PharmD")
tech_name = st.text_input("Technician", "Dantae Stires")
fax_title = st.text_input("Fax Title", "Prescription Transfer Request")

st.header("Receiving Pharmacy")
recv_name = st.text_input("Receiving Pharmacy Name", "Walgreens #1234")
recv_fax_number = st.text_input("Receiving Fax Number", placeholder="4805551234")

st.header("Patient Information")
pat_name = st.text_input("Patient Full Name", "Jane A. Smith")
pat_dob = st.text_input("Date of Birth", "01/15/1985")

st.header("Prescriptions to Transfer")
if "rx_list" not in st.session_state:
    st.session_state.rx_list = [""]

for i in range(len(st.session_state.rx_list)):
    st.session_state.rx_list[i] = st.text_input(f"RX Line {i+1}", value=st.session_state.rx_list[i], key=f"rx_{i}")

if st.button("➕ Add RX Line"):
    st.session_state.rx_list.append("")
    st.rerun()
if len(st.session_state.rx_list) > 1 and st.button("🗑 Remove Last"):
    st.session_state.rx_list.pop()
    st.rerun()

# ====================== GENERATE PDF ======================
if st.button("Generate PDF", type="secondary", use_container_width=True):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=50)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=16, alignment=1, spaceAfter=20)
    normal = styles['Normal']
    bold = ParagraphStyle('Bold', parent=normal, fontName="Helvetica-Bold", fontSize=11)

    story = []
    story.append(Paragraph(f"<b>{fax_title}</b>", title_style))
    story.append(Spacer(1, 12))

    header = f"""
    <b>{req_name}</b><br/>
    {req_address}<br/>
    {req_citystatezip}<br/>
    Phone: {req_phone} Fax: {req_fax}<br/>
    NPI: {req_npi} DEA: {req_dea}<br/>
    Requesting: {pharmacist_name}{" / Tech: " + tech_name if tech_name else ""}
    """
    story.append(Paragraph(header, normal))
    story.append(Spacer(1, 20))

    story.append(Paragraph(f"<b>Transfers requested from:</b> {recv_name}", bold))
    story.append(Spacer(1, 15))
    story.append(Paragraph(f"<b>Patient:</b> {pat_name}  DOB: {pat_dob}", bold))
    story.append(Spacer(1, 15))

    data = [["Prescription / Request"]]
    for line in st.session_state.rx_list:
        if line.strip():
            data.append([line.strip()])

    if len(data) > 1:
        t = Table(data, colWidths=[6.5*inch])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
            ('GRID', (0,0), (-1,-1), 1, colors.black),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ]))
        story.append(t)

    story.append(Spacer(1, 30))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y %I:%M %p')}", normal))

    doc.build(story)
    buffer.seek(0)
    st.session_state.pdf_bytes = buffer.getvalue()
    st.success("✅ PDF Generated!")

# ====================== SEND FAX (Two-Step) ======================
if "pdf_bytes" in st.session_state:
    if st.button("📠 SEND FAX NOW", type="primary", use_container_width=True):
        if not recv_fax_number.strip():
            st.error("Please enter receiving fax number")
        else:
            with st.spinner("Sending via Fax.Plus..."):
                try:
                    headers = {"Authorization": f"Bearer {FAXPLUS_TOKEN}"}

                    # Step 1: Upload file
                    upload_url = "https://restapi.fax.plus/v3/accounts/self/files"
                    files = {'file': ('transfer.pdf', st.session_state.pdf_bytes, 'application/pdf')}
                    upload_resp = requests.post(upload_url, headers=headers, files=files, timeout=30)

                    if upload_resp
