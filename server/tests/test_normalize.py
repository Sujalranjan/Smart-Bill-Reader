from datetime import date

import pytest

from normalize import (InvalidValue, apply_edits, bill_from_legacy, clean_gstin, duplicate_key,
                       is_valid_gstin, parse_date, parse_number)


@pytest.mark.parametrize("raw, expected", [
    ("₹1,23,456.50", 123456.5), ("Rs. 500/-", 500.0), ("(17.64)", -17.64), ("-9.36", -9.36),
    ("9%", 9.0), ("2.000 KG", 2.0), ("1 180.00", 1180.0), (42, 42.0), ("", None), ("N/A", None), (None, None),
])
def test_parse_number(raw, expected):
    assert parse_number(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("25-Jul-2025", "2025-07-25"), ("29/06/2025 20:54:54", "2025-06-29"), ("05/07/2025", "2025-07-05"),
    ("5.7.25", "2025-07-05"), ("2025-07-25", "2025-07-25"), ("25th July, 2025", "2025-07-25"),
    ("Jul 25, 2025", "2025-07-25"), ("25-Jul-2025 09:55 AM", "2025-07-25"), ("31/02/2025", None),
    ("tomorrow", None), (date(2025, 1, 2), "2025-01-02"),
])
def test_parse_date_is_day_first(raw, expected):
    assert parse_date(raw) == expected


def test_gstin_checksum():
    assert is_valid_gstin("29CKPPB2626C1ZC")
    assert is_valid_gstin("29AAHFU3053E1Z6")
    assert not is_valid_gstin("29CKPPB2626C1ZD")  # wrong check digit
    assert not is_valid_gstin("29CKPPB2626")
    assert clean_gstin(" 29ckppb2626c1zc ") == "29CKPPB2626C1ZC"


def test_duplicate_key_prefers_gstin_and_ignores_punctuation():
    a = duplicate_key({"invoice_id": "INV-7561", "supplier_gstin": "29CKPPB2626C1ZC", "supplier_name": "X"})
    b = duplicate_key({"invoice_id": "inv 7561", "supplier_gstin": "29CKPPB2626C1ZC", "supplier_name": "Y"})
    assert a == b == "29CKPPB2626C1ZC|INV7561"
    assert duplicate_key({"invoice_id": "1", "supplier_name": "Metro Cash & Carry"}) == "metrocashcarry|1"
    assert duplicate_key({"invoice_id": "", "supplier_name": "Metro"}) is None


def test_legacy_bill_conversion():
    legacy = {"File_Name": "a.jpg", "supplier_name": "Atlas", "supplier_gst_number": "29AAHFU3053E1Z6",
              "invoice_id": "RB25588", "invoice_date": "05/07/2025", "total_amount": "1,250.00",
              "line_items": [{"Item/Product Name": "Milk", "Quantity": "5", "Rate": "50", "CGST %": "2.5",
                              "SGST %": "2.5", "Amount": "250.00"}]}
    bill = bill_from_legacy(legacy)
    assert bill["header"]["invoice_date"] == "2025-07-05"
    assert bill["header"]["supplier_gstin"] == "29AAHFU3053E1Z6"
    assert bill["totals"]["total_amount"] == 1250.0
    assert bill["line_items"][0] == {"description": "Milk", "hsn_sac": None, "quantity": 5.0, "rate": 50.0,
                                     "discount_pct": None, "cgst_pct": 2.5, "cgst_amount": None,
                                     "sgst_pct": 2.5, "sgst_amount": None, "amount": 250.0}


def test_apply_edits_parses_values_and_clears_confidence():
    bill = bill_from_legacy({"invoice_date": "bad date", "total_amount": "10"})
    bill["confidence"] = {"total_amount": 0.4, "invoice_date": 0.3}
    changed = apply_edits(bill, {"header": {"invoice_date": "01/08/2025"}, "totals": {"total_amount": "1,500"},
                                 "line_items": [{"description": "Tea", "amount": "100"}, {"description": ""}]})
    assert changed == {"invoice_date", "total_amount", "line_items"}
    assert bill["header"]["invoice_date"] == "2025-08-01"
    assert bill["totals"]["total_amount"] == 1500.0
    assert len(bill["line_items"]) == 1  # empty row dropped
    assert bill["confidence"] == {}


@pytest.mark.parametrize("edits, field", [
    ({"header": {"invoice_date": "32/13/2025"}}, "invoice_date"),
    ({"totals": {"total_amount": "abc"}}, "total_amount"),
    ({"line_items": [{"quantity": "two"}]}, "line_items[0].quantity"),
])
def test_apply_edits_rejects_unreadable_values(edits, field):
    bill = bill_from_legacy({})
    with pytest.raises(InvalidValue) as e:
        apply_edits(bill, edits)
    assert e.value.field == field
