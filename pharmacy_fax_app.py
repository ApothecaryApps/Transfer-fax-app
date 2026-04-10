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
st.markdown("**Live Version with NPI Pharmacy Search**")

# ====================== YOUR PHARMACY ======================
st.header("Your Pharmacy Info (Requesting)")
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
    pharmacist_name = st.text_input("Supervising Pharmacist", "John Doe, PharmD")
with col4:
    tech_name = st.text_input("Technician (optional)", "")

fax_title = st.text_input("Fax Title", "Prescription Transfer Request")

# ====================== RECEIVING PHARMACY ======================
st.header("Receiving Pharmacy")

search_col1, search_col2 = st.columns([3, 1])
with search_col1:
    search_term = st.text_input("Search pharmacies", 
                               placeholder="Walgreens #1263  or  CVS Phoenix")
with search_col2:
    if st.button("🔍 Search", type="primary"):
        if search_term.strip():
            with st.spinner("Searching..."):
                try:
                    url = "https://npiregistry.cms.hhs.gov/api/"
                    params = {"version": "2.1", "organization_name": search_term, "limit": 15}
                    resp = requests.get(url, params=params, timeout=10)
                    if resp.status_code == 200:
                        results = []
                        for item in resp.json().get("results", [])[:10]:
                            basic = item.get("basic", {})
                            addr = item.get("addresses", [{}])[0] if item.get("addresses") else {}
                            name = basic.get("organization_name", "Unknown")
                            results.append(name)
                        st.session_state.search_results = results
                        st.success(f"Found {len(results)} results")
                    else:
                        st.error("Search service unavailable")
                except:
                    st.error("Search temporarily unavailable — type manually below")

# Show search results
if "search_results" in st.session_state:
    st.subheader("Search Results")
    for name in st.session_state.search_results:
        if st.button(name):
            st.session_state.selected_pharmacy = name
            st.rerun()

recv_name = st.text_input("Receiving Pharmacy Name / Store #", 
                         value=st.session_state.get("selected_pharmacy", "Walgreens #1263"))

# ====================== PATIENT ======================
st.header("Patient Information")
pat_name = st.text_input("Patient Full Name", "Jane A. Smith")
pat_dob = st.text_input("Date of Birth", "01/15/1985")

# ====================== RX LINES (FIXED) ======================
st.header("Prescriptions to Transfer")

if "rx_list" not in st.session_state:
    st.session_state.rx_list = [""]

# Display current lines
new_list = []
for i, text in enumerate(st.session_state.rx_list):
    col1, col2 = st.columns([5, 1])
    with col1:
        new_text = st.text_input(f"RX Line {i+1}", value=text, key=f"rx_input_{i}")
    with col2:
        if st.button("🗑", key=f"del_{i}"):
            new_list = [x for j, x in enumerate(st.session_state.rx_list) if j != i]
            st.session_state.rx_list = new_list
            st.rerun()
    new_list.append(new_text)

st.session_state.rx_list = new_list

if st.button("➕ Add Another RX Line"):
    st.session_state.rx_list.append("")
    st.rerun()

# ====================== GENERATE PDF ======================
if st.button("Generate & Download Fax PDF", type="primary", use_container_width=True):
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
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ]))
        story.append(t)

    story.append(Spacer(1, 30))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y  %I:%M %p')}", normal))

    doc.build(story)
    buffer.seek(0)

    st.success("✅ PDF Generated Successfully!")
    st.download_button(
        label="⬇️ Download Fax PDF",
        data=buffer,
        file_name=f"Transfer_Request_{pat_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf",
        mime="application/pdf",
        use_container_width=True
    )
