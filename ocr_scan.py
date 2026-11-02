"""Best-effort OCR for bottle labels / transfer forms. Images are processed in memory only."""
import io
import re

DATE_RE = re.compile(r"\b(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{2,4})\b")
BIRTH_WORDS = re.compile(r"\b(DOB|D\.?O\.?B|BIRTH|BORN|BDAY|B/D)\b", re.I)
FILL_WORDS = re.compile(r"\b(FILL|FILLED|DATE\s*FILLED|DISCARD|EXP|EXPIRE|USE\s*BY|BEYOND|ORIG|WRITTEN|DATE)\b", re.I)
RX_LABELED = re.compile(
    r"(?:\bR\s*[Xx]\b|\bRX\b|PRESCRIPTION|SCRIPT|RX\s*NO)\s*(?:#|NO\.?|NUM(?:BER)?)?\s*[:#.]?\s*([0-9][0-9\- ]{4,11}[0-9])",
    re.I,
)
RX_HASH = re.compile(r"#\s*([0-9]{6,8})\b")
NAME_LABELED = re.compile(r"\b(?:PATIENT(?:\s+NAME)?|PT\.?|NAME|FOR)\s*[:\-]\s*([A-Za-z][A-Za-z ,.'\-]{2,40})", re.I)

BOILER = re.compile(
    r"PHARMACY|DRUG|WALGREEN|CVS|WALMART|SAFEWAY|FRY|KROGER|COSTCO|TARGET|RITE|STORE|"
    r"\bDR\b|\bMD\b|DOCTOR|PRESCRIBER|TAKE|TABLET|CAPSULE|\bTAB\b|\bCAP\b|\bMG\b|\bML\b|DAILY|"
    r"MOUTH|REFILL|QTY|QUANTITY|CAUTION|FEDERAL|LAW|TRANSFER|WARNING|USE|BEFORE|AFTER|"
    r"STREET|\bST\b|\bAVE\b|\bRD\b|\bBLVD\b|SUITE|PHONE|FAX|\bAZ\b|DATE|GENERIC|SUBSTITUTE|"
    r"\bNDC\b|\bLOT\b|EXP|DISCARD|MFG|MANUFACTURER|REQUEST|FORM|PHARMACIST|TECH",
    re.I,
)


def ocr_available():
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _variants(data):
    from PIL import Image, ImageOps, ImageFilter
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img).convert("L")
    m = max(img.size)
    if m < 2000:
        s = 2000 / m
        img = img.resize((int(img.width * s), int(img.height * s)))
    elif m > 3500:
        s = 3500 / m
        img = img.resize((int(img.width * s), int(img.height * s)))
    ac = ImageOps.autocontrast(img, cutoff=2).filter(ImageFilter.SHARPEN)
    yield ac
    yield ac.point(lambda p: 255 if p > 140 else 0)


def image_to_text(data: bytes) -> str:
    """Try a few preprocess + page-segmentation combos; keep the longest useful text."""
    import pytesseract
    best = ""
    for im in _variants(data):
        for psm in (6, 4):
            try:
                t = pytesseract.image_to_string(im, config=f"--psm {psm}")
            except Exception:
                continue
            score = len(re.findall(r"[A-Za-z0-9]", t))
            if score > len(re.findall(r"[A-Za-z0-9]", best)):
                best = t
    return best


def _fmt(mo, d, y):
    mo, d = int(mo), int(d)
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return ""
    if len(y) == 2:
        y = ("19" if int(y) > 30 else "20") + y
    if len(y) != 4:
        return ""
    return f"{mo:02d}/{d:02d}/{y}"


def _find_dob(lines):
    cands = []  # (score, date)
    for i, ln in enumerate(lines):
        for m in DATE_RE.finditer(ln):
            v = _fmt(*m.groups())
            if not v:
                continue
            yr = int(v[-4:])
            near = " ".join(lines[max(0, i - 1): i + 1])
            sc = 0
            if BIRTH_WORDS.search(ln) or BIRTH_WORDS.search(near):
                sc += 10
            if FILL_WORDS.search(ln) and not BIRTH_WORDS.search(ln):
                sc -= 5
            if yr <= 2020:
                sc += 3  # birth dates are older than fill dates
            if yr >= 2023:
                sc -= 3
            cands.append((sc, v))
    cands = [c for c in cands if c[0] > 0]
    return max(cands)[1] if cands else ""


def _clean_name(s):
    s = re.sub(r"[^A-Za-z ,.'\-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" ,.-'")
    return s


def _find_name(text, lines):
    m = NAME_LABELED.search(text)
    if m:
        n = _clean_name(m.group(1))
        if len(n.split()) >= 2 and not BOILER.search(n):
            return n.title()
    for ln in lines[:12]:
        n = _clean_name(ln)
        words = n.replace(",", " ").split()
        if not (2 <= len(words) <= 4) or BOILER.search(n):
            continue
        if any(len(w) < 2 for w in words) or re.search(r"\d", ln):
            continue
        letters = sum(c.isalpha() for c in ln)
        if letters < 0.7 * len(ln.strip()):
            continue
        if n.isupper() or all(w[0].isupper() for w in words):
            if "," in n:  # LAST, FIRST
                last, first = [p.strip() for p in n.split(",", 1)]
                if first and last:
                    n = f"{first} {last}"
            return n.title()
    return ""


def _find_rx(text):
    out = []
    for r in RX_LABELED.findall(text) + RX_HASH.findall(text):
        r = re.sub(r"[\s\-]", "", r)
        if 5 <= len(r) <= 10 and r not in out:
            out.append(r)
    return out[:10]


def parse_fields(text: str) -> dict:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return {"name": _find_name(text, lines), "dob": _find_dob(lines), "rx": _find_rx(text)}


def _alnum(t):
    return len(re.findall(r"[A-Za-z0-9]", t or ""))


def vision_text(data: bytes) -> str:
    """Google Cloud Vision fallback using the existing Sheets service account (free tier 1,000/mo)."""
    import base64
    import requests
    from google.oauth2.service_account import Credentials
    from google.auth.transport.requests import Request
    import pharmacy_sheet
    creds = Credentials.from_service_account_info(
        pharmacy_sheet._service_account_info(),
        scopes=["https://www.googleapis.com/auth/cloud-vision"],
    )
    creds.refresh(Request())
    r = requests.post(
        "https://vision.googleapis.com/v1/images:annotate",
        headers={"Authorization": f"Bearer {creds.token}"},
        json={"requests": [{"image": {"content": base64.b64encode(data).decode()},
                            "features": [{"type": "DOCUMENT_TEXT_DETECTION"}]}]},
        timeout=30,
    )
    j = r.json() if r.content else {}
    if r.status_code != 200:
        msg = (j.get("error") or {}).get("message", str(r.status_code))
        raise RuntimeError(f"Vision {r.status_code}: {msg[:160]}")
    res = (j.get("responses") or [{}])[0]
    if res.get("error"):
        raise RuntimeError(f"Vision: {res['error'].get('message', '')[:160]}")
    return (res.get("fullTextAnnotation") or {}).get("text", "")


def read_image(data: bytes):
    """Return (text, engine, notes). Tesseract first; Vision if Tesseract missing or weak."""
    notes = []
    text = ""
    if ocr_available():
        try:
            text = image_to_text(data)
        except Exception as e:
            notes.append(f"Tesseract error: {type(e).__name__}")
    else:
        notes.append("Tesseract not installed on server")
    if _alnum(text) >= 25:
        return text, "Tesseract", notes
    try:
        vt = vision_text(data)
        if _alnum(vt) >= _alnum(text):
            return vt, "Google Vision", notes
    except Exception as e:
        notes.append(str(e)[:200] if isinstance(e, RuntimeError) else f"Vision error: {type(e).__name__}")
    return text, "Tesseract" if text else "none", notes
