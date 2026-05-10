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
st.markdown("**Fax.Plus - One Button Version**")

FAXPLUS_TOKEN = "alohi_pat_csW4VhPcKBUAEwbHuyERJJ_aMKXjvtsjJDsGnEr7rtr5QdISTGpmm2sA60uN0YJpYyDkreEXJYMR9rJDkD"

fax_title = st.text_input("Fax Title", "Prescription Transfer Request")

st.header("Your Pharmacy Info")
req_name = st.text_input("Pharmacy Name", "Western Drug")
req_address = st.text_input("Address", "106 East Main Street")
req_citystatezip = st.text_input("City, State ZIP", "Springerville, AZ 85938")
req_phone = st.text_input("Phone", "(928) 333-4321")
req_fax = st.text_input("Fax", "(928) 333-4328")
pharmacist_name = st.text_input("Pharmacist", "Craig Mathews, PharmD")

st.header("Receiving")
recv_name = st.text_input("Receiving Pharmacy", "Walgreens #1234")
recv_fax_number = st.text_input("Receiving Fax Number", placeholder="4805551234")

st.header("Patient")
pat_name = st.text_input("Patient Name", "Jane A. Smith")
pat_dob = st.text_input("DOB", "01/15/1985")

st.header("Prescriptions")
if "rx_list" not in st.session_state:
    st.session_state.rx_list = ["Testing fax, give this to Craig", "Thank you!"]

for i in range(len(st.session_state.rx_list)):
    st.session_state.rx_list[i] = st.text_input(f"RX Line {i+1}", value=st.session_state.rx_list[i], key=f"rx_{i}")

if st.button("➕ Add RX Line"):
    st.session_state.rx_list.append("")
    st.rerun()
if len(st.session_state.rx_list) > 1 and st.button("🗑 Remove Last"):
    st.session_state.rx_list.pop()
    st.rerun()

# ====================== MAIN ACTION ======================
if st.button("📠 Generate PDF & Send Fax", type="primary", use_container_width=True):
    if not recv_fax_number.strip():
        st.error("Please enter receiving fax number")
    else:
        with st.spinner("Generating PDF and sending..."):
            try:
                # Generate PDF
                buffer = io.BytesIO()
                doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=50)
                styles = getSampleStyleSheet()
                bold = ParagraphStyle('Bold', parent=styles['Normal'], fontName="Helvetica-Bold", fontSize=11)

                story = []
                story.append(Paragraph(f"<b>{fax_title}</b>", styles['Heading1']))
                story.append(Spacer(1, 12))
                story.append(Paragraph(f"<b>{req_name}</b><br/>{req_address}<br/>{req_citystatezip}<br/>Phone: {req_phone} Fax: {req_fax}<br/>Requesting: {pharmacist_name}", styles['Normal']))
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
                story.append(Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y %I:%M %p')}", styles['Normal']))

                doc.build(story)
                buffer.seek(0)
                pdf_bytes = buffer.getvalue()

                st.success(f"PDF generated ({len(pdf_bytes)} bytes)")

                # Send to Fax.Plus
                headers = {"Authorization": f"Bearer {FAXPLUS_TOKEN}"}
                upload_resp = requests.post(
                    "https://restapi.fax.plus/v3/accounts/self/files",
                    headers=headers,
                    files={'file': ('transfer.pdf', pdf_bytes, 'application/pdf')}
                )

                if upload_resp.status_code not in [200, 201]:
                    st.error(f"Upload failed: {upload_resp.text}")
                else:
                    file_path = upload_resp.json().get("path") or upload_resp.json().get("filename")
                    send_resp = requests.post(
                        "https://restapi.fax.plus/v3/accounts/self/outbox",
                        headers=headers,
                        json={
                            "to": [recv_fax_number.replace("-", "").replace(" ", "").replace("(", "").replace(")", "")],
                            "files": [file_path],
                            "comment": f"Prescription Transfer - {pat_name}"
                        }
                    )

                    if send_resp.status_code in [200, 201]:
                        st.success(f"✅ Fax successfully sent to {recv_fax_number}!")
                        st.balloons()
                    else:
                        st.error(f"Send failed: {send_resp.text}")
            except Exception as e:
                st.error(f"Error: {e}")

st.caption("Use the big red button")
