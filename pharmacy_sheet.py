import json
import re
from datetime import datetime, timedelta, timezone

import gspread
import streamlit as st
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADERS = [
    "name",
    "store_number",
    "address",
    "city",
    "state",
    "zip",
    "phone",
    "fax",
    "added_by",
    "added_at",
]


def digits_only(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _service_account_info():
    if "GCP_SERVICE_ACCOUNT" not in st.secrets:
        raise ValueError(
            "Missing GCP_SERVICE_ACCOUNT in Streamlit Secrets. "
            "Add the full JSON between triple quotes."
        )
    raw = st.secrets["GCP_SERVICE_ACCOUNT"]
    if raw is None:
        raise ValueError("GCP_SERVICE_ACCOUNT is empty")
    # Already a mapping (nested TOML table)
    if not isinstance(raw, str):
        return dict(raw)
    text = raw.strip()
    if not text:
        raise ValueError("GCP_SERVICE_ACCOUNT is blank")
    if not (text.startswith("{") and text.endswith("}")):
        raise ValueError(
            "GCP_SERVICE_ACCOUNT should be the full JSON object starting with { and ending with }"
        )
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(
            "GCP_SERVICE_ACCOUNT JSON is damaged or incomplete. "
            "Re-copy the key file into Secrets between triple quotes."
        ) from e


@st.cache_resource(show_spinner=False)
def _client():
    # Built once per server process and reused (saves re-authorizing on every search).
    info = _service_account_info()
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)


def get_worksheet():
    if "SHEET_ID" not in st.secrets:
        raise ValueError("Missing SHEET_ID in Streamlit Secrets")
    gc = _client()
    sh = gc.open_by_key(st.secrets["SHEET_ID"])
    ws = sh.sheet1
    first = ws.row_values(1)
    if not first:
        ws.append_row(HEADERS, value_input_option="USER_ENTERED")
    return ws


# How long the directory stays cached before it is re-read from the Google Sheet.
CACHE_TTL_SECONDS = 600  # 10 minutes


def _read_rows(ws=None):
    """Fresh (uncached) read of every row in the sheet."""
    if ws is None:
        ws = get_worksheet()
    rows = ws.get_all_records()
    out = []
    for r in rows:
        out.append({k: str(r.get(k, "") or "").strip() for k in HEADERS})
    return out


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _load_directory():
    """Cached copy of the sheet plus a small search index.

    Returns (rows, index, state_map):
      rows      - list of row dicts (same shape load_pharmacies always returned)
      index     - one tuple per searchable row (has name and fax), in sheet order:
                  (row_pos, store_lower, city_lower, state_lower, zip_digits, phone_digits, blob_lower)
      state_map - state_lower -> list of positions in index (in sheet order)
    """
    rows = _read_rows()
    index = []
    state_map = {}
    for i, r in enumerate(rows):
        if not (r.get("name") and r.get("fax")):
            continue
        blob = " ".join(
            [
                r.get("name") or "",
                r.get("store_number") or "",
                r.get("address") or "",
                r.get("city") or "",
                r.get("state") or "",
                r.get("zip") or "",
                r.get("phone") or "",
                r.get("fax") or "",
            ]
        ).lower()
        state_l = (r.get("state") or "").lower()
        state_map.setdefault(state_l, []).append(len(index))
        index.append(
            (
                i,
                (r.get("store_number") or "").lower(),
                (r.get("city") or "").lower(),
                state_l,
                digits_only(r.get("zip") or ""),
                digits_only(r.get("phone") or ""),
                blob,
            )
        )
    return rows, index, state_map


def clear_pharmacy_cache():
    """Forget the cached directory so the next search re-reads the sheet."""
    _load_directory.clear()


def load_pharmacies():
    rows, _index, _state_map = _load_directory()
    return rows


def search_pharmacies(query: str = "", store_number: str = "", city: str = "", state: str = "", zip_code: str = "", phone: str = ""):
    rows, index, state_map = _load_directory()
    q = (query or "").strip().lower()
    sn = (store_number or "").strip().lower()
    city_q = (city or "").strip().lower()
    state_q = (state or "").strip().lower()
    zip_q = digits_only(zip_code)
    phone_q = digits_only(phone)

    # Narrow by state first (same "contains" rule as before, e.g. "az" matches "AZ").
    if state_q:
        keys = [k for k in state_map if state_q in k]
        if len(keys) == 1:
            candidates = state_map[keys[0]]
        else:
            candidates = sorted(pos for k in keys for pos in state_map[k])
        entries = (index[pos] for pos in candidates)
    else:
        entries = index

    hits = []
    for i, r_sn, r_city, _r_state, r_zip, r_phone, blob in entries:
        if sn and sn not in r_sn:
            continue
        if city_q and city_q not in r_city:
            continue
        if zip_q and zip_q not in r_zip:
            continue
        if phone_q and phone_q not in r_phone:
            continue
        if q and q not in blob:
            continue
        hits.append(rows[i])
    return hits


def add_pharmacy(
    name: str,
    fax: str,
    store_number: str = "",
    address: str = "",
    city: str = "",
    state: str = "",
    zip_code: str = "",
    phone: str = "",
    added_by: str = "",
):
    name = (name or "").strip()
    fax = digits_only(fax)
    if not name or not fax:
        raise ValueError("Name and fax are required")
    if len(fax) not in (10, 11):
        raise ValueError("Fax should be 10 digits (US)")

    # Fresh read (not the cache) so the duplicate check sees rows added in the last few minutes.
    ws = get_worksheet()
    existing = _read_rows(ws)
    for r in existing:
        if digits_only(r.get("fax") or "") == fax and (r.get("name") or "").strip().lower() == name.lower():
            raise ValueError("That pharmacy (same name + fax) is already in the list")

    ws.append_row(
        [
            name,
            (store_number or "").strip(),
            (address or "").strip(),
            (city or "").strip(),
            (state or "").strip().upper(),
            digits_only(zip_code)[:5],
            digits_only(phone),
            fax[-10:] if len(fax) == 11 and fax.startswith("1") else fax,
            (added_by or "").strip(),
            datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        ],
        value_input_option="USER_ENTERED",
    )
    # New row saved: drop the cached directory so the next search shows it right away.
    clear_pharmacy_cache()


# ---------- Feedback box ----------
# Suggestions go to a separate "Feedback" tab. This never touches Sheet1 or the directory cache.
FEEDBACK_TAB = "Feedback"
FEEDBACK_HEADERS = ["timestamp", "user", "category", "message", "status"]


def _phoenix_now():
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("America/Phoenix"))
    except Exception:
        # Arizona has no daylight saving time, so UTC-7 is always correct.
        return datetime.now(timezone(timedelta(hours=-7)))


def add_feedback(category: str, message: str, user: str = ""):
    message = (message or "").strip()
    if not message:
        raise ValueError("Please type a message first.")
    if "SHEET_ID" not in st.secrets:
        raise ValueError("Missing SHEET_ID in Streamlit Secrets")
    sh = _client().open_by_key(st.secrets["SHEET_ID"])
    try:
        ws = sh.worksheet(FEEDBACK_TAB)
    except gspread.exceptions.WorksheetNotFound:
        # Safety net: create the tab (placed after Sheet1) if someone deleted it.
        ws = sh.add_worksheet(title=FEEDBACK_TAB, rows=1000, cols=len(FEEDBACK_HEADERS), index=1)
        ws.append_row(FEEDBACK_HEADERS, value_input_option="RAW")
    ws.append_row(
        [
            _phoenix_now().strftime("%Y-%m-%d %H:%M MST"),
            (user or "unknown").strip() or "unknown",
            (category or "").strip(),
            message,
            "new",
        ],
        # RAW = saved exactly as typed (a message starting with "=" is not run as a formula).
        value_input_option="RAW",
            )
    


# ---------- Sent-fax log (no-response tracking) ----------
# Lives on its own "FaxLog" tab. Never touches Sheet1 or the directory cache.
# NO patient info is ever written here: only receiving pharmacy, fax number, time, sender, SRFax id/result.
FAXLOG_TAB = "FaxLog"
FAXLOG_HEADERS = [
    "log_id",
    "sent_at",
    "sent_by",
    "to_pharmacy",
    "to_fax",
    "srfax_id",
    "delivery_result",
    "status",
    "status_updated_at",
    "note",
]
NO_RESPONSE_DAYS = 3
_PHX = timezone(timedelta(hours=-7))  # Arizona: no daylight saving time


def _faxlog_ws():
    if "SHEET_ID" not in st.secrets:
        raise ValueError("Missing SHEET_ID in Streamlit Secrets")
    sh = _client().open_by_key(st.secrets["SHEET_ID"])
    try:
        return sh.worksheet(FAXLOG_TAB)
    except gspread.exceptions.WorksheetNotFound:
        # Safety net if the tab was deleted: recreate it after Sheet1.
        ws = sh.add_worksheet(title=FAXLOG_TAB, rows=1000, cols=len(FAXLOG_HEADERS), index=1)
        ws.append_row(FAXLOG_HEADERS, value_input_option="RAW")
        return ws


def _phx_stamp():
    return _phoenix_now().strftime("%Y-%m-%d %H:%M")


def _fax10(fax):
    d = digits_only(fax)
    return d[-10:] if len(d) == 11 and d.startswith("1") else d


def log_fax(to_pharmacy, to_fax, sent_by="", srfax_id="", delivery_result="pending", status="waiting", note=""):
    """Add one row to FaxLog. Returns the new log_id."""
    import uuid

    log_id = uuid.uuid4().hex[:8]
    _faxlog_ws().append_row(
        [
            log_id,
            _phx_stamp(),
            (sent_by or "unknown").strip() or "unknown",
            (to_pharmacy or "").strip(),
            _fax10(to_fax),
            str(srfax_id or ""),
            delivery_result,
            status,
            _phx_stamp(),
            (note or "")[:150],
        ],
        value_input_option="RAW",
    )
    clear_fax_log_cache()
    return log_id


def _row_number(ws, log_id):
    ids = ws.col_values(1)
    for i, v in enumerate(ids):
        if str(v).strip() == str(log_id):
            return i + 1  # sheet rows are 1-based
    raise ValueError("That fax is no longer in the log")


def _set_cells(ws, row, updates):
    """updates: {"status": "...", ...} -> written in one call. status_updated_at set automatically."""
    updates = dict(updates)
    if "status" in updates:
        updates["status_updated_at"] = _phx_stamp()
    data = []
    for key, val in updates.items():
        col = chr(ord("A") + FAXLOG_HEADERS.index(key))
        data.append({"range": f"{col}{row}", "values": [[val]]})
    ws.batch_update(data, value_input_option="RAW")


def update_fax_log(log_id, **updates):
    ws = _faxlog_ws()
    _set_cells(ws, _row_number(ws, log_id), updates)
    clear_fax_log_cache()


def mark_fax_received(log_id):
    update_fax_log(log_id, status="received")


def _read_fax_log_fresh(ws=None):
    ws = ws or _faxlog_ws()
    out = []
    for i, r in enumerate(ws.get_all_records()):
        row = {k: str(r.get(k, "") or "").strip() for k in FAXLOG_HEADERS}
        row["_row"] = i + 2  # header is row 1
        out.append(row)
    return out


@st.cache_data(ttl=60, show_spinner=False)
def read_fax_log():
    return _read_fax_log_fresh()


def clear_fax_log_cache():
    read_fax_log.clear()


def _parse_phx(stamp):
    try:
        return datetime.strptime(stamp[:16], "%Y-%m-%d %H:%M").replace(tzinfo=_PHX)
    except Exception:
        return None


def display_status(row, now=None):
    """What the app shows. 'waiting' older than 3 days shows as 'no response' (the sheet keeps 'waiting')."""
    status = (row.get("status") or "").lower()
    if status == "waiting":
        sent = _parse_phx(row.get("sent_at") or "")
        now = now or datetime.now(_PHX)
        if sent and now - sent >= timedelta(days=NO_RESPONSE_DAYS):
            return "no response"
    return status or "unknown"


def srfax_to_delivery(result):
    """Map an SRFax Get_FaxStatus result to 'delivered' / 'failed' / None (still in progress)."""
    if isinstance(result, list):
        result = result[0] if result else {}
    sent = (result or {}).get("SentStatus") if isinstance(result, dict) else None
    if sent == "Sent":
        return "delivered"
    if sent == "Failed":
        return "failed"
    return None


def sync_delivery_results(get_status, max_checks=10, max_age_days=14):
    """Ask SRFax about 'waiting' rows whose delivery is still pending. Returns how many rows changed.

    get_status(srfax_id) -> SRFax result (the existing srfax.get_fax_status, wrapped).
    """
    ws = _faxlog_ws()
    now = datetime.now(_PHX)
    changed = checked = 0
    for row in _read_fax_log_fresh(ws):
        if checked >= max_checks:
            break
        if row["status"].lower() != "waiting" or not row["srfax_id"]:
            continue
        if row["delivery_result"].lower() not in ("", "pending"):
            continue
        sent = _parse_phx(row["sent_at"])
        if sent and now - sent > timedelta(days=max_age_days):
            continue
        checked += 1
        try:
            delivery = srfax_to_delivery(get_status(row["srfax_id"]))
        except Exception:
            continue
        if delivery == "delivered":
            _set_cells(ws, row["_row"], {"delivery_result": "delivered"})
            changed += 1
        elif delivery == "failed":
            _set_cells(ws, row["_row"], {"delivery_result": "failed", "status": "failed"})
            changed += 1
    if changed:
        clear_fax_log_cache()
    return changed


def non_responders(rows, now=None):
    """Pharmacies ranked by unanswered faxes, split into delivery-failed vs delivered-but-no-response."""
    groups = {}
    for r in rows:
        delivery = r.get("delivery_result", "").lower()
        shown = display_status(r, now)
        failed = delivery == "failed"
        no_resp = shown == "no response"
        if not (failed or no_resp):
            continue
        key = (r.get("to_pharmacy", ""), r.get("to_fax", ""))
        g = groups.setdefault(key, {"Pharmacy": key[0], "Fax": key[1], "Delivery failed": 0, "No response": 0})
        if failed:
            g["Delivery failed"] += 1
        else:
            g["No response"] += 1
    out = list(groups.values())
    for g in out:
        g["Total"] = g["Delivery failed"] + g["No response"]
    out.sort(key=lambda g: (-g["Total"], -g["Delivery failed"], g["Pharmacy"].lower()))
    return out
    
