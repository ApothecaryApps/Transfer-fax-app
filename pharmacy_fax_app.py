import streamlit as st
import io
from datetime import datetime

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch

from srfax import queue_fax, wait_for_fax, get_fax_status, retrieve_sent_fax_pdf, delete_sent_faxes
import importlib
import pharmacy_sheet as _ps
importlib.reload(_ps)  # make sure Streamlit uses the latest pharmacy_sheet.py
from pharmacy_sheet import search_pharmacies, add_pharmacy, digits_only, add_feedback
from pharmacy_sheet import log_sign_in
from pharmacy_sheet import (
    log_fax,
    update_fax_log,
    mark_fax_received,
    read_fax_log,
    sync_delivery_results,
    display_status,
    non_responders,
    record_resend,
    cleanup_old_faxes,
    is_deleted,
)

st.set_page_config(page_title="Pharmacy Transfer Fax", layout="wide")


def _auth_configured() -> bool:
    """True only if the [auth] block exists in Streamlit Secrets."""
    try:
        return "auth" in st.secrets
    except Exception:
        return False


def _is_signed_in() -> bool:
    try:
        return bool(getattr(st.user, "is_logged_in", False))
    except Exception:
        return False


def _current_user_email() -> str:
    # Google sign-in first (st.user when logged in), then the older fallbacks.
    try:
        if _is_signed_in():
            email = getattr(st.user, "email", None)
            if email:
                return str(email)
    except Exception:
        pass
    for attr in ("user", "experimental_user"):
        try:
            email = getattr(st, attr).email
            if email:
                return str(email)
        except Exception:
            pass
    return "unknown"


def _sign_in_box():
    """Sidebar sign-in / sign-out. Optional for now: the app works either way."""
    try:
        with st.sidebar:
            if not _auth_configured() or not hasattr(st, "login"):
                return
            if _is_signed_in():
                st.caption(f"Signed in as {getattr(st.user, 'email', '') or 'your Google account'}")
                if st.button("Sign out", key="auth_sign_out"):
                    st.logout()
            else:
                if st.button("Sign in with Google", key="auth_sign_in"):
                    st.login()
    except Exception:
        st.sidebar.caption("Sign-in is unavailable right now. You can still use the app.")


_sign_in_box()


def _log_sign_in_once():
    """Write one SignInLog row per signed-in session (not on every rerun). Never breaks the app."""
    try:
        if not _is_signed_in():
            return
        email = str(getattr(st.user, "email", "") or "").strip()
        if not email:
            return
        flag = f"_signin_logged_{email.lower()}"
        if st.session_state.get(flag):
            return
        st.session_state[flag] = True  # set first so a Sheet error can't cause repeat tries each rerun
        log_sign_in(email, str(getattr(st.user, "name", "") or ""))
    except Exception:
        pass


_log_sign_in_once()


def _safe_log_fax(**kw):
    """Write to the sent-fax log. Never blocks sending: on error, show a small warning only."""
    try:
        return log_fax(sent_by=_current_user_email(), **kw)
    except Exception:
        st.caption("⚠️ Couldn't save this fax to the Sent faxes log (the fax itself is not affected).")
        return None


def _safe_update_log(log_id, **kw):
    if not log_id:
        return
    try:
        update_fax_log(log_id, **kw)
    except Exception:
        st.caption("⚠️ Couldn't update the Sent faxes log (the fax itself is not affected).")


def _short_reason(err) -> str:
    """Fixed, PHI-free label for an error (raw error text is never shown or saved)."""
    try:
        import requests as _rq

        if isinstance(err, (_rq.exceptions.ConnectionError, _rq.exceptions.Timeout)):
            return "Network error"
        if isinstance(err, _rq.exceptions.RequestException):
            return "SRFax error"
    except Exception:
        pass
    if isinstance(err, ValueError):
        return "Fax number error"
    return "SRFax error"


def _auto_delete_once():
    """Once per session: delete SRFax copies 7+ days after the last send. Never breaks the app."""
    if st.session_state.get("_cleanup_done"):
        return
    st.session_state["_cleanup_done"] = True
    try:
        if "SRFAX_ACCESS_ID" not in st.secrets:
            return
        cleanup_old_faxes(lambda ids: delete_sent_faxes(st.secrets, ids))
    except Exception:
        pass


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
  padding: 0.3rem 0.65rem;
  border-radius: 6px;
  background: #475569;
  color: #ffffff !important;
  line-height: 1.3;
}
/* Colored band, white text (readable in light and dark theme) */
.section-label.req { background: #0f766e; }
.section-label.recv { background: #4338ca; }
.section-label.patient { background: #15803d; }
.section-label.rx { background: #b45309; }
.section-label.send { background: #1e293b; }
/* Soft left border on bordered containers via parent wrapper */
div[data-testid="stVerticalBlockBorderWrapper"] {
  border-radius: 8px !important;
}
</style>
""",
    unsafe_allow_html=True,
)

st.title("🧾 Pharmacy Prescription Transfer Fax Generator")
st.markdown("**Live with SRFax**")

# ---------- Session defaults ----------
if "add_open" not in st.session_state:
    st.session_state.add_open = False
if "add_prefill" not in st.session_state:
    st.session_state.add_prefill = {}
if "rx_list" not in st.session_state:
    st.session_state.rx_list = [""]
if "pharmacy_hits" not in st.session_state:
    st.session_state.pharmacy_hits = []

# After any send attempt, clear patient/Rx/receiving fields BEFORE widgets are created.
if "pat_name" not in st.session_state:
    st.session_state.pat_name = ""
if "pat_dob" not in st.session_state:
    st.session_state.pat_dob = ""
if st.session_state.pop("_clear_after_send", False):
    st.session_state.pat_name = ""
    st.session_state.pat_dob = ""
    for _k in [k for k in st.session_state.keys() if str(k).startswith("rx_") and k != "rx_list"]:
        del st.session_state[_k]
    st.session_state.rx_list = [""]
    st.session_state.recv_name = ""
    st.session_state.recv_fax = ""
    st.session_state.pharmacy_hits = []
    st.session_state.pop("_pending_recv_name", None)
    st.session_state.pop("_pending_recv_fax", None)
_flash_sent = st.session_state.pop("_flash_sent", "")
_flash_fail = st.session_state.pop("_flash_fail", "")
_auto_delete_once()

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
            st.error("Search error. Please try again in a minute.")

    hits = st.session_state.get("pharmacy_hits") or []
    if hits:
        st.markdown("**Results — tap one to load**")
        max_shown = 50  # keep the list phone-friendly
        if len(hits) > max_shown:
            st.info(
                f"Showing the first {max_shown} of {len(hits):,} matches. "
                "Add a name, city, or ZIP to narrow it down."
            )
        for i, p in enumerate(hits[:max_shown]):
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
        pat_name = st.text_input("Patient Full Name", key="pat_name")
    with p2:
        pat_dob = st.text_input("Date of Birth", key="pat_dob", placeholder="MM/DD/YYYY")

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

    story.append(Spacer(1, 15))
    story.append(Paragraph("If no refills remain, please call or fax us back.", styles["Normal"]))
    story.append(Spacer(1, 30))
    story.append(
        Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y %I:%M %p')}", styles["Normal"])
    )
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def _friendly_status(result, status=None) -> str:
    """Turn an SRFax status reply into short plain text (never a raw dict)."""
    item = result[0] if isinstance(result, list) and result else result
    if isinstance(item, dict):
        status = item.get("SentStatus") or status
        reason = (item.get("ErrorCode") or "").strip() if isinstance(item.get("ErrorCode"), str) else ""
        if reason and status == "Failed":
            return f"Failed ({reason})"
    return str(status or "Unknown")


# ========== SEND ==========
with st.container(border=True):
    st.markdown('<p class="section-label send">Send fax</p>', unsafe_allow_html=True)
    if _flash_sent:
        st.success(f"✅ {_flash_sent} Form cleared for the next request.")
    if _flash_fail:
        st.error(f"❌ {_flash_fail} Form cleared — please re-enter and try again.")
    _attempted = False
    if st.button("📠 Generate PDF & Send Fax", type="primary", use_container_width=True):
        if not (recv_name or "").strip():
            st.error("Please enter receiving pharmacy name")
        elif not (recv_fax_number or "").strip():
            st.error("Please enter receiving fax number")
        else:
            _attempted = True
            pdf_bytes = None
            try:
                with st.spinner("Generating PDF..."):
                    pdf_bytes = build_pdf_bytes()
            except Exception:
                st.session_state["_flash_fail"] = "PDF error — fax not sent."
            if pdf_bytes is not None:
                try:
                    with st.spinner("Sending with SRFax..."):
                        try:
                            fax_id = queue_fax(st.secrets, recv_fax_number, pdf_bytes, filename="transfer.pdf")
                        except Exception as queue_err:
                            _safe_log_fax(
                                to_pharmacy=recv_name,
                                to_fax=recv_fax_number,
                                delivery_result="not sent",
                                status="failed",
                                note=_short_reason(queue_err),
                            )
                            raise
                        finally:
                            pdf_bytes = None  # drop the PDF from memory right after the send attempt
                        log_id = _safe_log_fax(
                            to_pharmacy=recv_name,
                            to_fax=recv_fax_number,
                            srfax_id=fax_id,
                            delivery_result="pending",
                            status="waiting",
                        )
                        st.info(f"Queued with SRFax. Job ID: {fax_id}")
                        result = wait_for_fax(st.secrets, fax_id)
                        status = None
                        if isinstance(result, dict):
                            status = result.get("SentStatus")
                        elif isinstance(result, list) and result:
                            status = result[0].get("SentStatus")
                        if status == "Sent":
                            _safe_update_log(log_id, delivery_result="delivered")
                            st.success(f"✅ Fax successfully sent to {recv_fax_number}!")
                            st.balloons()
                            st.session_state["_flash_sent"] = f"Fax sent to {recv_fax_number}."
                        elif status == "Failed":
                            _safe_update_log(
                                log_id, delivery_result="failed", status="failed", note="SRFax delivery failed"
                            )
                            st.session_state["_flash_fail"] = (
                                f"Fax to {recv_fax_number} failed ({_friendly_status(result, 'Failed')})."
                            )
                        else:
                            st.session_state["_flash_sent"] = (
                                f"Fax accepted by SRFax for {recv_fax_number}; still sending — check Sent faxes below."
                            )
                except Exception as send_err:
                    st.session_state["_flash_fail"] = f"{_short_reason(send_err)} — fax not sent."
            pdf_bytes = None
    if _attempted:
        st.session_state["_clear_after_send"] = True
        import time as _t

        _t.sleep(1.5)  # let the message show briefly
        st.rerun()

# ========== SENT FAXES (no-response tracking) ==========
with st.expander("📋 Sent faxes", expanded=False):
    if st.toggle("Show sent faxes & non-responders", key="show_fax_log"):
        try:
            # Ask SRFax about pending deliveries at most every 10 minutes per session.
            import time as _time

            if _time.time() - st.session_state.get("_fax_sync_at", 0) > 600:
                st.session_state["_fax_sync_at"] = _time.time()
                try:
                    sync_delivery_results(lambda fid: get_fax_status(st.secrets, fid))
                except Exception:
                    pass  # delivery check is a bonus; never break the list
            log_rows = read_fax_log()
        except Exception:
            log_rows = None
            st.warning("Couldn't load the Sent faxes log right now. Please try again in a minute.")

        if log_rows is not None:
            if st.session_state.pop("_flash_received", False):
                st.success("Marked as received.")
            _m = st.session_state.pop("_flash_resent", "")
            if _m:
                st.success(_m)
            _m = st.session_state.pop("_flash_resent_fail", "")
            if _m:
                st.error(_m)
            recent = list(reversed(log_rows))[:30]
            if not recent:
                st.caption("No faxes logged yet.")
            st.caption("Newest first. 'No response' = still waiting after 3 days.")
            badge = {
                "waiting": "⏳ waiting",
                "no response": "🔴 no response",
                "received": "✅ received",
                "failed": "❌ failed",
            }
            for r in recent:
                shown = display_status(r)
                delivery = r.get("delivery_result") or ""
                st.markdown(f"**{r.get('to_pharmacy') or '(no name)'}** — {badge.get(shown, shown)}")
                st.caption(
                    " · ".join(
                        x
                        for x in [
                            f"Sent {r.get('sent_at')}",
                            f"Fax {r.get('to_fax')}" if r.get("to_fax") else "",
                            f"Delivery: {delivery}" if delivery else "",
                        ]
                        if x
                    )
                )
                lid = r.get("log_id")
                if r.get("resend_count") not in (None, "", "0"):
                    st.caption(f"Resent {r.get('resend_count')}× · last sent {r.get('last_sent_at')}")
                if shown != "received" and lid:
                    if is_deleted(r):
                        st.caption("Resend: expired (fax copy deleted from SRFax after 7 days)")
                    elif r.get("srfax_id"):
                        if st.session_state.get("_confirm_resend") == lid:
                            st.warning(f"Resend this fax to {r.get('to_fax')}?")
                            c1, c2 = st.columns(2)
                            if c1.button("Yes, resend", key=f"resend_yes_{lid}", type="primary", use_container_width=True):
                                st.session_state.pop("_confirm_resend", None)
                                try:
                                    with st.spinner("Resending with SRFax..."):
                                        _pdf = retrieve_sent_fax_pdf(st.secrets, r["srfax_id"])
                                        try:
                                            new_id = queue_fax(st.secrets, r.get("to_fax") or "", _pdf, filename="transfer.pdf")
                                        finally:
                                            _pdf = None  # memory only, dropped right away
                                    try:
                                        record_resend(lid, new_id)
                                    except Exception:
                                        pass
                                    st.session_state["_flash_resent"] = "Resent. Delivery status will update in a few minutes."
                                except Exception as rs_err:
                                    st.session_state["_flash_resent_fail"] = f"{_short_reason(rs_err)} — not resent."
                                st.rerun()
                            if c2.button("Cancel", key=f"resend_no_{lid}", use_container_width=True):
                                st.session_state.pop("_confirm_resend", None)
                                st.rerun()
                        elif st.button("Resend", key=f"resend_{lid}", use_container_width=True):
                            st.session_state["_confirm_resend"] = lid
                            st.rerun()
                if shown in ("waiting", "no response") and lid:
                    if st.button("Received", key=f"recv_{lid}", use_container_width=True):
                        try:
                            mark_fax_received(lid)
                            st.session_state["_flash_received"] = True
                            st.rerun()
                        except Exception:
                            st.error("Sorry, couldn't update that fax right now. Please try again.")

            st.markdown("**Non-responders**")
            report = non_responders(log_rows)
            if report:
                st.caption(
                    "Delivery failed = SRFax couldn't deliver (fax number may be wrong). "
                    "No response = delivered, but nothing back after 3 days."
                )
                st.dataframe(report, hide_index=True, use_container_width=True)
            else:
                st.caption("No non-responders right now.")

st.caption("Directory is a shared Google Sheet. App can add new pharmacies only — no edit/delete.")


# Numeric keypad on phones for number fields (display only; values unchanged).
import streamlit.components.v1 as _components

_components.html(
    """<script>
(function(){
  const doc = window.parent.document;
  function fix(){
    doc.querySelectorAll('input[type="text"], input:not([type])').forEach(function(el){
      const l = (el.getAttribute('aria-label') || '').toLowerCase();
      let mode = null;
      if ((l.includes('phone') || l.includes('fax') || l === 'zip' || l.includes('date of birth'))
          && !l.includes('title') && !l.includes('search text')) {
        mode = 'tel';  // tel keypad also has / and - for dates
      } else if (l.startsWith('store #') || l.includes('rx number') || l.includes('quantity')) {
        mode = 'numeric';
      }
      if (mode && el.getAttribute('inputmode') !== mode) {
        el.setAttribute('inputmode', mode);
      }
    });
  }
  fix();
  new MutationObserver(fix).observe(doc.body, {childList: true, subtree: true});
})();
</script>""",
    height=0,
)

# ========== SEND FEEDBACK ==========
with st.expander("💬 Send feedback"):
    st.warning("Please don't include patient names, DOBs, or Rx details.")
    with st.form("feedback_form", clear_on_submit=True):
        fb_category = st.selectbox("Category", ["Bug", "Idea", "Directory fix"])
        fb_message = st.text_area("Message", max_chars=2000, placeholder="What should we fix or add?")
        fb_submitted = st.form_submit_button("Send feedback", use_container_width=True)
    if fb_submitted:
        if not (fb_message or "").strip():
            st.error("Please type a message first.")
        else:
            try:
                add_feedback(fb_category, fb_message, user=_current_user_email())
                st.success("Thank you! Your feedback was sent.")
            except Exception:
                st.error("Sorry, your feedback couldn't be saved right now. Please try again in a minute.")
    
