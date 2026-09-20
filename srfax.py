import base64
import time
import requests

SRFAX_URL = "https://www.srfax.com/SRF_SecWebSvc.php"


def _srfax_creds(secrets):
    return {
        "access_id": str(secrets["SRFAX_ACCESS_ID"]),
        "access_pwd": str(secrets["SRFAX_ACCESS_PWD"]),
        "sCallerID": str(secrets["SRFAX_CALLER_ID"]).replace("-", "").replace(" ", "")[-10:],
        "sSenderEmail": str(secrets["SRFAX_SENDER_EMAIL"]),
    }


def queue_fax(secrets, to_fax_number: str, pdf_bytes: bytes, filename: str = "transfer.pdf"):
    to_digits = "".join(c for c in to_fax_number if c.isdigit())
    if len(to_digits) == 10:
        to_digits = "1" + to_digits
    if len(to_digits) != 11:
        raise ValueError(f"Need 11-digit destination fax, got {to_digits!r}")

    creds = _srfax_creds(secrets)
    payload = {
        "action": "Queue_Fax",
        "access_id": creds["access_id"],
        "access_pwd": creds["access_pwd"],
        "sCallerID": creds["sCallerID"],
        "sSenderEmail": creds["sSenderEmail"],
        "sFaxType": "SINGLE",
        "sToFaxNumber": to_digits,
        "sResponseFormat": "JSON",
        "sFileName_1": filename,
        "sFileContent_1": base64.b64encode(pdf_bytes).decode("ascii"),
    }
    r = requests.post(SRFAX_URL, data=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    if data.get("Status") != "Success":
        raise RuntimeError(f"Queue_Fax failed: {data}")
    return str(data["Result"])


def get_fax_status(secrets, fax_details_id: str):
    creds = _srfax_creds(secrets)
    payload = {
        "action": "Get_FaxStatus",
        "access_id": creds["access_id"],
        "access_pwd": creds["access_pwd"],
        "sFaxDetailsID": str(fax_details_id),
        "sResponseFormat": "JSON",
    }
    r = requests.post(SRFAX_URL, data=payload, timeout=30)
    r.raise_for_status()
    data = r.json()
    if data.get("Status") != "Success":
        raise RuntimeError(f"Get_FaxStatus failed: {data}")
    return data["Result"]


def wait_for_fax(secrets, fax_details_id: str, timeout_sec: int = 300, poll_every: int = 10):
    deadline = time.time() + timeout_sec
    last = None
    while time.time() < deadline:
        last = get_fax_status(secrets, fax_details_id)
        status = last.get("SentStatus") if isinstance(last, dict) else None
        if isinstance(last, list) and last:
            status = last[0].get("SentStatus")
        if status in ("Sent", "Failed"):
            return last
        time.sleep(poll_every)
    return last
