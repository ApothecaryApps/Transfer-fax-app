import json
import re
from datetime import datetime, timezone

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
