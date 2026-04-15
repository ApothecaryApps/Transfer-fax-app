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
st.markdown("**Now with Real Fax Sending**")

# ====================== YOUR PHARMACY ======================
# ... (same as before - keeping it short here)
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

pharmacist_name = st.text_input("Supervising Pharmacist", "Craig Doe, PharmD")
tech_name = st.text_input("Technician (optional)", "")
fax_title = st.text_input("Fax Title", "Prescription Transfer Request")

# Receiving Pharmacy + Search (from previous version - abbreviated for space)
st.header("Receiving Pharmacy")
# ... paste your latest search + manual add code here ...

recv_name = st.text_input("Receiving Pharmacy on Fax", value=st.session_state.get("selected_pharmacy", ""), help="Appears on fax")

# Add receiving fax number field
recv_fax_number = st.text_input("Receiving Fax Number (required to send)", placeholder="4805551234 or +14805551234", help="Include country code if needed")

# Patient & RX (same)
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

# ====================== GENERATE PDF ======================
if st.button("Generate PDF First", type="secondary", use_container_width=True):
    # PDF generation code (same as before)
    buffer = io.BytesIO()
    # ... (full PDF code from previous versions)
    # For brevity, assume we have pdf_bytes = buffer.getvalue()
    st.session_state.pdf_bytes = buffer.getvalue()
    st.success("PDF Ready for Sending!")

# ====================== SEND FAX ======================
if "pdf_bytes" in st.session_state:
    documo_key = st.text_input("Documo API Key (secret)", type="password", value="")  # Replace with your key later

    if st.button("📠 SEND FAX NOW", type="primary", use_container_width=True):
        if not recv_fax_number.strip():
            st.error("Please enter the receiving fax number")
        elif not documo_key:
            st.error("Please enter your Documo API Key")
        else:
            with st.spinner("Sending fax..."):
                try:
                    url = "https://api.documo.com/v1/fax/send"
                    files = {'file': ('transfer_request.pdf', st.session_state.pdf_bytes, 'application/pdf')}
                    data = {
                        'recipientFax': recv_fax_number.replace('-','').replace(' ','').replace('(','').replace(')',''),
                        'recipientName': recv_name,
                        'subject': fax_title,
                        'notes': f"Prescription Transfer Request - Patient: {pat_name}"
                    }
                    headers = {'Authorization': f'Basic {documo_key}'}

                    response = requests.post(url, headers=headers, data=data, files=files, timeout=30)
                    
                    if response.status_code in [200, 201]:
                        st.success(f"✅ Fax sent successfully to {recv_fax_number}!")
                        st.info("You will receive confirmation via email from Documo.")
                    else:
                        st.error(f"Failed: {response.text}")
                except Exception as e:
                    st.error(f"Error: {e}")

# Keep the Download button too
if "pdf_bytes" in st.session_state:
    st.download_button("⬇️ Or Just Download PDF", st.session_state.pdf_bytes, 
                       f"Transfer_{pat_name.replace(' ','_')}.pdf", "application/pdf", use_container_width=True)
