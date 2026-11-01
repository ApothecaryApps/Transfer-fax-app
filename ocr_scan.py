"""Best-effort OCR for bottle labels / transfer forms. Images are processed in memory only."""
import io
import re

DATE_RE = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\b")
RX_RE = re.compile(r"\bR\s*X\s*(?:#|NO\.?|NUM(?:BER)?)?\s*[:#]?\s*([0-9][0-9\-]{4,})", re.I)
NAME_RE = re.compile(r"\b(?:PATIENT(?:\s+NAME)?|PT|NAME)\s*[:\-]\s*([A-Z][A-Z ,.'\-]{2,40})", re.I)
DOB_RE = re.compile(r"\b(?:DOB|D\.O\.B\.?|BIRTH(?:\s*DATE)?|DATE\s+OF\s+BIRTH)\s*[:\-]?\s*(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})", re.I)


def ocr_available():
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def image_to_text(data: bytes) -> str:
    import pytesseract
    from PIL import Image, ImageOps
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img).convert("L")
    if max(img.size) < 1500:
        s = 1500 / max(img.size)
        img = img.resize((int(img.width * s), int(img.height * s)))
    return pytesseract.image_to_string(img)


def _fmt_date(s):
    m = DATE_RE.search(s)
    if not m:
        return ""
    mo, d, y = m.groups()
    if len(y) == 2:
        y = ("19" if int(y) > 30 else "20") + y
    return f"{int(mo):02d}/{int(d):02d}/{y}"


def parse_fields(text: str) -> dict:
    out = {"name": "", "dob": "", "rx": []}
    m = DOB_RE.search(text)
    if m:
        out["dob"] = _fmt_date(m.group(1))
    m = NAME_RE.search(text)
    if m:
        out["name"] = re.sub(r"\s+", " ", m.group(1)).strip(" ,.-").title()
    seen = []
    for r in RX_RE.findall(text):
        r = r.strip("-")
        if r not in seen:
            seen.append(r)
    out["rx"] = seen[:10]
    return out
