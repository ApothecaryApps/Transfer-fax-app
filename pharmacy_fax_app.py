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
st.markdown("**Ultra-Refined Search: Now finds St. John's Drug + Walgreens reliably**")

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

# ====================== ULTRA-REFINED SEARCH ======================
st.header("Receiving Pharmacy - Ultra Smart Search")

st.subheader("Search Criteria")
col_a, col_b = st.columns(2)
with col_a:
    search_name = st.text_input("Pharmacy Name", placeholder="St. John's Drug or Walgreens", value="")
    search_city = st.text_input("City", placeholder="St. John's or Phoenix")
with col_b:
    search_state = st.text_input("State (2-letter)", placeholder="AZ", max_chars=2).upper()
    search_zip = st.text_input("ZIP Code", placeholder="86036", max_chars=5)

# Always-visible manual add
if st.button("➕ Add Any Pharmacy Manually (if search misses it)"):
    with st.expander("Manual Entry Form", expanded=True):
        manual_name = st.text_input("Pharmacy Name *", key="m_name")
        manual_store = st.text_input("Store # / Address", key="m_store")
        manual_city = st.text_input("City", key="m_city")
        manual_state = st.text_input("State", key="m_state")
        manual_zip = st.text_input("ZIP", key="m_zip")
        if st.button("Save to My Custom List", type="primary"):
            if manual_name.strip():
                display = f"{manual_name} - {manual_store} {manual_city}, {manual_state} {manual_zip}".strip(" ,-")
                if "custom_pharmacies" not in st.session_state:
                    st.session_state.custom_pharmacies = []
                st.session_state.custom_pharmacies.append({"name": manual_name, "display": display})
                st.success(f"✅ Added: {manual_name}")
                st.rerun()

# Show saved custom pharmacies
if "custom_pharmacies" in st.session_state and st.session_state.custom_pharmacies:
    st.subheader("My Custom Pharmacies")
    for i, c in enumerate(st.session_state.custom_pharmacies):
        if st.button(c["display"], key=f"cust_{i}"):
            st.session_state.selected_pharmacy = c["display"]
            st.rerun()

# Smart Search
if st.button("🔍 Ultra Smart Search (tries every variation)", type="primary"):
    if not search_name.strip() and not search_city.strip():
        st.warning("Please enter at least a name or city")
    else:
        with st.spinner("Searching every possible spelling and variation..."):
            results = []
            seen = set()

            # Clean and generate variants
            clean_name = re.sub(r"[.'’]", "", search_name).strip().upper() if search_name else ""
            variants = [search_name]
            if clean_name:
                variants.extend([
                    clean_name,
                    clean_name.replace("ST", "SAINT"),
                    clean_name.replace("SAINT", "ST"),
                    clean_name + " DRUG",
                    clean_name + " PHARMACY",
                    "WALGREEN CO" if "WALGREEN" in clean_name.upper() else ""
                ])

            for variant in set(variants):
                if not variant.strip():
                    continue
                params = {
                    "version": "2.1",
                    "limit": 20,
                    "taxonomy_description": "Pharmacy"   # ← This is the key fix
                }
                if variant: params["organization_name"] = variant
                if search_city: params["city"] = search_city
                if search_state: params["state"] = search_state
                if search_zip: params["postal_code"] = search_zip

                try:
                    resp = requests.get("https://npiregistry.cms.hhs.gov/api/", params=params, timeout=10)
                    if resp.status_code == 200:
                        for item in resp.json().get("results", []):
                            basic = item.get("basic", {})
                            addr = item.get("addresses", [{}])[0] if item.get("addresses") else {}
                            name = basic.get("organization_name", "")
                            city = addr.get("city", "")
                            state = addr.get("state", "")
                            postal = addr.get("postal_code", "")[:5]
                            display = f"{name} — {city}, {state} {postal}".strip(" ,")
                            key = f"{name}|{city}|{state}"
                            if name and key not in seen:
                                seen.add(key)
                                results.append({"name": name, "display": display, "idx": len(results)})
                except:
                    pass  # keep going with other variants

            st.session_state.search_results = results
            if results:
                st.success(f"✅ Found {len(results)} pharmacies")
            else:
                st.warning("No matches found with current search. Try different spelling or use 'Add Manually' below.")

# Display results
if "search_results" in st.session_state and st.session_state.search_results:
    st.subheader("Select the correct pharmacy:")
    for res in st.session_state.search_results:
        if st.button(res["display"], key=f"sel_{res['idx']}"):
            st.session_state.selected_pharmacy = res["display"]
            st.success(f"✅ Selected: {res['name']}")
            st.rerun()

# Final field for fax
recv_name = st.text_input("Receiving Pharmacy on Fax", 
                         value=st.session_state.get("selected_pharmacy", ""), 
                         help="This exact text will appear on the fax")

# ====================== PATIENT & RX (unchanged) ======================
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

# ====================== PDF (unchanged) ======================
if st.button("Generate & Download Fax PDF", type="primary", use_container_width=True):
    # [PDF code exactly the same as last version - omitted here for brevity]
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

    st.success("✅ PDF Generated!")
    st.download_button(
        label="⬇️ Download Fax PDF",
        data=buffer,
        file_name=f"Transfer_Request_{pat_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf",
        mime="application/pdf",
        use_container_width=True
    )
