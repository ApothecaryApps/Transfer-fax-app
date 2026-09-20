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


def _client():
    raw = st.secrets["GCP_SERVICE_ACCOUNT"]
    info = json.loads(raw) if isinstance(raw, str) else dict(raw)
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)


def get_worksheet():
    gc = _client()
    sh = gc.open_by_key(st.secrets["SHEET_ID"])
    ws = sh.sheet1
    first = ws.row_values(1)
    if not first:
        ws.append_row(HEADERS, value_input_option="USER_ENTERED")
    return ws


def load_pharmacies():
    ws = get_worksheet()
    rows = ws.get_all_records()
    out = []
    for r in rows:
        out.append({k: str(r.get(k, "") or "").strip() for k in HEADERS})
    return out


def search_pharmacies(query: str = "", store_number: str = "", city: str = "", state: str = "", zip_code: str = "", phone: str = ""):
    rows = load_pharmacies()
    q = (query or "").strip().lower()
    sn = (store_number or "").strip().lower()
    city_q = (city or "").strip().lower()
    state_q = (state or "").strip().lower()
    zip_q = digits_only(zip_code)
    phone_q = digits_only(phone)

    hits = []
    for r in rows:
        if not (r.get("name") and r.get("fax")):
            continue
        if sn and sn not in (r.get("store_number") or "").lower():
            continue
        if city_q and city_q not in (r.get("city") or "").lower():
            continue
        if state_q and state_q not in (r.get("state") or "").lower():
            continue
        if zip_q and zip_q not in digits_only(r.get("zip") or ""):
            continue
        if phone_q and phone_q not in digits_only(r.get("phone") or ""):
            continue
        if q:
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
            if q not in blob:
                continue
        hits.append(r)
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

    existing = load_pharmacies()
    for r in existing:
        if digits_only(r.get("fax") or "") == fax and (r.get("name") or "").strip().lower() == name.lower():
            raise ValueError("That pharmacy (same name + fax) is already in the list")

    ws = get_worksheet()
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
