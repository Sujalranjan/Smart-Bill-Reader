"""Vendor (supplier) master list.

Each user has `users/{uid}/vendors/{vendor_id}`:
    {name, name_key, gstin, address, phone, email, blocked, bill_ids, bill_count,
     first_seen, last_seen, source: "auto" | "manual"}

Vendors are added automatically when a bill is approved, and can be edited or
blocked by the user. Every scanned bill is checked against this list.
"""
import re
from difflib import SequenceMatcher

from normalize import clean_gstin, clean_text, is_valid_gstin

_LEGAL_WORDS = re.compile(
    r"\b(m/s|messrs|pvt|private|ltd|limited|llp|co|company|corp|corporation|inc|and|the|india|enterprises?|traders?)\b"
)


def name_key(name):
    """'M/s Metro Cash & Carry India Pvt. Ltd.' -> 'metrocashcarry'."""
    text = (name or "").lower()
    text = _LEGAL_WORDS.sub(" ", text.replace("&", " "))
    return re.sub(r"[^0-9a-z]", "", text)


def vendor_id(header):
    """Document id for a supplier: its GSTIN when valid, else its normalized name."""
    gstin = header.get("supplier_gstin")
    if gstin and is_valid_gstin(gstin):
        return gstin
    key = name_key(header.get("supplier_name"))
    return f"name-{key}" if key else None


def names_match(a, b):
    ka, kb = name_key(a), name_key(b)
    if not ka or not kb:
        return False
    if ka in kb or kb in ka:
        return True
    return SequenceMatcher(None, ka, kb).ratio() >= 0.75


def match_vendor(header, by_id, by_name):
    """Compare a bill's supplier with the master list.

    by_id:   the vendor stored under vendor_id(header), or None
    by_name: vendors whose name_key equals the bill's supplier name, possibly empty
    Returns {"status": ..., "vendor": vendor or None}; status is one of
      "unknown"         - bill has no usable supplier name/GSTIN
      "new"             - supplier not in the master list
      "match"           - known supplier, details agree
      "blocked"         - supplier is blocked by the user
      "name_mismatch"   - GSTIN known, but under a clearly different name
      "gstin_mismatch"  - name known, but the bill shows a different GSTIN
    """
    if not vendor_id(header):
        return {"status": "unknown", "vendor": None}

    vendor = by_id
    if vendor is None and by_name:
        vendor = by_name[0]
        bill_gstin = header.get("supplier_gstin")
        if vendor.get("gstin") and bill_gstin and vendor["gstin"] != bill_gstin:
            return {"status": "blocked" if vendor.get("blocked") else "gstin_mismatch", "vendor": vendor}
    if vendor is None:
        return {"status": "new", "vendor": None}
    if vendor.get("blocked"):
        return {"status": "blocked", "vendor": vendor}
    if header.get("supplier_name") and vendor.get("name") and not names_match(header["supplier_name"], vendor["name"]):
        return {"status": "name_mismatch", "vendor": vendor}
    return {"status": "match", "vendor": vendor}


def vendor_from_bill(header, bill_id, now):
    return {
        "name": clean_text(header.get("supplier_name")),
        "name_key": name_key(header.get("supplier_name")),
        "gstin": header.get("supplier_gstin") if is_valid_gstin(header.get("supplier_gstin")) else None,
        "address": clean_text(header.get("supplier_address")),
        "phone": clean_text(header.get("supplier_phone")),
        "email": clean_text(header.get("supplier_email")),
        "blocked": False,
        "bill_ids": [bill_id],
        "bill_count": 1,
        "first_seen": now,
        "last_seen": now,
        "source": "auto",
    }


def record_bill(existing, header, bill_id, now):
    """Update a known vendor after one of its bills is approved (missing details are filled in)."""
    vendor = dict(existing)
    ids = list(vendor.get("bill_ids") or [])
    if bill_id not in ids:
        ids.append(bill_id)
    vendor["bill_ids"] = ids
    vendor["bill_count"] = len(ids)
    vendor["last_seen"] = now
    for field, source in (("address", "supplier_address"), ("phone", "supplier_phone"), ("email", "supplier_email")):
        if not vendor.get(field) and header.get(source):
            vendor[field] = clean_text(header[source])
    if not vendor.get("gstin") and is_valid_gstin(header.get("supplier_gstin")):
        vendor["gstin"] = header["supplier_gstin"]
    return vendor


EDITABLE = {"name", "gstin", "address", "phone", "email", "blocked"}


def apply_vendor_edits(vendor, edits):
    """User edits from the Vendors screen. Raises ValueError for an invalid GSTIN."""
    out = dict(vendor)
    for field, value in edits.items():
        if field not in EDITABLE:
            continue
        if field == "blocked":
            out["blocked"] = bool(value)
        elif field == "gstin":
            gstin = clean_gstin(value)
            if gstin and not is_valid_gstin(gstin):
                raise ValueError(f"'{value}' is not a valid GSTIN.")
            out["gstin"] = gstin
        else:
            out[field] = clean_text(value)
    out["name_key"] = name_key(out.get("name"))
    out["source"] = "manual"
    return out
