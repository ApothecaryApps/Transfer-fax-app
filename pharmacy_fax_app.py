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
st.markdown("**Real Fax Sending Enabled** (Documo)")

# ====================== YOUR PHARMACY ======================
st.header("Your Pharmacy Info (Requesting)")
col1, col2 = st.columns(2)
with col1:
    req_name = st.text_input("Pharmacy Name", "Western Drug")
    req_address = st.text_input("Address", "123 Main St")
    req_citystatezip = st.text_input("City, State ZIP", "Tempe, AZ 85281")
with col2:
    req_phone = st.text_input("Phone", "(480) 555-1234")
    req_fax = st.text_input("Fax", "(480) 555-5678")
    req_npi = st.text_input("NPI", "1234567890")
    req_dea = st.text_input("DEA", "AB1234567")

col3, col4 = st.columns(2)
with col3:
    pharmacist_name = st.text_input("Supervising Pharmacist", "Craig Doe, PharmD")
with col4:
    tech_name = st.text_input("Technician (optional)", "")

fax_title = st.text_input("Fax Title", "Prescription Transfer Request")

# Receiving Pharmacy (keep your existing search + manual add code here)
st.header("Receiving Pharmacy")
# ... [Paste your latest search + manual add section here] ...

recv_name = st.text_input("Receiving Pharmacy Name on Fax", 
                         value=st.session_state.get("selected_pharmacy", ""))

recv_fax = st.text_input("📠 Receiving Fax Number (required to send)", 
                        placeholder="4805551234", 
                        help="10-digit number, no dashes or parentheses")

# Patient & RX
st.header("Patient Information")
pat_name = st.text_input("Patient Full Name", "Jane A. Smith")
pat_dob = st.text_input("Date of Birth", "01/15/1985")

st.header("Prescriptions to Transfer")
if "rx_list" not in st.session_state:
    st.session_state.rx_list = [""]

for i in range(len(st.session_state.rx_list)):
    st.session_state.rx_list[i] = st.text_input(f"RX Line {i+1}", 
                                                value=st.session_state.rx_list[i], 
                                                key=f"rx_{i}")

col1, col2 = st.columns(2)
with col1:
    if st.button("➕ Add RX Line"):
        st.session_state.rx_list.append("")
        st.rerun()
with col2:
    if len(st.session_state.rx_list) > 1 and st.button("🗑 Remove Last"):
        st.session_state.rx_list.pop()
        st.rerun()

# ====================== DOCUMO API KEY ======================
documo_key = st.text_input("Documo API Key", type="password", 
                          help="Paste your secret key here. It stays private on your device.")

# ====================== GENERATE & SEND ======================
if st.button("Generate PDF", type="secondary", use_container_width=True):
    buffer = io.BytesIO()
    # (Full PDF generation code - same as before)
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

    data = [["Prescription / Request"]] + [[line] for line in st.session_state.rx_list if line.strip()]
    if len(data) > 1:
        t = Table(data, colWidths=[6.5*inch])
        t.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
                               ('GRID', (0,0), (-1,-1), 1, colors.black),
                               ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold')]))
        story.append(t)

    story.append(Spacer(1, 30))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y %I:%M %p')}", normal))

    doc.build(story)
    buffer.seek(0)
    st.session_state.pdf_bytes = buffer.getvalue()
    st.success("✅ PDF Generated!")

# Send Fax
if "pdf_bytes" in st.session_state and documo_key:
    if st.button("📠 SEND FAX NOW", type="primary", use_container_width=True):
        if not recv_fax.strip():
            st.error("Please enter receiving fax number")
        else:
            with st.spinner("Sending fax via Documo..."):
                try:
                    url = "https://api.documo.com/v1/fax/send"
                    files = {'file': ('rx_transfer.pdf', st.session_state.pdf_bytes, 'application/pdf')}
                    data = {
                        'recipientFax': recv_fax.replace('-','').replace('(','').replace(')','').replace(' ',''),
                        'recipientName': recv_name[:50],
                        'subject': fax_title,
                        'notes': f"Patient: {pat_name} | DOB: {pat_dob}"
                    }
                    headers = {'Authorization': f'Basic {documo_key}'}

                    response = requests.post(url, headers=headers, data=data, files=files, timeout=60)

                    if response.status_code in [200, 201]:
                        st.success(f"✅ Fax successfully sent to {recv_fax}!")
                        st.balloons()
                    else:
                        st.error(f"Failed to send. Status: {response.status_code} - {response.text[:200]}")
                except Exception as e:
                    st.error(f"Error: {e}")

# Always allow download
if "pdf_bytes" in st.session_state:
    st.download_button("⬇️ Download PDF (instead of sending)", 
                       st.session_state.pdf_bytes, 
                       f"Transfer_{pat_name.replace(' ','_')}.pdf", 
                       "application/pdf", 
                       use_container_width=True)
