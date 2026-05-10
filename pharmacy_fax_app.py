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
st.markdown("**Fax.Plus - Fixed Two-Step Upload**")

FAXPLUS_TOKEN = "alohi_pat_csW4VhPcKBUAEwbHuyERJJ_aMKXjvtsjJDsGnEr7rtr5QdISTGpmm2sA60uN0YJpYyDkreEXJYMR9rJDkD"

# ... [Keep all your form fields the same: Your Pharmacy, Receiving, Patient, RX List] ...

# (Paste your existing form fields here - I'm shortening for space)

# ====================== GENERATE PDF ======================
if st.button("Generate PDF", type="secondary", use_container_width=True):
    buffer = io.BytesIO()
    # ... (your full PDF generation code - same as before) ...
    doc.build(story)
    buffer.seek(0)
    st.session_state.pdf_bytes = buffer.getvalue()
    st.success("✅ PDF Generated!")

# ====================== SEND FAX (Improved) ======================
if "pdf_bytes" in st.session_state:
    if st.button("📠 SEND FAX NOW", type="primary", use_container_width=True):
        if not recv_fax_number.strip():
            st.error("Enter receiving fax number")
        else:
            with st.spinner("Uploading file then sending fax..."):
                try:
                    headers = {"Authorization": f"Bearer {FAXPLUS_TOKEN}"}

                    # Step 1: Upload file
                    upload_url = "https://restapi.fax.plus/v3/accounts/self/files"
                    files = {'file': ('transfer.pdf', st.session_state.pdf_bytes, 'application/pdf')}
                    
                    upload_resp = requests.post(upload_url, headers=headers, files=files)
                    
                    if upload_resp.status_code not in [200, 201]:
                        st.error(f"Upload failed: {upload_resp.text}")
                        st.stop()

                    # Get the file path from response
                    upload_data = upload_resp.json()
                    file_path = upload_data.get("path") or upload_data.get("filename") or upload_data.get("file_path")
                    
                    if not file_path:
                        st.error("Could not get file path from upload response")
                        st.stop()

                    # Step 2: Send fax
                    send_url = "https://restapi.fax.plus/v3/accounts/self/outbox"
                    payload = {
                        "to": [recv_fax_number.replace("-", "").replace(" ", "").replace("(", "").replace(")", "")],
                        "files": [file_path],
                        "comment": f"Prescription Transfer Request - Patient: {pat_name}"
                    }

                    send_resp = requests.post(send_url, headers=headers, json=payload)

                    if send_resp.status_code in [200, 201]:
                        st.success(f"✅ Fax sent successfully to {recv_fax_number}!")
                        st.balloons()
                    else:
                        st.error(f"Send failed ({send_resp.status_code}): {send_resp.text[:500]}")
                except Exception as e:
                    st.error(f"Error: {str(e)}")

# Download button
if "pdf_bytes" in st.session_state:
    st.download_button("⬇️ Download PDF Instead", st.session_state.pdf_bytes, 
                       f"Transfer_{pat_name.replace(' ','_')}.pdf", "application/pdf", use_container_width=True)
