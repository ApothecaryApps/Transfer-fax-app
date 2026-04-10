import streamlit as st
import requests
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
import io
from datetime import datetime

st.set_page_config(page_title="Pharmacy Transfer Fax", layout="centered")
st.title("🧾 Pharmacy Prescription Transfer Fax Generator")

st.markdown("**Live Version with NPI Pharmacy Search**")

# ====================== REQUESTING PHARMACY ======================
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
    tech_name = st.text_input("Technician (optional)", "Jane Smith, CPhT")

fax_title = st.text_input("Fax Title", "Prescription Transfer Request")

# ====================== RECEIVING PHARMACY SEARCH ======================
st.header("Receiving Pharmacy (Search NPI Registry)")

search_col1, search_col2 = st.columns([3, 1])
with search_col1:
    search_term = st.text_input("Search by name, store#, city, zip, etc.", placeholder="Walgreens #1263 or CVS Phoenix")
with search_col2:
    if st.button("🔍 Search"):
        if search_term.strip():
            with st.spinner("Searching NPI Registry..."):
                try:
                    url = "https://npiregistry.cms.hhs.gov/api/"
                    params = {
                        "version": "2.1",
                        "organization_name": search_term,
                        "limit": 20,
                        "taxonomy_description": "Pharmacy"  # Helps filter pharmacies
                    }
                    response = requests.get(url, params=params, timeout=10)
                    data = response.json()
                    
                    if "results" in data and data["results"]:
                        results = []
                        for item in data["results"]:
                            basic = item.get("basic", {})
                            addr = item.get("addresses", [{}])[0] if item.get("addresses") else {}
                            tax = item.get("taxonomies", [{}])[0] if item.get("taxonomies") else {}
                            
                            name = basic.get("organization_name", "N/A")
                            npi = item.get("number", "N/A")
                            city = addr.get("city", "")
                            state = addr.get("state", "")
                            postal = addr.get("postal_code", "")
                            phone = addr.get("telephone_number", "N/A")
                            
                            display = f"{name} | {city}, {state} {postal} | NPI: {npi}"
                            results.append({"display": display, "name": name, "npi": npi, "phone": phone})
                        
                        st.session_state.search_results = results
                    else:
                        st.warning("No results found. Try a different search term.")
                except Exception as e:
                    st.error(f"Search failed: {e}")

# Show results
if "search_results" in st.session_state and st.session_state.search_results:
    st.subheader("Search Results")
    for res in st.session_state.search_results:
        if st.button(res["display"], key=res["npi"]):
            st.session_state.selected_pharmacy = res["name"]
            st.success(f"Selected: {res['name']}")
            st.rerun()

# Manual override / selected
recv_name = st.text_input("Receiving Pharmacy Name / Store # (auto-filled or edit)", 
                         value=st.session_state.get("selected_pharmacy", "Walgreens #1263"))

# ====================== PATIENT & RX (unchanged) ======================
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

# ====================== GENERATE PDF (same as before) ======================
if st.button("Generate & Download Fax PDF", type="primary"):
    # ... (same PDF generation code as previous version - copy from earlier if needed)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=16, spaceAfter=12, alignment=1)
    header_style = ParagraphStyle('Header', parent=styles['Normal'], fontSize=11, spaceAfter=6)
    bold_style = ParagraphStyle('Bold', parent=styles['Normal'], fontSize=11, textColor=colors.black, fontName="Helvetica-Bold")
    
    story = []
    story.append(Paragraph(f"<b>{fax_title}</b>", title_style))
    story.append(Spacer(1, 12))

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

    story.append(Paragraph(f"<b>Transfers requested from:</b> {recv_name}", bold_style))
    story.append(Spacer(1, 18))

    story.append(Paragraph(f"<b>Patient:</b> {pat_name} &nbsp;&nbsp;&nbsp; DOB: {pat_dob}", bold_style))
    story.append(Spacer(1, 12))

    data = [["RX# / Drug Info"]]
    for rx in st.session_state.rx_list:
        if rx.strip():
            data.append([rx.strip()])

    if len(data) > 1:
        t = Table(data, colWidths=[6*inch])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('GRID', (0,0), (-1,-1), 1, colors.black),
        ]))
        story.append(t)

    story.append(Spacer(1, 24))
    story.append(Paragraph(f"Generated on: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", styles['Normal']))

    doc.build(story)
    buffer.seek(0)

    st.success("✅ PDF Generated!")
    st.download_button(
        label="⬇️ Download Fax PDF",
        data=buffer,
        file_name=f"Rx_Transfer_{pat_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf",
        mime="application/pdf"
    )
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
