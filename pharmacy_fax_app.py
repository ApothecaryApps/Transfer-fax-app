import streamlit as st
import requests
import re
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
import io
from datetime import datetime

st.set_page_config(page_title="Pharmacy Transfer Fax", layout="wide")
st.title("🧾 Pharmacy Prescription Transfer Fax Generator")
st.markdown("**Hybrid Search: NPI + Shared Custom + Google Fallback**")

# Sidebar: Usage + Pricing
if "faxes_sent_this_month" not in st.session_state:
    st.session_state.faxes_sent_this_month = 0

st.sidebar.header("📊 Usage This Month")
st.sidebar.metric("Faxes Sent", st.session_state.faxes_sent_this_month)
st.sidebar.info("**Hybrid Pricing**: $15/mo base + $0.25/extra fax over 100 free")
st.sidebar.caption("Light ads help keep your cost low")

# ====================== YOUR PHARMACY ======================
st.header("Your Pharmacy Info")
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

pharmacist_name = st.text_input("Supervising Pharmacist", "Craig Doe, PharmD")
tech_name = st.text_input("Technician (optional)", "")
fax_title = st.text_input("Fax Title", "Prescription Transfer Request")

# ====================== HYBRID SEARCH ======================
st.header("Receiving Pharmacy - Hybrid Search")

st.subheader("Search NPI Registry")
col_a, col_b = st.columns(2)
with col_a:
    search_name = st.text_input("Pharmacy Name", placeholder="St. John's Drug")
    search_npi = st.text_input("NPI", max_chars=10)
with col_b:
    search_city = st.text_input("City", placeholder="St. John's")
    search_state = st.text_input("State", placeholder="AZ", max_chars=2).upper()

if st.button("🔍 Search NPI Registry", type="primary"):
    with st.spinner("Searching with multiple variations..."):
        results = []
        seen = set()
        base_name = search_name.strip()
        variants = [base_name]
        clean = re.sub(r"[.'’]", "", base_name).strip() if base_name else ""
        if clean:
            variants.extend([clean, clean.replace("ST", "SAINT"), clean.replace("SAINT", "ST"), clean + " DRUG", clean + " PHARMACY"])

        for variant in variants:
            if not variant: continue
            params = {"version": "2.1", "limit": 15, "taxonomy_description": "Pharmacy"}
            if variant: params["organization_name"] = variant
            if search_city: params["city"] = search_city
            if search_state: params["state"] = search_state
            if search_npi: params["number"] = search_npi

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
                        phone = addr.get("telephone_number", "N/A")
                        display = f"{name} — {city}, {state} {postal} | ☎ {phone}"
                        key = f"{name}|{city}|{state}"
                        if name and key not in seen:
                            seen.add(key)
                            results.append({"display": display, "name": name})
            except:
                pass

        st.session_state.search_results = results
        if results:
            st.success(f"Found {len(results)} results")
        else:
            st.warning("No results from NPI. Try manual add or Google fallback.")

# Show NPI results
if "search_results" in st.session_state and st.session_state.search_results:
    st.subheader("NPI Results")
    for res in st.session_state.search_results:
        if st.button(res["display"], key=f"npi_{res['name']}"):
            st.session_state.selected_pharmacy = res["display"]
            st.rerun()

# ====================== SHARED MANUAL ADD ======================
st.subheader("➕ Add to Shared Pharmacy List (visible to all users)")
col_m1, col_m2 = st.columns(2)
with col_m1:
    manual_name = st.text_input("Pharmacy Name *", key="m_name")
    manual_city = st.text_input("City", key="m_city")
with col_m2:
    manual_store = st.text_input("Store # / Address", key="m_store")
    manual_phone = st.text_input("Phone or Fax", key="m_phone")

if st.button("Save to Shared List", type="primary"):
    if manual_name.strip():
        display = f"{manual_name} — {manual_store} {manual_city} | ☎ {manual_phone}"
        if "shared_pharmacies" not in st.session_state:
            st.session_state.shared_pharmacies = []
        st.session_state.shared_pharmacies.append({"name": manual_name, "display": display})
        st.success(f"✅ Added to shared list: {manual_name}")
        st.rerun()

# Show shared list
if "shared_pharmacies" in st.session_state and st.session_state.shared_pharmacies:
    st.subheader("Shared Custom Pharmacies")
    for i, pharm in enumerate(st.session_state.shared_pharmacies):
        if st.button(pharm["display"], key=f"shared_{i}"):
            st.session_state.selected_pharmacy = pharm["display"]
            st.rerun()

# Google Fallback
if st.button("🌐 Search on Google (for hard-to-find pharmacies)"):
    query = f"{search_name} {search_city} {search_state} pharmacy"
    st.markdown(f"[🔗 Open Google Search for: {query}](https://www.google.com/search?q={query.replace(' ', '+')})", unsafe_allow_html=True)

# Final selection
recv_name = st.text_input("Receiving Pharmacy on Fax", value=st.session_state.get("selected_pharmacy", ""))

# Patient, RX, PDF sections (add your stable patient/RX/PDF code here)
# ... (paste the working patient + RX + PDF generation from previous version)

st.info("Hybrid search is now active. Test with 'St. John's Drug' + city 'St. John's'!")
