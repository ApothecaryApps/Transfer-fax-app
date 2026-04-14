import streamlit as st
import requests
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
import io
from datetime import datetime
import re

st.set_page_config(page_title="Pharmacy Transfer Fax", layout="wide")
st.title("🧾 Pharmacy Prescription Transfer Fax Generator")
st.markdown("**Search + Manual Add Fixed**")

# Your Pharmacy Info (same)
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

# ====================== SEARCH & MANUAL ADD ======================
st.header("Receiving Pharmacy")

st.subheader("Smart Search")
col_a, col_b = st.columns(2)
with col_a:
    search_name = st.text_input("Pharmacy Name", placeholder="St. John's Drug or Walgreens")
    search_city = st.text_input("City", placeholder="St. John's")
with col_b:
    search_state = st.text_input("State", placeholder="AZ", max_chars=2).upper()
    search_zip = st.text_input("ZIP", placeholder="86036", max_chars=5)

if st.button("🔍 Smart Search", type="primary"):
    with st.spinner("Searching..."):
        results = []
        seen = set()
        variants = [search_name]
        clean = re.sub(r"[.'’]", "", search_name).strip() if search_name else ""
        if clean:
            variants.extend([clean, clean.replace("ST", "SAINT"), clean.replace("SAINT", "ST"), clean + " DRUG", clean + " PHARMACY"])

        for v in variants:
            if not v.strip(): continue
            params = {"version": "2.1", "limit": 15}
            if v: params["organization_name"] = v
            if search_city: params["city"] = search_city
            if search_state: params["state"] = search_state
            if search_zip: params["postal_code"] = search_zip

            try:
                resp = requests.get("https://npiregistry.cms.hhs.gov/api/", params=params, timeout=10)
                for item in resp.json().get("results", []):
                    basic = item.get("basic", {})
                    addr = item.get("addresses", [{}])[0] if item.get("addresses") else {}
                    name = basic.get("organization_name", "")
                    city = addr.get("city", "")
                    state = addr.get("state", "")
                    postal = addr.get("postal_code", "")[:5]
                    display = f"{name} — {city}, {state} {postal}".strip(" ,")
                    key = f"{name}|{city}"
                    if name and key not in seen:
                        seen.add(key)
                        results.append({"display": display, "name": name, "idx": len(results)})
            except:
                pass

        st.session_state.search_results = results
        if results:
            st.success(f"Found {len(results)} results")
        else:
            st.warning("No results. Use manual add below.")

# Display search results
if "search_results" in st.session_state and st.session_state.search_results:
    st.subheader("Select from results")
    for res in st.session_state.search_results:
        if st.button(res["display"], key=f"sel_{res['idx']}"):
            st.session_state.selected_pharmacy = res["display"]
            st.rerun()

# ====================== MANUAL ADD (Fixed) ======================
st.subheader("➕ Add Pharmacy Manually")
manual_name = st.text_input("Pharmacy Name *", key="m_name")
manual_detail = st.text_input("Store # / Address / Notes", key="m_detail")
manual_city = st.text_input("City", key="m_city")
manual_state = st.text_input("State", key="m_state", max_chars=2)
manual_zip = st.text_input("ZIP", key="m_zip", max_chars=5)

if st.button("Save to Custom List", type="primary"):
    if manual_name.strip():
        display = f"{manual_name} - {manual_detail} {manual_city}, {manual_state} {manual_zip}".strip(" ,-")
        if "custom_pharmacies" not in st.session_state:
            st.session_state.custom_pharmacies = []
        st.session_state.custom_pharmacies.append({"name": manual_name, "display": display})
        st.success(f"✅ Saved: {manual_name}")
        st.rerun()
    else:
        st.error("Pharmacy name is required")

# Show custom list
if "custom_pharmacies" in st.session_state and st.session_state.custom_pharmacies:
    st.subheader("My Custom Pharmacies")
    for i, c in enumerate(st.session_state.custom_pharmacies):
        if st.button(c["display"], key=f"cust_{i}"):
            st.session_state.selected_pharmacy = c["display"]
            st.rerun()

# Final fax field
recv_name = st.text_input("Receiving Pharmacy on Fax", 
                         value=st.session_state.get("selected_pharmacy", ""), 
                         help="This text will appear on the fax")

# Patient & RX sections (same as before)
st.header("Patient Information")
pat_name = st.text_input("Patient Full Name", "Jane A. Smith")
pat_dob = st.text_input("Date of Birth", "01/15/1985")

st.header("Prescriptions to Transfer")
if "rx_list" not in st.session_state:
    st.session_state.rx_list = [""]

for i in range(len(st.session_state.rx_list)):
    st.session_state.rx_list[i] = st.text_input(f"RX Line {i+1}", value=st.session_state.rx_list[i], key=f"rx_{i}")

col1, col2 = st.columns(2)
with col1:
    if st.button("➕ Add RX Line"):
        st.session_state.rx_list.append("")
        st.rerun()
with col2:
    if len(st.session_state.rx_list) > 1 and st.button("🗑 Remove Last"):
        st.session_state.rx_list.pop()
        st.rerun()

# PDF Generation (same)
if st.button("Generate & Download Fax PDF", type="primary", use_container_width=True):
    # [Full PDF code - same as previous versions]
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
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y  %I:%M %p')}", normal))

    doc.build(story)
    buffer.seek(0)

    st.success("✅ PDF Generated!")
    st.download_button("⬇️ Download PDF", buffer, f"Transfer_{pat_name.replace(' ','_')}.pdf", "application/pdf", use_container_width=True)
