from datetime import date

from google.cloud import documentai

from docai_fixtures import GOOD_BILL, GOOD_ITEMS, make_document
from extraction import extract_document
from normalize import bill_from_extraction
from validation import summarize, validate

TODAY = date(2025, 8, 1)


def _bill(fields=GOOD_BILL, items=GOOD_ITEMS):
    return bill_from_extraction(extract_document(make_document(fields, items)))


def codes(issues):
    return sorted(i["code"] for i in issues)


def test_extraction_maps_and_normalizes_fields():
    bill = _bill()
    assert bill["header"]["invoice_id"] == "INV-7561"
    assert bill["header"]["invoice_date"] == "2025-07-25"
    assert bill["header"]["supplier_gstin"] == "29CKPPB2626C1ZC"
    assert bill["totals"] == {"sub_total": 1000.0, "cgst_amount": 90.0, "sgst_amount": 90.0,
                              "igst_amount": None, "total_tax": 180.0, "total_amount": 1180.0}
    assert bill["line_items"][0]["quantity"] == 2.0 and bill["line_items"][0]["cgst_pct"] == 9.0
    # a single "GST %" column is split into CGST + SGST
    assert bill["line_items"][1]["cgst_pct"] == 9.0 and bill["line_items"][1]["sgst_pct"] == 9.0
    assert bill["raw"]["total_amount"] == "₹1,180.00"
    assert 0 < bill["confidence"]["invoice_id"] <= 1


def test_clean_bill_has_no_issues():
    assert validate(_bill(), today=TODAY) == []


def test_missing_mandatory_fields_are_errors():
    fields = {k: v for k, v in GOOD_BILL.items() if k not in ("invoice_id", "total_amount")}
    issues = validate(_bill(fields), today=TODAY)
    missing = [i for i in issues if i["code"] == "missing_field"]
    assert {i["field"] for i in missing} == {"invoice_id", "total_amount"}
    assert all(i["severity"] == "error" for i in missing)
    assert summarize(issues)["error_count"] >= 2


def test_totals_mismatch_flagged():
    # line items still match the subtotal, so only the total is called out
    issues = validate(_bill(dict(GOOD_BILL, total_amount="1,500.00")), today=TODAY)
    assert codes(issues) == ["totals_mismatch"]


def test_line_items_mismatch_flagged():
    items = [dict(GOOD_ITEMS[0], quantity="5", amount="1500.00"), GOOD_ITEMS[1]]
    issues = validate(_bill(items=items), today=TODAY)
    assert codes(issues) == ["line_items_mismatch"]


def test_round_off_within_tolerance_is_accepted():
    assert validate(_bill(dict(GOOD_BILL, total_amount="1,180.40")), today=TODAY) == []


def test_line_amount_mismatch():
    items = [dict(GOOD_ITEMS[0], amount="900.00"), GOOD_ITEMS[1]]
    issues = validate(_bill(items=items), today=TODAY)
    assert any(i["code"] == "line_amount_mismatch" and i["field"] == "line_items[0].amount" for i in issues)


def test_invalid_gstin_future_date_low_confidence_and_duplicate():
    fields = dict(GOOD_BILL, supplier_gst_number="29CKPPB2626C1ZX", invoice_date="25-Jul-2026",
                  supplier_name=("Shree Bharath Distributor", 0.42))
    issues = validate(_bill(fields), duplicate_ids=["bill9"], today=TODAY)
    assert {"invalid_gstin", "future_date", "low_confidence", "duplicate"} <= set(codes(issues))
    dup = next(i for i in issues if i["code"] == "duplicate")
    assert dup["severity"] == "error" and dup["duplicate_of"] == ["bill9"]


def test_unreadable_total_is_an_error():
    issues = validate(_bill(dict(GOOD_BILL, total_amount="see overleaf")), today=TODAY)
    assert any(i["code"] == "unreadable_amount" and i["severity"] == "error" for i in issues)


def test_multiple_descriptions_in_one_line_item_entity_become_rows():
    extra = "Milk\nCurd\n50\n30\n"
    base = 0
    seg = documentai.Document.TextAnchor.TextSegment

    def prop(t, s, e):
        return documentai.Document.Entity(type_=t, text_anchor=documentai.Document.TextAnchor(
            text_segments=[seg(start_index=base + s, end_index=base + e)]))

    doc = documentai.Document(text=extra, entities=[documentai.Document.Entity(type_="line_item", properties=[
        prop("line_item/description", 0, 4), prop("line_item/description", 5, 9),
        prop("line_item/amount", 10, 12), prop("line_item/amount", 13, 15)])])
    out = extract_document(doc)
    assert out["line_items"] == [{"description": "Milk", "amount": "50", "_location": None},
                                 {"description": "Curd", "amount": "30", "_location": None}]
    assert out["page_count"] == 1
