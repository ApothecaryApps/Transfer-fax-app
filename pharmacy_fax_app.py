import streamlit as st
import io
from datetime import datetime

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch

from srfax import queue_fax, wait_for_fax
from pharmacy_sheet import search_pharmacies, add_pharmacy

st.set_page_config(page_title="Pharmacy Transfer Fax", layout="wide")
st.title("🧾 Pharmacy Prescription Transfer Fax Generator")
st.markdown("**Live with SRFax** (PDF download + portal send works; API send needs IP unlock)")

st.header("Your Pharmacy Info (Requesting)")
col1, col2 = st.columns(2)
with col1:
    req_name = st.text_input("Pharmacy Name", "Western Drug")
    req_address = st.text_input("Address", "106 East Main Street")
    req_citystatezip = st.text_input("City, State ZIP", "Springerville, AZ 85938")
with col2:
    req_phone = st.text_input("Phone", "(928) 333-4321")
    req_fax = st.text_input("Fax", "(928) 333-4328")

pharmacist_name = st.text_input("Supervising Pharmacist", "Craig Mathews, PharmD")
tech_name = st.text_input("Technician", "Dantae Stires")
fax_title = st.text_input("Fax Title", "Prescription Transfer Request")

st.header("Receiving pharmacy")
st.caption(
    "Search the shared directory (name, store #, address, city, phone). "
    "Tap a result to load name + fax. If it’s missing, add it below — add only, no edit/delete."
)

s1, s2 = st.columns(2)
with s1:
    q_name = st.text_input("Search text (name / store # / address)", placeholder="Walgreens 5712")
    q_phone = st.text_input("Search phone", placeholder="4805551234")
with s2:
    q_city = st.text_input("City", placeholder="Phoenix")
    c1, c2 = st.columns(2)
    with c1:
        q_state = st.text_input("State", placeholder="AZ", max_chars=2)
    with c2:
        q_store = st.text_input("Store #", placeholder="5712")

if st.button("🔎 Search directory", use_container_width=True):
    try:
        with st.spinner("Searching shared list..."):
            st.session_state.pharmacy_hits = search_pharmacies(
                query=q_name,
                store_number=q_store,
                city=q_city,
                state=q_state,
                phone=q_phone,
            )
        if not st.session_state.pharmacy_hits:
            st.warning("No matches. Add the pharmacy below, or clear filters and try again.")
    except Exception as e:
        st.error(f"Search error: {e}")

hits = st.session_state.get("pharmacy_hits") or []
if hits:
    st.subheader("Results — tap one to load")
    for i, p in enumerate(hits):
        detail = " · ".join(
            x
            for x in [
                p.get("address"),
                f"{p.get('city')} {p.get('state')} {p.get('zip')}".strip(),
                f"Store #{p['store_number']}" if p.get("store_number") else "",
                f"Phone {p['phone']}" if p.get("phone") else "",
                f"Fax {p['fax']}" if p.get("fax") else "",
            ]
            if x and str(x).strip()
        )
        if st.button(f"Use: {p.get('name')}", key=f"pick_{i}", use_container_width=True):
            st.session_state.recv_name = p.get("name") or ""
            st.session_state.recv_fax = p.get("fax") or ""
            st.rerun()
        st.caption(detail)

if "recv_name" not in st.session_state:
    st.session_state.recv_name = ""
if "recv_fax" not in st.session_state:
    st.session_state.recv_fax = ""

recv_name = st.text_input("Receiving Pharmacy Name (required)", key="recv_name")
recv_fax_number = st.text_input(
    "Receiving Fax Number (required)",
    key="recv_fax",
    placeholder="4805551234",
)

with st.expander("➕ Add pharmacy to shared directory (if not found)"):
    st.caption("Adds a new row only. Cannot edit or delete existing entries from the app.")
    a_name = st.text_input("Name (required)", key="add_name")
    a_fax = st.text_input("Fax (required, 10 digits)", key="add_fax")
    a_store = st.text_input("Store #", key="add_store")
    a_addr = st.text_input("Street address", key="add_addr")
    a_city = st.text_input("City", key="add_city")
    ac1, ac2 = st.columns(2)
    with ac1:
        a_state = st.text_input("State", key="add_state", max_chars=2)
    with ac2:
        a_zip = st.text_input("ZIP", key="add_zip")
    a_phone = st.text_input("Phone", key="add_phone")
    a_by = st.text_input("Added by (your pharmacy / initials)", key="add_by")
    if st.button("Save to shared directory", use_container_width=True):
        try:
            add_pharmacy(
                name=a_name,
                fax=a_fax,
                store_number=a_store,
                address=a_addr,
                city=a_city,
                state=a_state,
                zip_code=a_zip,
                phone=a_phone,
                added_by=a_by,
            )
            st.success("Added. You can search for it now.")
            st.session_state.recv_name = a_name.strip()
            from pharmacy_sheet import digits_only

            fax_digits = digits_only(a_fax)
            if len(fax_digits) == 11 and fax_digits.startswith("1"):
                fax_digits = fax_digits[-10:]
            st.session_state.recv_fax = fax_digits
            st.session_state.pharmacy_hits = []
            st.rerun()
        except Exception as e:
            st.error(str(e))

st.header("Patient")
st.caption("Keep real patient details in the app only — don’t paste them into chat.")
pat_name = st.text_input("Patient Full Name", "Jane A. Smith")
pat_dob = st.text_input("Date of Birth", "01/15/1985")

st.header("Prescriptions to Transfer")
if "rx_list" not in st.session_state:
    st.session_state.rx_list = ["Testing fax, give this to Craig", "Thank you!"]

for i in range(len(st.session_state.rx_list)):
    st.session_state.rx_list[i] = st.text_input(
        f"RX Line {i+1}", value=st.session_state.rx_list[i], key=f"rx_{i}"
    )

if st.button("➕ Add RX Line"):
    st.session_state.rx_list.append("")
    st.rerun()
if len(st.session_state.rx_list) > 1 and st.button("🗑 Remove Last"):
    st.session_state.rx_list.pop()
    st.rerun()


def build_pdf_bytes() -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=50
    )
    styles = getSampleStyleSheet()
    bold = ParagraphStyle("Bold", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=11)

    story = []
    story.append(Paragraph(f"<b>{fax_title}</b>", styles["Heading1"]))
    story.append(Spacer(1, 12))
    story.append(
        Paragraph(
            f"<b>{req_name}</b><br/>{req_address}<br/>{req_citystatezip}<br/>"
            f"Phone: {req_phone} Fax: {req_fax}<br/>Requesting: {pharmacist_name}"
            + (f"<br/>Technician: {tech_name}" if tech_name.strip() else ""),
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 20))
    story.append(Paragraph(f"<b>Transfers requested from:</b> {recv_name}", bold))
    story.append(Spacer(1, 15))
    story.append(Paragraph(f"<b>Patient:</b> {pat_name}  DOB: {pat_dob}", bold))
    story.append(Spacer(1, 15))

    data = [["Prescription / Request"]] + [[line] for line in st.session_state.rx_list if line.strip()]
    if len(data) > 1:
        t = Table(data, colWidths=[6.5 * inch])
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("GRID", (0, 0), (-1, -1), 1, colors.black),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ]
            )
        )
        story.append(t)

    story.append(Spacer(1, 30))
    story.append(
        Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y %I:%M %p')}", styles["Normal"])
    )
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


if st.button("📠 Generate PDF & Send Fax", type="primary", use_container_width=True):
    if not (recv_name or "").strip():
        st.error("Please enter receiving pharmacy name")
    elif not (recv_fax_number or "").strip():
        st.error("Please enter receiving fax number")
    else:
        with st.spinner("Generating PDF..."):
            try:
                pdf_bytes = build_pdf_bytes()
                st.success(f"PDF generated ({len(pdf_bytes)} bytes)")
                st.download_button(
                    "Download PDF (use with SRFax portal)",
                    data=pdf_bytes,
                    file_name="transfer.pdf",
                    mime="application/pdf",
                )
                try:
                    with st.spinner("Trying SRFax API send..."):
                        fax_id = queue_fax(
                            st.secrets,
                            recv_fax_number,
                            pdf_bytes,
                            filename="transfer.pdf",
                        )
                        st.info(f"Queued with SRFax. Job ID: {fax_id}")
                        result = wait_for_fax(st.secrets, fax_id)
                        status = None
                        if isinstance(result, dict):
                            status = result.get("SentStatus")
                        elif isinstance(result, list) and result:
                            status = result[0].get("SentStatus")
                        if status == "Sent":
                            st.success(f"✅ Fax successfully sent to {recv_fax_number}!")
                            st.balloons()
                        elif status == "Failed":
                            st.error(f"Fax failed: {result}")
                        else:
                            st.warning(f"Still in progress / unknown status: {result}")
                except Exception as send_err:
                    st.warning(
                        f"API send didn’t work ({send_err}). Use Download PDF → SRFax portal to send."
                    )
            except Exception as e:
                st.error(f"Error: {e}")

st.caption("Directory is a shared Google Sheet. App can add new pharmacies only — no edit/delete.")
