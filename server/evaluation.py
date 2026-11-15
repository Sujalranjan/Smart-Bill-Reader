"""Compare extracted bills with hand-checked values (ground truth) and score each field.

Ground truth is a CSV with one row per bill. Columns: `file` plus any of FIELDS.
  - empty cell  -> field not checked for this bill
  - NONE        -> the field does not appear on the bill (extraction should find nothing)
  - a value     -> what a person read from the bill
"""
import re

from normalize import clean_gstin, parse_date, parse_number

TEXT_FIELDS = ["invoice_id", "supplier_name", "purchase_order", "payment_terms"]
DATE_FIELDS = ["invoice_date"]
GSTIN_FIELDS = ["supplier_gstin"]
AMOUNT_FIELDS = ["sub_total", "cgst_amount", "sgst_amount", "igst_amount", "total_tax", "total_amount"]
COUNT_FIELDS = ["line_item_count"]
HEADER_FIELDS = TEXT_FIELDS + DATE_FIELDS + GSTIN_FIELDS + AMOUNT_FIELDS
FIELDS = HEADER_FIELDS + COUNT_FIELDS

ABSENT = "NONE"


def _text_key(value):
    return re.sub(r"[^0-9a-z]", "", str(value).lower())


def extracted_value(bill, field):
    if field == "line_item_count":
        return len(bill["line_items"])
    if field in AMOUNT_FIELDS:
        return bill["totals"].get(field)
    return bill["header"].get(field)


def values_equal(field, truth, extracted):
    if extracted is None:
        return False
    if field in AMOUNT_FIELDS:
        expected = parse_number(truth)
        return expected is not None and abs(expected - float(extracted)) <= 0.01
    if field in COUNT_FIELDS:
        expected = parse_number(truth)
        return expected is not None and int(expected) == int(extracted)
    if field in DATE_FIELDS:
        return parse_date(truth) is not None and parse_date(truth) == extracted
    if field in GSTIN_FIELDS:
        return clean_gstin(truth) == extracted
    return _text_key(truth) == _text_key(extracted)


def score_field(field, truth, extracted):
    """Return one of: skipped, correct, wrong, missing, spurious, correct_absent."""
    truth = (truth or "").strip()
    if not truth:
        return "skipped"
    empty = extracted is None or extracted == "" or (field in COUNT_FIELDS and extracted == 0)
    if truth.upper() == ABSENT:
        return "correct_absent" if empty else "spurious"
    if empty:
        return "missing"
    return "correct" if values_equal(field, truth, extracted) else "wrong"


def score_bill(truth_row, bill):
    return {f: score_field(f, truth_row.get(f), extracted_value(bill, f)) for f in FIELDS}


def _ratio(a, b):
    return round(a / b, 4) if b else None


def summarize_scores(per_bill):
    """per_bill: {file: {field: outcome}} -> per-field and overall metrics."""
    fields = {}
    for field in FIELDS:
        outcomes = [scores[field] for scores in per_bill.values() if scores[field] != "skipped"]
        count = {k: outcomes.count(k) for k in ("correct", "wrong", "missing", "spurious", "correct_absent")}
        evaluated = len(outcomes)
        right = count["correct"] + count["correct_absent"]
        produced = count["correct"] + count["wrong"] + count["spurious"]   # extraction returned a value
        present = count["correct"] + count["wrong"] + count["missing"]     # value exists on the bill
        fields[field] = {
            "evaluated": evaluated,
            **count,
            "accuracy": _ratio(right, evaluated),
            "precision": _ratio(count["correct"], produced),
            "recall": _ratio(count["correct"], present),
            "error_rate": _ratio(evaluated - right, evaluated),
        }

    def group(names):
        evaluated = sum(fields[f]["evaluated"] for f in names)
        right = sum(fields[f]["correct"] + fields[f]["correct_absent"] for f in names)
        return {"evaluated": evaluated, "accuracy": _ratio(right, evaluated)}

    perfect = sum(1 for scores in per_bill.values()
                  if all(o in ("correct", "correct_absent", "skipped") for o in scores.values()))
    return {
        "bills": len(per_bill),
        "bills_fully_correct": perfect,
        "fields": fields,
        "header": group(HEADER_FIELDS),
        "line_items": group(COUNT_FIELDS),
    }


def _pct(value):
    return "n/a" if value is None else f"{value * 100:.1f}%"


def render_report(summary, per_bill, exceptions, timings, thresholds=(0.95, 0.10)):
    """Markdown test report. exceptions: {file: [issue codes]}; timings: list of OCR ms (live calls only)."""
    header_target, exception_target = thresholds
    bills = summary["bills"]
    flagged = sum(1 for codes in exceptions.values() if codes)
    exception_rate = flagged / bills if bills else None
    header_acc = summary["header"]["accuracy"]

    def verdict(ok):
        return "n/a" if ok is None else ("PASS" if ok else "FAIL")

    lines = [
        "# Extraction accuracy report",
        "",
        f"Bills evaluated: **{bills}**. Fully correct on every checked field: **{summary['bills_fully_correct']}**.",
        "",
        "## Acceptance criteria",
        "",
        "| Criterion | Target | Result | Verdict |",
        "| --- | --- | --- | --- |",
        f"| Header field accuracy | ≥ {_pct(header_target)} | {_pct(header_acc)} | "
        f"{verdict(None if header_acc is None else header_acc >= header_target)} |",
        f"| Invoices needing manual review | ≤ {_pct(exception_target)} | {_pct(exception_rate)} | "
        f"{verdict(None if exception_rate is None else exception_rate <= exception_target)} |",
        f"| Line-item count accuracy | (agree with client) | {_pct(summary['line_items']['accuracy'])} | n/a |",
        "",
        "## Field-level results",
        "",
        "| Field | Checked | Correct | Misread | Omitted | Spurious | Accuracy | Precision | Recall |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for field, m in summary["fields"].items():
        if not m["evaluated"]:
            continue
        lines.append(f"| {field} | {m['evaluated']} | {m['correct'] + m['correct_absent']} | {m['wrong']} | "
                     f"{m['missing']} | {m['spurious']} | {_pct(m['accuracy'])} | {_pct(m['precision'])} | {_pct(m['recall'])} |")

    lines += ["", "## Processing time", ""]
    if timings:
        ordered = sorted(timings)
        p95 = ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]
        lines.append(f"{len(timings)} live Document AI calls: average {sum(timings) / len(timings) / 1000:.1f}s, "
                     f"95th percentile {p95 / 1000:.1f}s, slowest {max(timings) / 1000:.1f}s per bill.")
    else:
        lines.append("All results came from the cache, so no processing time was measured in this run.")

    lines += ["", "## Failure cases", "", "| File | Wrong or missing fields | Validation flags |", "| --- | --- | --- |"]
    any_failure = False
    for file, scores in sorted(per_bill.items()):
        bad = [f"{f} ({o})" for f, o in scores.items() if o in ("wrong", "missing", "spurious")]
        codes = exceptions.get(file, [])
        if bad or codes:
            any_failure = True
            lines.append(f"| {file} | {', '.join(bad) or '—'} | {', '.join(codes) or '—'} |")
    if not any_failure:
        lines.append("| — | none | none |")
    lines.append("")
    return "\n".join(lines)
