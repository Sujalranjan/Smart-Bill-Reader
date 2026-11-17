"""Turn OCR text into clean values: numbers, ISO dates, GSTINs, and the bill schema.

Every bill stored by the server (schema_version 2) has this shape:

    {
      "schema_version": 2,
      "header":  {invoice_id, invoice_date (YYYY-MM-DD), due_date, supplier_name,
                  supplier_address, supplier_gstin, supplier_phone, supplier_email,
                  buyer_name, buyer_gstin, purchase_order, payment_terms},
      "totals":  {sub_total, cgst_amount, sgst_amount, igst_amount, total_tax,
                  total_amount}                     # floats or None
      "line_items": [{description, hsn_sac, quantity, rate, discount_pct,
                      cgst_pct, cgst_amount, sgst_pct, sgst_amount, amount}],
      "confidence": {field: 0..1},                  # OCR confidence, header/totals only
      "raw": {field: original OCR text},            # kept for auditing
      ...status / issues / file fields added by the app
    }
"""
import re
from datetime import date, datetime

SCHEMA_VERSION = 2

HEADER_FIELDS = [
    "invoice_id", "invoice_date", "due_date",
    "supplier_name", "supplier_address", "supplier_gstin", "supplier_phone", "supplier_email",
    "buyer_name", "buyer_gstin", "purchase_order", "payment_terms",
]
DATE_FIELDS = {"invoice_date", "due_date"}
TOTAL_FIELDS = ["sub_total", "cgst_amount", "sgst_amount", "igst_amount", "total_tax", "total_amount"]
LINE_TEXT_FIELDS = ["description", "hsn_sac"]
LINE_NUMBER_FIELDS = ["quantity", "rate", "discount_pct", "cgst_pct", "cgst_amount",
                      "sgst_pct", "sgst_amount", "amount"]
LINE_FIELDS = LINE_TEXT_FIELDS + LINE_NUMBER_FIELDS

# Document AI entity types (custom processor and the standard Invoice Parser) -> our fields.
HEADER_ALIASES = {
    "invoice_id": ["invoice_id", "invoice_number", "invoice_no"],
    "invoice_date": ["invoice_date"],
    "due_date": ["due_date"],
    "supplier_name": ["supplier_name", "vendor_name"],
    "supplier_address": ["supplier_address", "vendor_address"],
    "supplier_gstin": ["supplier_gst_number", "supplier_gstin", "supplier_tax_id"],
    "supplier_phone": ["supplier_phone"],
    "supplier_email": ["supplier_email"],
    "buyer_name": ["receiver_name", "buyer_name"],
    "buyer_gstin": ["receiver_gst_number", "receiver_tax_id", "buyer_gstin"],
    "purchase_order": ["purchase_order", "po_number"],
    "payment_terms": ["payment_terms"],
}
TOTAL_ALIASES = {
    "sub_total": ["sub_total", "net_amount", "subtotal"],
    "cgst_amount": ["cgst_amount", "total_cgst"],
    "sgst_amount": ["sgst_amount", "total_sgst"],
    "igst_amount": ["igst_amount", "total_igst"],
    "total_tax": ["total_gst_amount", "total_tax_amount", "tax_amount"],
    "total_amount": ["total_amount", "grand_total"],
}
LINE_ALIASES = {
    "description": ["description"],
    "hsn_sac": ["product_code", "hsn_sac", "hsn"],
    "quantity": ["quantity"],
    "rate": ["unit_price", "rate"],
    "discount_pct": ["discount"],
    "cgst_pct": ["cgst"],
    "cgst_amount": ["cgst_amount"],
    "sgst_pct": ["sgst"],
    "sgst_amount": ["sgst_amount"],
    "amount": ["amount"],
}

_NUMBER_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?|-?\.\d+")
_CURRENCY_RE = re.compile(r"(?i)\b(?:rs|inr)\b\.?|₹")


def clean_text(value):
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def parse_number(value):
    """'₹1,23,456.50' -> 123456.5, 'Rs. 500/-' -> 500.0, '(17.64)' -> -17.64, '9%' -> 9.0."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = _CURRENCY_RE.sub("", text)
    match = _NUMBER_RE.search(text.replace(" ", ""))
    if not match:
        return None
    try:
        number = float(match.group(0).replace(",", ""))
    except ValueError:
        return None
    return -abs(number) if negative else number


_DATE_FORMATS = [
    "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y", "%d.%m.%y",
    "%d-%b-%Y", "%d %b %Y", "%d-%b-%y", "%d %b %y", "%d %B %Y", "%d-%B-%Y",
    "%b %d %Y", "%B %d %Y", "%Y/%m/%d",
]


def parse_date(value):
    """Return YYYY-MM-DD, reading ambiguous dates day-first (Indian invoices)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = clean_text(value)
    if not text:
        return None
    # Drop a trailing time ("29/06/2025 20:54:54") and ordinal suffixes ("25th").
    text = re.sub(r"[ T]\d{1,2}:\d{2}(:\d{2})?\s*(AM|PM|am|pm)?$", "", text).strip()
    text = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", text)
    text = text.replace(",", " ").replace("'", " ")
    text = re.sub(r"\s+", " ", text).strip()
    for fmt in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt).date()
        except ValueError:
            continue
        if 2000 <= parsed.year <= 2100:
            return parsed.isoformat()
    return None


def is_iso_date(value):
    return isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is not None


_GSTIN_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_GSTIN_RE = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")


def clean_gstin(value):
    text = clean_text(value)
    if not text:
        return None
    return re.sub(r"[^0-9A-Za-z]", "", text).upper() or None


def is_valid_gstin(gstin):
    """Format check plus the official mod-36 check digit."""
    if not gstin or not _GSTIN_RE.match(gstin):
        return False
    total = 0
    for i, ch in enumerate(gstin[:14]):
        product = _GSTIN_CHARS.index(ch) * (1 if i % 2 == 0 else 2)
        total += product // 36 + product % 36
    check = (36 - total % 36) % 36
    return gstin[14] == _GSTIN_CHARS[check]


def duplicate_key(header):
    """Same invoice number from the same supplier => same key."""
    invoice = re.sub(r"[^0-9A-Za-z]", "", header.get("invoice_id") or "").upper()
    if not invoice:
        return None
    gstin = header.get("supplier_gstin")
    if gstin and is_valid_gstin(gstin):
        supplier = gstin
    else:
        supplier = re.sub(r"[^0-9a-z]", "", (header.get("supplier_name") or "").lower())
    return f"{supplier}|{invoice}" if supplier else None


# --- building the schema -------------------------------------------------------------

def _pick(entities, aliases):
    """First alias present in the extracted entities -> (entity dict, alias)."""
    for alias in aliases:
        if alias in entities and entities[alias].get("text"):
            return entities[alias]
    return None


def normalize_header_value(field, value):
    if field in DATE_FIELDS:
        return parse_date(value) or clean_text(value)
    if field in ("supplier_gstin", "buyer_gstin"):
        return clean_gstin(value)
    return clean_text(value)


def clean_location(value):
    """Keep a field position only if it is well formed: {"page": int >= 0, "box": [x0, y0, x1, y1]} in 0..1."""
    if not isinstance(value, dict):
        return None
    page, box = value.get("page"), value.get("box")
    if not isinstance(page, int) or isinstance(page, bool) or page < 0:
        return None
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return None
    try:
        x0, y0, x1, y1 = (float(v) for v in box)
    except (TypeError, ValueError):
        return None
    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
        return None
    return {"page": page, "box": [x0, y0, x1, y1]}


def line_is_empty(line):
    return all(line.get(f) is None for f in LINE_FIELDS)


def normalize_line_item(item):
    out = {}
    for field in LINE_TEXT_FIELDS:
        out[field] = clean_text(item.get(field))
    for field in LINE_NUMBER_FIELDS:
        out[field] = parse_number(item.get(field))
    location = clean_location(item.get("location"))
    if location:
        out["location"] = location  # where this row was read on the bill
    return out


def bill_from_extraction(extracted):
    """`extracted` is the output of extraction.extract_document()."""
    entities = extracted.get("entities", {})
    header, totals, confidence, raw, locations = {}, {}, {}, {}, {}

    for field, aliases in HEADER_ALIASES.items():
        entity = _pick(entities, aliases)
        header[field] = None
        if entity:
            raw[field] = entity["text"]
            confidence[field] = entity.get("confidence")
            locations[field] = clean_location(entity.get("location"))
            value = entity.get("normalized") if field in DATE_FIELDS and entity.get("normalized") else entity["text"]
            header[field] = normalize_header_value(field, value)

    for field, aliases in TOTAL_ALIASES.items():
        entity = _pick(entities, aliases)
        totals[field] = None
        if entity:
            raw[field] = entity["text"]
            confidence[field] = entity.get("confidence")
            locations[field] = clean_location(entity.get("location"))
            normalized = entity.get("normalized")
            totals[field] = normalized if isinstance(normalized, (int, float)) else parse_number(entity["text"])

    line_items = []
    for raw_item in extracted.get("line_items", []):
        item = {}
        for field, aliases in LINE_ALIASES.items():
            item[field] = next((raw_item[a] for a in aliases if raw_item.get(a)), None)
        item["location"] = raw_item.get("_location")
        line = normalize_line_item(item)
        # A single "GST %" column is split evenly into CGST and SGST.
        gst = parse_number(raw_item.get("gst"))
        if line["cgst_pct"] is None and line["sgst_pct"] is None and gst is not None:
            line["cgst_pct"] = line["sgst_pct"] = round(gst / 2, 4)
        if not line_is_empty(line):
            line_items.append(line)

    if totals["total_tax"] is None:
        parts = [totals[k] for k in ("cgst_amount", "sgst_amount", "igst_amount") if totals[k] is not None]
        if parts:
            totals["total_tax"] = round(sum(parts), 2)

    return {
        "schema_version": SCHEMA_VERSION,
        "header": header,
        "totals": totals,
        "line_items": line_items,
        "confidence": {k: v for k, v in confidence.items() if v is not None},
        "raw": raw,
        # where each header/total value was read on the bill, for highlighting in the review screen
        "locations": {k: v for k, v in locations.items() if v},
    }


_LEGACY_HEADER = {
    "invoice_id": "invoice_id", "invoice_date": "invoice_date", "due_date": "due_date",
    "supplier_name": "supplier_name", "supplier_address": "supplier_address",
    "supplier_gstin": "supplier_gst_number", "supplier_phone": "supplier_phone",
    "supplier_email": "supplier_email", "buyer_name": "receiver_name",
    "purchase_order": "purchase_order", "payment_terms": "payment_terms",
}
_LEGACY_TOTALS = {
    "sub_total": "sub_total", "cgst_amount": "cgst_amount", "sgst_amount": "sgst_amount",
    "igst_amount": "igst_amount", "total_tax": "total_gst_amount", "total_amount": "total_amount",
}
_LEGACY_LINE = {
    "description": "Item/Product Name", "hsn_sac": "HSN/SAC", "quantity": "Quantity",
    "rate": "Rate", "cgst_pct": "CGST %", "sgst_pct": "SGST %", "discount_pct": "Discount %",
    "amount": "Amount",
}


def bill_from_legacy(data):
    """Convert a bill saved by the first server version (flat OCR strings)."""
    header = {f: normalize_header_value(f, data.get(src)) for f, src in _LEGACY_HEADER.items()}
    header.setdefault("buyer_gstin", None)
    totals = {f: parse_number(data.get(src)) for f, src in _LEGACY_TOTALS.items()}
    line_items = [
        normalize_line_item({f: item.get(src) for f, src in _LEGACY_LINE.items()})
        for item in data.get("line_items", []) or []
    ]
    raw = {f: data[src] for f, src in {**_LEGACY_HEADER, **_LEGACY_TOTALS}.items() if data.get(src)}
    return {
        "schema_version": SCHEMA_VERSION,
        "header": header,
        "totals": totals,
        "line_items": line_items,
        "confidence": {},
        "raw": raw,
        "file_name": data.get("File_Name"),
    }


class InvalidValue(ValueError):
    def __init__(self, field, message):
        super().__init__(message)
        self.field = field
        self.message = message


def apply_edits(bill, edits):
    """Apply user corrections. Values may be strings (as typed) or numbers.

    Raises InvalidValue for text that can't be read as a number/date, so the user
    gets a precise message instead of silently losing the value.
    Returns the set of fields that changed.
    """
    changed = set()

    for field, value in (edits.get("header") or {}).items():
        if field not in HEADER_FIELDS:
            continue
        new = normalize_header_value(field, value)
        if field in DATE_FIELDS and new and not is_iso_date(new):
            raise InvalidValue(field, f"'{value}' is not a valid date. Use DD/MM/YYYY.")
        if new != bill["header"].get(field):
            bill["header"][field] = new
            changed.add(field)

    for field, value in (edits.get("totals") or {}).items():
        if field not in TOTAL_FIELDS:
            continue
        new = parse_number(value)
        if new is None and clean_text(value):
            raise InvalidValue(field, f"'{value}' is not a valid amount.")
        if new != bill["totals"].get(field):
            bill["totals"][field] = new
            changed.add(field)

    if "line_items" in edits and edits["line_items"] is not None:
        new_items = []
        for i, item in enumerate(edits["line_items"]):
            for field in LINE_NUMBER_FIELDS:
                value = item.get(field)
                if parse_number(value) is None and clean_text(value):
                    raise InvalidValue(f"line_items[{i}].{field}", f"Line {i + 1}: '{value}' is not a valid number.")
            line = normalize_line_item(item)
            if not line_is_empty(line):
                new_items.append(line)
        if new_items != bill["line_items"]:
            bill["line_items"] = new_items
            changed.add("line_items")

    # A value the user typed or confirmed no longer needs a low-confidence warning.
    for field in changed:
        bill.get("confidence", {}).pop(field, None)
    return changed
