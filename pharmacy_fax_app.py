import streamlit as st
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
import io
from datetime import datetime

st.set_page_config(page_title="Pharmacy Transfer Fax Generator", layout="centered")
st.title("🧾 Pharmacy Prescription Transfer Fax Generator")

st.markdown("**MVP Prototype** — Generates professional 1-page fax")

# ====================== REQUESTING PHARMACY ======================
st.header("Requesting Pharmacy (Your Info)")

col1, col2 = st.columns(2)
with col1:
    req_name = st.text_input("Pharmacy Name", "Example Pharmacy")
    req_address = st.text_input("Address", "123 Main St")
    req_citystatezip = st.text_input("City, State ZIP", "Tempe, AZ 85281")
with col2:
    req_phone = st.text_input("Phone", "(480) 555-1234")
    req_fax = st.text_input("Fax", "(480) 555-5678")
    req_npi = st.text_input("NPI", "1234567890")
    req_dea = st.text_input("DEA", "AB1234567")

col3, col4 = st.columns(2)
with col3:
    pharmacist_name = st.text_input("Supervising Pharmacist Name", "John Doe, PharmD")
with col4:
    tech_name = st.text_input("Technician Name (if applicable)", "Jane Smith, CPhT")

fax_title = st.text_input("Fax Title", "Prescription Transfer Request")

# ====================== RECEIVING PHARMACY ======================
st.header("Receiving Pharmacy")
recv_name = st.text_input("Receiving Pharmacy Name / Store #", "Walgreens #1263")

# ====================== PATIENT & RX ======================
st.header("Patient Information")
pat_name = st.text_input("Patient Full Name", "Jane A. Smith")
pat_dob = st.text_input("Date of Birth", "01/15/1985")

st.header("Prescriptions to Transfer")
if "rx_list" not in st.session_state:
    st.session_state.rx_list = [""]

def add_rx():
    st.session_state.rx_list.append("")

def remove_rx(idx):
    if len(st.session_state.rx_list) > 1:
        st.session_state.rx_list.pop(idx)

for i, rx in enumerate(st.session_state.rx_list):
    col1, col2 = st.columns([4, 1])
    with col1:
        st.session_state.rx_list[i] = st.text_input(f"RX Line {i+1}", rx, key=f"rx_{i}")
    with col2:
        if st.button("Remove", key=f"rem_{i}"):
            remove_rx(i)
            st.rerun()

if st.button("➕ Add Another RX Line"):
    add_rx()
    st.rerun()

# ====================== GENERATE PDF ======================
if st.button("Generate & Download Fax PDF", type="primary"):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=16, spaceAfter=12, alignment=1)
    header_style = ParagraphStyle('Header', parent=styles['Normal'], fontSize=11, spaceAfter=6)
    bold_style = ParagraphStyle('Bold', parent=styles['Normal'], fontSize=11, textColor=colors.black, fontName="Helvetica-Bold")
    
    story = []

    # Title
    story.append(Paragraph(f"<b>{fax_title}</b>", title_style))
    story.append(Spacer(1, 12))

    # Requesting Pharmacy Header
    header_text = f"""
    <b>{req_name}</b><br/>
    {req_address}<br/>
    {req_citystatezip}<br/>
    Phone: {req_phone} | Fax: {req_fax}<br/>
    NPI: {req_npi} | DEA: {req_dea}<br/>
    Requesting: {pharmacist_name} {f' / Tech: {tech_name}' if tech_name else ''}
    """
    story.append(Paragraph(header_text, header_style))
    story.append(Spacer(1, 18))

    # Receiving
    story.append(Paragraph(f"<b>Transfers requested from:</b> {recv_name}", bold_style))
    story.append(Spacer(1, 18))

    # Patient
    story.append(Paragraph(f"<b>Patient:</b> {pat_name} &nbsp;&nbsp;&nbsp; DOB: {pat_dob}", bold_style))
    story.append(Spacer(1, 12))

    # Rx Table
    data = [["RX# / Drug Info"]]  # Header
    for rx in st.session_state.rx_list:
        if rx.strip():
            data.append([rx.strip()])

    if len(data) > 1:
        t = Table(data, colWidths=[6*inch])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
            ('TEXTCOLOR', (0,0), (-1,0), colors.black),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 11),
            ('BOTTOMPADDING', (0,0), (-1,0), 8),
            ('BACKGROUND', (0,1), (-1,-1), colors.white),
            ('GRID', (0,0), (-1,-1), 1, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ]))
        story.append(t)
    else:
        story.append(Paragraph("No prescriptions listed.", styles['Normal']))

    story.append(Spacer(1, 24))
    story.append(Paragraph(f"Generated on: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", styles['Normal']))

    doc.build(story)
    buffer.seek(0)

    st.success("✅ PDF Generated Successfully!")
    st.download_button(
        label="⬇️ Download Fax PDF",
        data=buffer,
        file_name=f"Rx_Transfer_Request_{pat_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf",
        mime="application/pdf"
  )
