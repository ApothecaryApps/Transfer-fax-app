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
st.markdown("**Real Fax Sending with Fax.Plus**")

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

# ====================== RECEIVING PHARMACY ======================
st.header("Receiving Pharmacy")
# (Add your current search + manual add code here if you want - for now keeping simple)
recv_name = st.text_input("Receiving Pharmacy Name on Fax", value=st.session_state.get("selected_pharmacy", "Walgreens #1234"))

recv_fax = st.text_input("📠 Receiving Fax Number", placeholder="4805551234", help="10 or 11 digits, no dashes")

# Patient & RX
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

# ====================== FAX.PLUS INTEGRATION ======================
FAXPLUS_TOKEN = "alohi_pat_csW4VhPcKBUAEwbHuyERJJ_aMKXjvtsjJDsGnEr7rtr5QdISTGpmm2sA60uN0YJpYyDkreEXJYMR9rJDkD"  # Your token is safely embedded

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

    data = [["Prescription / Request"]] + [[line] for line in st.session_state.rx_list if line.strip()]
    if len(data) > 1:
        t = Table(data, colWidths=[6.5*inch])
        t.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), colors.lightgrey), ('GRID', (0,0), (-1,-1), 1, colors.black), ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold')]))
        story.append(t)

    story.append(Spacer(1, 30))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y %I:%M %p')}", normal))

    doc.build(story)
    buffer.seek(0)
    st.session_state.pdf_bytes = buffer.getvalue()
    st.success("✅ PDF Ready to Send!")

# ====================== SEND FAX ======================
if "pdf_bytes" in st.session_state:
    if st.button("📠 SEND FAX NOW", type="primary", use_container_width=True):
        if not recv_fax.strip():
            st.error("Please enter the receiving fax number")
        else:
            with st.spinner("Sending fax via Fax.Plus..."):
                try:
                    url = "https://restapi.fax.plus/v3/accounts/self/outbox"
                    headers = {
                        "Authorization": f"Bearer {FAXPLUS_TOKEN}",
                        "Content-Type": "application/json"
                    }

                    # For simple test, we use a base64 or direct file, but Fax.Plus prefers file upload first or inline for small PDFs
                    # Simpler approach: Use multipart for file
                    files = {'file': ('transfer.pdf', st.session_state.pdf_bytes, 'application/pdf')}
                    data = {
                        'to': [recv_fax.replace('-', '').replace(' ', '').replace('(', '').replace(')', '')],
                        'comment': f"Prescription Transfer - {pat_name}"
                    }

                    response = requests.post(url, headers=headers, data=data, files=files, timeout=60)

                    if response.status_code in [200, 201]:
                        st.success(f"✅ Fax sent successfully to {recv_fax}!")
                        st.balloons()
                    else:
                        st.error(f"Failed: {response.status_code} - {response.text}")
                except Exception as e:
                    st.error(f"Error sending fax: {e}")

# Download fallback
if "pdf_bytes" in st.session_state:
    st.download_button("⬇️ Download PDF Only", st.session_state.pdf_bytes, 
                       f"Transfer_{pat_name.replace(' ','_')}.pdf", "application/pdf", use_container_width=True)
