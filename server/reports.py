"""Operational quality numbers computed from stored bills.

These answer the requirement letter's Phase 2 questions for live usage: how many
invoices needed manual review, why, what users had to correct, and how long
processing takes. (Field-level accuracy against hand-checked data is measured
separately by tools/evaluate.py.)
"""
from collections import Counter


def _percentile(values, pct):
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(pct / 100 * (len(ordered) - 1))))
    return ordered[index]


def _rate(part, whole):
    return round(part / whole, 4) if whole else None


def quality_report(bills):
    total = len(bills)
    measured = [b for b in bills if b.get("metrics")]  # bills scanned since metrics were introduced
    approved = [b for b in bills if b.get("status") == "approved"]
    auto = [b for b in approved if (b.get("metrics") or {}).get("auto_approved")]

    flagged = [b for b in measured if b["metrics"].get("initial_issue_codes")]
    blocked = [b for b in measured if b["metrics"].get("initial_error_count")]
    reasons = Counter(code for b in measured for code in b["metrics"].get("initial_issue_codes", []))

    edited_fields = Counter()
    corrected = 0
    for b in bills:
        fields = {f for a in b.get("audit", []) if a.get("action") == "edited" for f in a.get("fields", [])}
        if fields:
            corrected += 1
            edited_fields.update(fields)

    ocr = [b["metrics"]["ocr_ms"] for b in measured if b["metrics"].get("ocr_ms") is not None]
    pages = sum(b["metrics"].get("pages") or 1 for b in measured)

    return {
        "bills_total": total,
        "bills_measured": len(measured),
        "approved": len(approved),
        "auto_approved": len(auto),
        "manually_approved": len(approved) - len(auto),
        "waiting_for_review": total - len(approved),
        # share of scanned invoices that needed a person to look at them
        "exception_rate": _rate(len(flagged), len(measured)),
        "straight_through_rate": _rate(len(auto), len(measured)),
        "blocked_by_error_rate": _rate(len(blocked), len(measured)),
        "manual_correction_rate": _rate(corrected, total),
        "exception_reasons": [{"code": c, "bills": n} for c, n in reasons.most_common()],
        "most_corrected_fields": [{"field": f, "bills": n} for f, n in edited_fields.most_common(10)],
        "processing": {
            "pages": pages,
            "avg_ocr_ms": round(sum(ocr) / len(ocr)) if ocr else None,
            "p95_ocr_ms": _percentile(ocr, 95),
            "max_ocr_ms": max(ocr) if ocr else None,
        },
    }
