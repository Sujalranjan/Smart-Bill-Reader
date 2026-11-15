import io

from PIL import Image

import app as api
import vendors
from docai_fixtures import GOOD_BILL, GOOD_ITEMS, make_document

AUTH = {"Authorization": "Bearer good-token"}


def _jpeg():
    out = io.BytesIO()
    Image.new("RGB", (50, 50), "white").save(out, "JPEG")
    return out.getvalue()


def _scan(client, fake_cloud, fields=GOOD_BILL, items=GOOD_ITEMS):
    fake_cloud["state"]["document"] = make_document(fields, items)
    return client.post("/scan-bill", headers=AUTH, data={"image": [(io.BytesIO(_jpeg()), "bill.jpg")]},
                       content_type="multipart/form-data")


def _codes(bill):
    return {i["code"] for i in bill["issues"]}


# --- pure vendor logic ---------------------------------------------------------------

def test_name_key_ignores_legal_suffixes_and_punctuation():
    assert vendors.name_key("M/s Metro Cash & Carry India Pvt. Ltd.") == "metrocashcarry"
    assert vendors.names_match("Shree Bharath Distributor", "SHREE BHARATH DISTRIBUTORS")
    assert not vendors.names_match("Shree Bharath Distributor", "Atlas Distributors")


def test_vendor_id_prefers_valid_gstin():
    assert vendors.vendor_id({"supplier_gstin": "29CKPPB2626C1ZC", "supplier_name": "X"}) == "29CKPPB2626C1ZC"
    assert vendors.vendor_id({"supplier_gstin": "BAD", "supplier_name": "Atlas Pvt Ltd"}) == "name-atlas"
    assert vendors.vendor_id({"supplier_name": ""}) is None


def test_match_vendor_statuses():
    header = {"supplier_gstin": "29CKPPB2626C1ZC", "supplier_name": "Shree Bharath Distributor"}
    known = {"id": "29CKPPB2626C1ZC", "name": "Shree Bharath Distributor", "gstin": "29CKPPB2626C1ZC"}
    assert vendors.match_vendor(header, None, [])["status"] == "new"
    assert vendors.match_vendor(header, known, [])["status"] == "match"
    assert vendors.match_vendor(header, dict(known, blocked=True), [])["status"] == "blocked"
    assert vendors.match_vendor(header, dict(known, name="Atlas Distributors"), [])["status"] == "name_mismatch"
    other = {"id": "x", "name": "Shree Bharath Distributor", "gstin": "29AAHFU3053E1Z6"}
    assert vendors.match_vendor(header, None, [other])["status"] == "gstin_mismatch"
    assert vendors.match_vendor({"supplier_name": None}, None, [])["status"] == "unknown"


# --- API -----------------------------------------------------------------------------

def test_first_bill_needs_review_then_same_vendor_is_auto_approved(fake_cloud):
    c = api.app.test_client()

    first = _scan(c, fake_cloud).get_json()
    assert first["auto_approved"] is False
    assert first["bill"]["status"] == "draft" and _codes(first["bill"]) == {"new_vendor"}
    assert c.get("/vendors", headers=AUTH).get_json()["vendors"] == []

    c.post(f"/bills/{first['id']}/approve", headers=AUTH)
    listed = c.get("/vendors", headers=AUTH).get_json()["vendors"]
    assert [(v["id"], v["name"], v["bill_count"]) for v in listed] == \
        [("29CKPPB2626C1ZC", "Shree Bharath Distributor", 1)]

    # A second, clean invoice from the now-known supplier goes straight through
    second = _scan(c, fake_cloud, fields=dict(GOOD_BILL, invoice_id="INV-7562")).get_json()
    assert second["auto_approved"] is True
    assert second["bill"]["status"] == "approved" and second["bill"]["issues"] == []
    assert [a["action"] for a in second["bill"]["audit"]] == ["scanned", "auto_approved"]
    assert c.get("/vendors", headers=AUTH).get_json()["vendors"][0]["bill_count"] == 2

    summaries = {b["id"]: b for b in c.get("/bills", headers=AUTH).get_json()["bills"]}
    assert summaries[second["id"]]["auto_approved"] is True
    assert summaries[first["id"]]["auto_approved"] is False


def test_no_auto_approve_when_confidence_is_low_or_bill_has_issues(fake_cloud):
    c = api.app.test_client()
    first = _scan(c, fake_cloud).get_json()
    c.post(f"/bills/{first['id']}/approve", headers=AUTH)

    unsure = dict(GOOD_BILL, invoice_id="INV-2", total_amount=("₹1,180.00", 0.8))
    assert _scan(c, fake_cloud, fields=unsure).get_json()["auto_approved"] is False  # below 0.9, above the 0.7 warning

    wrong_total = dict(GOOD_BILL, invoice_id="INV-3", total_amount="1,500.00")
    body = _scan(c, fake_cloud, fields=wrong_total).get_json()
    assert body["auto_approved"] is False and "totals_mismatch" in _codes(body["bill"])


def test_auto_approve_can_be_switched_off(fake_cloud, monkeypatch):
    monkeypatch.setattr(api, "AUTO_APPROVE", False)
    c = api.app.test_client()
    first = _scan(c, fake_cloud).get_json()
    c.post(f"/bills/{first['id']}/approve", headers=AUTH)
    assert _scan(c, fake_cloud, fields=dict(GOOD_BILL, invoice_id="INV-2")).get_json()["auto_approved"] is False


def test_blocked_vendor_and_mismatches(fake_cloud):
    c = api.app.test_client()
    first = _scan(c, fake_cloud).get_json()
    c.post(f"/bills/{first['id']}/approve", headers=AUTH)

    # Same GSTIN under a different name is flagged
    renamed = dict(GOOD_BILL, invoice_id="INV-2", supplier_name="Atlas Distributors")
    assert "vendor_name_mismatch" in _codes(_scan(c, fake_cloud, fields=renamed).get_json()["bill"])

    # Same name with a different (valid) GSTIN is flagged
    other_gstin = dict(GOOD_BILL, invoice_id="INV-3", supplier_gst_number="29AAHFU3053E1Z6")
    assert "vendor_gstin_mismatch" in _codes(_scan(c, fake_cloud, fields=other_gstin).get_json()["bill"])

    # Blocking the vendor stops approval of its bills
    r = c.put("/vendors/29CKPPB2626C1ZC", headers=AUTH, json={"blocked": True})
    assert r.status_code == 200 and r.get_json()["vendor"]["blocked"] is True
    blocked = _scan(c, fake_cloud, fields=dict(GOOD_BILL, invoice_id="INV-4")).get_json()
    assert "vendor_blocked" in _codes(blocked["bill"])
    assert c.post(f"/bills/{blocked['id']}/approve", headers=AUTH).status_code == 409


def test_vendor_crud(fake_cloud):
    c = api.app.test_client()
    r = c.post("/vendors", headers=AUTH, json={"name": "Atlas Distributors Pvt Ltd", "gstin": "29aahfu3053e1z6"})
    assert r.status_code == 201 and r.get_json()["vendor"]["id"] == "29AAHFU3053E1Z6"
    assert c.post("/vendors", headers=AUTH, json={"name": "Atlas", "gstin": "29AAHFU3053E1Z6"}).status_code == 409
    assert c.post("/vendors", headers=AUTH, json={"name": "Bad", "gstin": "123"}).status_code == 400
    assert c.post("/vendors", headers=AUTH, json={"gstin": ""}).status_code == 400

    # A manually added vendor is recognised on its first bill
    fields = dict(GOOD_BILL, supplier_name="Atlas Distributors", supplier_gst_number="29AAHFU3053E1Z6")
    assert _scan(c, fake_cloud, fields=fields).get_json()["auto_approved"] is True

    r = c.put("/vendors/29AAHFU3053E1Z6", headers=AUTH, json={"phone": "080 1234"})
    assert r.get_json()["vendor"]["phone"] == "080 1234"
    assert c.get("/vendors", headers={"Authorization": "Bearer other-token"}).get_json()["vendors"] == []
    assert c.delete("/vendors/29AAHFU3053E1Z6", headers=AUTH).status_code == 200
    assert c.delete("/vendors/29AAHFU3053E1Z6", headers=AUTH).status_code == 404


def test_quality_report(fake_cloud):
    c = api.app.test_client()
    first = _scan(c, fake_cloud).get_json()                                     # flagged: new vendor
    c.put(f"/bills/{first['id']}", headers=AUTH, json={"header": {"payment_terms": "Net 30"}})
    c.post(f"/bills/{first['id']}/approve", headers=AUTH)
    _scan(c, fake_cloud, fields=dict(GOOD_BILL, invoice_id="INV-2"))            # auto-approved
    no_id = {k: v for k, v in GOOD_BILL.items() if k != "invoice_id"}
    _scan(c, fake_cloud, fields=no_id)                                          # blocked by an error

    report = c.get("/reports/quality", headers=AUTH).get_json()["report"]
    assert report["bills_total"] == 3 and report["approved"] == 2
    assert report["auto_approved"] == 1 and report["manually_approved"] == 1
    assert report["waiting_for_review"] == 1
    assert report["exception_rate"] == round(2 / 3, 4)
    assert report["straight_through_rate"] == round(1 / 3, 4)
    assert report["blocked_by_error_rate"] == round(1 / 3, 4)
    assert report["manual_correction_rate"] == round(1 / 3, 4)
    assert {"code": "new_vendor", "bills": 1} in report["exception_reasons"]
    assert report["most_corrected_fields"] == [{"field": "payment_terms", "bills": 1}]
    assert report["processing"]["pages"] == 3 and report["processing"]["avg_ocr_ms"] is not None
