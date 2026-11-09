"""Business checks on an extracted bill. Produces a list of issues for the review screen.

Severity:
  "error"   - the bill cannot be approved until it is fixed
  "warning" - shown for review; the user may approve anyway
"""
from datetime import date, timedelta

from normalize import is_iso_date, is_valid_gstin

LOW_CONFIDENCE = 0.7
REQUIRED = {
    "invoice_id": "Invoice number",
    "invoice_date": "Invoice date",
    "supplier_name": "Supplier name",
}


def _issue(code, field, message, severity="warning"):
    return {"code": code, "field": field, "message": message, "severity": severity}


def _close(a, b, tolerance):
    return a is not None and b is not None and abs(a - b) <= tolerance


def _money(value):
    return f"₹{value:,.2f}"


def validate(bill, duplicate_ids=(), today=None):
    today = today or date.today()
    header, totals, items = bill["header"], bill["totals"], bill["line_items"]
    issues = []

    # 1. Mandatory fields
    for field, label in REQUIRED.items():
        if not header.get(field):
            issues.append(_issue("missing_field", field, f"{label} is missing.", "error"))
    if totals.get("total_amount") is None:
        issues.append(_issue("missing_field", "total_amount", "Total amount is missing.", "error"))

    # 2. Field formats
    for field in ("invoice_date", "due_date"):
        value = header.get(field)
        if value and not is_iso_date(value):
            issues.append(_issue("invalid_date", field, f"Could not read the date '{value}'.", "error"))
    invoice_date = header.get("invoice_date")
    if is_iso_date(invoice_date):
        d = date.fromisoformat(invoice_date)
        if d > today + timedelta(days=1):
            issues.append(_issue("future_date", "invoice_date", "Invoice date is in the future."))
        elif d < today - timedelta(days=3 * 365):
            issues.append(_issue("old_date", "invoice_date", "Invoice date is more than 3 years old."))

    for field, label in (("supplier_gstin", "Supplier GSTIN"), ("buyer_gstin", "Buyer GSTIN")):
        gstin = header.get(field)
        if gstin and not is_valid_gstin(gstin):
            issues.append(_issue("invalid_gstin", field, f"{label} '{gstin}' is not a valid GSTIN."))

    total = totals.get("total_amount")
    if total is not None and total <= 0:
        issues.append(_issue("invalid_amount", "total_amount", "Total amount must be greater than zero.", "error"))
    for field, value in totals.items():
        if field != "total_amount" and value is not None and value < 0:
            issues.append(_issue("invalid_amount", field, "Amount cannot be negative."))

    # Text that OCR found but that could not be read as a number
    raw = bill.get("raw", {})
    for field in totals:
        if totals[field] is None and raw.get(field):
            issues.append(_issue("unreadable_amount", field, f"Could not read the amount '{raw[field]}'.",
                                 "error" if field == "total_amount" else "warning"))

    # 3. Arithmetic
    tolerance = max(1.0, (total or 0) * 0.005)  # rounding / "round off" lines on Indian bills
    sub_total, total_tax = totals.get("sub_total"), totals.get("total_tax")
    tax_parts = [totals[k] for k in ("cgst_amount", "sgst_amount", "igst_amount") if totals.get(k) is not None]

    if total_tax is not None and tax_parts and not _close(sum(tax_parts), total_tax, tolerance):
        issues.append(_issue("tax_mismatch", "total_tax",
                             f"CGST + SGST + IGST ({_money(sum(tax_parts))}) does not equal total tax ({_money(total_tax)})."))

    tax = total_tax if total_tax is not None else (sum(tax_parts) if tax_parts else None)
    if sub_total is not None and tax is not None and total is not None and not _close(sub_total + tax, total, tolerance):
        issues.append(_issue("totals_mismatch", "total_amount",
                             f"Subtotal + tax ({_money(sub_total + tax)}) does not equal total ({_money(total)})."))

    amounts = [i["amount"] for i in items if i.get("amount") is not None]
    if amounts and total is not None:
        line_sum = sum(amounts)
        # Line amounts may be before tax or include tax, depending on the bill layout.
        candidates = [total]
        if sub_total is not None:
            candidates.append(sub_total)
        if tax is not None:
            candidates.append(total - tax)
        if not any(_close(line_sum, c, tolerance) for c in candidates):
            issues.append(_issue("line_items_mismatch", "line_items",
                                 f"Line items add up to {_money(line_sum)}, which does not match the bill total ({_money(total)})."))
    if not items:
        issues.append(_issue("no_line_items", "line_items", "No line items were found."))

    for n, item in enumerate(items, 1):
        q, r, amount = item.get("quantity"), item.get("rate"), item.get("amount")
        if not item.get("description"):
            issues.append(_issue("missing_field", f"line_items[{n - 1}].description", f"Line {n}: product name is missing."))
        if q is not None and r is not None and amount is not None:
            base = q * r * (1 - (item.get("discount_pct") or 0) / 100)
            gst_pct = (item.get("cgst_pct") or 0) + (item.get("sgst_pct") or 0)
            line_tol = max(1.0, abs(amount) * 0.01)
            if not (_close(base, amount, line_tol) or _close(base * (1 + gst_pct / 100), amount, line_tol)):
                issues.append(_issue("line_amount_mismatch", f"line_items[{n - 1}].amount",
                                     f"Line {n}: quantity × rate ({_money(base)}) does not match amount ({_money(amount)})."))

    # 4. Duplicates
    if duplicate_ids:
        issues.append(_issue("duplicate", "invoice_id",
                             "This invoice number from this supplier has already been scanned.", "error")
                      | {"duplicate_of": list(duplicate_ids)})

    # 5. Low OCR confidence
    for field, conf in sorted(bill.get("confidence", {}).items()):
        if conf is not None and conf < LOW_CONFIDENCE:
            issues.append(_issue("low_confidence", field,
                                 f"Low reading confidence ({conf:.0%}). Please check this value."))

    return issues


def summarize(issues):
    errors = sum(1 for i in issues if i["severity"] == "error")
    return {"issue_count": len(issues), "error_count": errors, "warning_count": len(issues) - errors}
