import streamlit as st
import io
from datetime import datetime

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch

from srfax import queue_fax, wait_for_fax
from pharmacy_sheet import search_pharmacies, add_pharmacy, digits_only

st.set_page_config(page_title="Pharmacy Transfer Fax", layout="wide")

# --- Dense layout + section card accents ---
st.markdown(
    """
<style>
/* Slightly denser Streamlit spacing */
div[data-testid="stVerticalBlock"] > div { gap: 0.35rem; }
div[data-testid="stHorizontalBlock"] { gap: 0.5rem; }
.stTextInput > div > div > input,
.stTextInput input {
  font-size: 0.92rem !important;
  padding-top: 0.35rem !important;
  padding-bottom: 0.35rem !important;
}
div[data-testid="stExpander"] { margin-top: 0.25rem; margin-bottom: 0.25rem; }
label { font-size: 0.85rem !important; }
div[data-testid="stCaptionContainer"] p { margin-bottom: 0.15rem; }
/* Constrain main content width a bit while keeping layout=wide */
.block-container {
  padding-top: 1.25rem !important;
  padding-bottom: 1.5rem !important;
  max-width: 1100px;
}
/* Section accent headers */
.section-label {
  font-weight: 700;
  font-size: 1.05rem;
  margin: 0 0 0.35rem 0;
  padding-left: 0.55rem;
  border-left: 4px solid #64748b;
  line-height: 1.3;
}
.section-label.req { border-left-color: #0d9488; color: #0f766e; }
.section-label.recv { border-left-color: #6366f1; color: #4338ca; }
.section-label.patient { border-left-color: #16a34a; color: #15803d; }
.section-label.rx { border-left-color: #d97706; color: #b45309; }
.section-label.send { border-left-color: #334155; color: #1e293b; }
/* Soft left border on bordered containers via parent wrapper */
div[data-testid="stVerticalBlockBorderWrapper"] {
  border-radius: 8px !important;
}
</style>
""",
    unsafe_allow_html=True,
)

st.title("🧾 Pharmacy Prescription Transfer Fax Generator")
st.markdown("**Live with SRFax** — PDF download + API send working")

# ---------- Session defaults ----------
if "add_open" not in st.session_state:
    st.session_state.add_open = False
if "add_prefill" not in st.session_state:
    st.session_state.add_prefill = {}
if "rx_list" not in st.session_state:
    st.session_state.rx_list = ["Testing fax, give this to Craig", "Thank you!"]
if "pharmacy_hits" not in st.session_state:
    st.session_state.pharmacy_hits = []

# Apply deferred receiving-pharmacy fill BEFORE recv_* widgets are created.
if "_pending_recv_name" in st.session_state:
    st.session_state.recv_name = st.session_state.pop("_pending_recv_name")
    st.session_state.recv_fax = st.session_state.pop("_pending_recv_fax", "")
_flash = st.session_state.pop("_flash_added", False)

if "recv_name" not in st.session_state:
    st.session_state.recv_name = ""
if "recv_fax" not in st.session_state:
    st.session_state.recv_fax = ""

# ========== YOUR PHARMACY (requesting) ==========
with st.container(border=True):
    st.markdown('<p class="section-label req">Your pharmacy (requesting)</p>', unsafe_allow_html=True)
    r1, r2, r3, r4 = st.columns([2.2, 2.2, 1.4, 1.4])
    with r1:
        req_name = st.text_input("Pharmacy Name", "Western Drug")
    with r2:
        req_address = st.text_input("Address", "106 East Main Street")
    with r3:
        req_phone = st.text_input("Phone", "(928) 333-4321")
    with r4:
        req_fax = st.text_input("Fax", "(928) 333-4328")

    r5, r6, r7 = st.columns([2, 2, 2])
    with r5:
        req_citystatezip = st.text_input("City, State ZIP", "Springerville, AZ 85938")
    with r6:
        pharmacist_name = st.text_input("Supervising Pharmacist", "Craig Mathews, PharmD")
    with r7:
        tech_name = st.text_input("Technician", "Dantae Stires")

    fax_title = st.text_input("Fax Title", "Prescription Transfer Request")

# ========== RECEIVING PHARMACY ==========
with st.container(border=True):
    st.markdown('<p class="section-label recv">Receiving pharmacy</p>', unsafe_allow_html=True)
    st.caption(
        "Search the shared directory (name, store #, address, city, phone). "
        "Tap a result to load name + fax. If it’s missing, add it below — add only, no edit/delete."
    )

    s1, s2, s3, s4, s5 = st.columns([2.2, 1.1, 1.4, 0.7, 1.2])
    with s1:
        q_name = st.text_input("Search text (name / store # / address)", placeholder="Walgreens 5712")
    with s2:
        q_store = st.text_input("Store #", placeholder="5712")
    with s3:
        q_city = st.text_input("City", placeholder="Phoenix")
    with s4:
        q_state = st.text_input("State", placeholder="AZ", max_chars=2)
    with s5:
        q_phone = st.text_input("Search phone", placeholder="4805551234")

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
        st.markdown("**Results — tap one to load**")
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
            # Use buttons run BEFORE recv_* widgets → safe to set session_state keys directly.
            if st.button(f"Use: {p.get('name')}", key=f"pick_{i}", use_container_width=True):
                st.session_state.recv_name = p.get("name") or ""
                st.session_state.recv_fax = p.get("fax") or ""
                st.rerun()
            st.caption(detail)

    if _flash:
        st.success("Added. Name and fax loaded below — you can search for it too.")

    recv_name = st.text_input("Receiving Pharmacy Name (required)", key="recv_name")
    recv_fax_number = st.text_input(
        "Receiving Fax Number (required)",
        key="recv_fax",
        placeholder="4805551234",
    )

    # --- Add pharmacy panel (toggle + form; not a collapsing expander) ---
    if not st.session_state.add_open:
        if st.button("➕ Add pharmacy to directory", use_container_width=True):
            st.session_state.add_prefill = {
                "name": (q_name or "").strip(),
                "store": (q_store or "").strip(),
                "city": (q_city or "").strip(),
                "state": (q_state or "").strip(),
                "phone": (q_phone or "").strip(),
            }
            st.session_state.add_open = True
            st.rerun()
    else:
        with st.container(border=True):
            st.markdown("**➕ Add pharmacy to shared directory**")
            st.caption("Adds a new row only. Cannot edit or delete existing entries from the app.")
            pf = st.session_state.get("add_prefill") or {}

            with st.form("add_pharmacy_form", clear_on_submit=True):
                a1, a2 = st.columns([2, 1.2])
                with a1:
                    a_name = st.text_input(
                        "Name (required)",
                        value=pf.get("name", ""),
                    )
                with a2:
                    a_fax = st.text_input("Fax (required, 10 digits)", value="")

                a3, a4, a5, a6 = st.columns([1, 2, 1.4, 0.7])
                with a3:
                    a_store = st.text_input("Store #", value=pf.get("store", ""))
                with a4:
                    a_addr = st.text_input("Street address", value="")
                with a5:
                    a_city = st.text_input("City", value=pf.get("city", ""))
                with a6:
                    a_state = st.text_input("State", value=pf.get("state", ""), max_chars=2)

                a7, a8, a9 = st.columns([1, 1.4, 1.6])
                with a7:
                    a_zip = st.text_input("ZIP", value="")
                with a8:
                    a_phone = st.text_input("Phone", value=pf.get("phone", ""))
                with a9:
                    a_by = st.text_input("Added by (pharmacy / initials)", value="")

                submitted = st.form_submit_button(
                    "Save to shared directory", use_container_width=True, type="primary"
                )

            if submitted:
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
                    fax_digits = digits_only(a_fax)
                    if len(fax_digits) == 11 and fax_digits.startswith("1"):
                        fax_digits = fax_digits[-10:]
                    # Stash for next run — never write recv_* after those widgets already exist.
                    st.session_state["_pending_recv_name"] = (a_name or "").strip()
                    st.session_state["_pending_recv_fax"] = fax_digits
                    st.session_state.pharmacy_hits = []
                    st.session_state["_flash_added"] = True
                    st.session_state.add_prefill = {}
                    st.session_state.add_open = False
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

            if st.button("Cancel", key="add_cancel", use_container_width=True):
                st.session_state.add_open = False
                st.session_state.add_prefill = {}
                st.rerun()

# ========== PATIENT ==========
with st.container(border=True):
    st.markdown('<p class="section-label patient">Patient</p>', unsafe_allow_html=True)
    st.caption("Keep real patient details in the app only — don’t paste them into chat.")
    p1, p2 = st.columns(2)
    with p1:
        pat_name = st.text_input("Patient Full Name", "Jane A. Smith")
    with p2:
        pat_dob = st.text_input("Date of Birth", "01/15/1985")

# ========== PRESCRIPTIONS ==========
with st.container(border=True):
    st.markdown('<p class="section-label rx">Prescriptions to transfer</p>', unsafe_allow_html=True)
    for i in range(len(st.session_state.rx_list)):
        st.session_state.rx_list[i] = st.text_input(
            f"RX Line {i+1}", value=st.session_state.rx_list[i], key=f"rx_{i}"
        )

    bx1, bx2 = st.columns(2)
    with bx1:
        if st.button("➕ Add RX Line", use_container_width=True):
            st.session_state.rx_list.append("")
            st.rerun()
    with bx2:
        if len(st.session_state.rx_list) > 1 and st.button(
            "🗑 Remove Last", use_container_width=True
        ):
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


# ========== SEND ==========
with st.container(border=True):
    st.markdown('<p class="section-label send">Send fax</p>', unsafe_allow_html=True)
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
    
