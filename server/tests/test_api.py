import io
from datetime import datetime, timezone

from PIL import Image

import app as api
from docai_fixtures import GOOD_BILL, GOOD_ITEMS, make_document

AUTH = {"Authorization": "Bearer good-token"}


def _jpeg():
    out = io.BytesIO()
    Image.new("RGB", (50, 50), "white").save(out, "JPEG")
    return out.getvalue()


def _scan(client, fake_cloud, fields=GOOD_BILL, items=GOOD_ITEMS, files=None):
    fake_cloud["state"]["document"] = make_document(fields, items)
    files = files or [(io.BytesIO(_jpeg()), "bill.jpg")]
    return client.post("/scan-bill", headers=AUTH, data={"image": files}, content_type="multipart/form-data")


def test_auth_required(fake_cloud):
    c = api.app.test_client()
    assert c.get("/bills").status_code == 401
    assert c.get("/bills", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert c.get("/healthz").status_code == 200


def test_scan_review_approve_export_flow(fake_cloud):
    c = api.app.test_client()
    r = _scan(c, fake_cloud)
    assert r.status_code == 201, r.get_json()
    bill, bill_id = r.get_json()["bill"], r.get_json()["id"]
    assert bill["status"] == "draft" and bill["error_count"] == 0
    assert bill["header"]["invoice_date"] == "2025-07-25"
    assert bill["image_url"].startswith("https://signed.example/bills/user1/")
    assert list(fake_cloud["bucket"].files) == [bill["image_path"]]

    listed = c.get("/bills", headers=AUTH).get_json()["bills"]
    assert [b["id"] for b in listed] == [bill_id] and listed[0]["total"] == 1180.0

    r = c.post(f"/bills/{bill_id}/approve", headers=AUTH)
    assert r.status_code == 200 and r.get_json()["bill"]["status"] == "approved"

    # Editing an approved bill sends it back to draft and records the change
    body = c.put(f"/bills/{bill_id}", headers=AUTH, json={"header": {"payment_terms": "Net 30"}}).get_json()["bill"]
    assert body["status"] == "draft" and body["header"]["payment_terms"] == "Net 30"
    assert [a["action"] for a in body["audit"]] == ["scanned", "approved", "edited"]

    c.post(f"/bills/{bill_id}/approve", headers=AUTH)
    r = c.get("/export?format=csv&status=approved&from=2025-07-01&to=2025-07-31", headers=AUTH)
    assert r.status_code == 200 and r.mimetype == "text/csv"
    assert "INV-7561" in r.data.decode("utf-8-sig")
    assert c.get("/export?format=csv&from=2025-08-01", headers=AUTH).status_code == 404
    assert c.get("/export?format=pdf", headers=AUTH).status_code == 400
    assert c.get("/export-bills", headers=AUTH).mimetype.endswith("sheet")


def test_bill_with_errors_cannot_be_approved_until_fixed(fake_cloud):
    c = api.app.test_client()
    fields = {k: v for k, v in GOOD_BILL.items() if k != "invoice_id"}
    bill_id = _scan(c, fake_cloud, fields=fields).get_json()["id"]

    r = c.post(f"/bills/{bill_id}/approve", headers=AUTH)
    assert r.status_code == 409
    assert any(i["field"] == "invoice_id" for i in r.get_json()["bill"]["issues"])

    r = c.put(f"/bills/{bill_id}", headers=AUTH, json={"header": {"invoice_id": "INV-9"}})
    assert r.get_json()["bill"]["error_count"] == 0
    assert c.post(f"/bills/{bill_id}/approve", headers=AUTH).status_code == 200


def test_invalid_edit_is_rejected_with_field(fake_cloud):
    c = api.app.test_client()
    bill_id = _scan(c, fake_cloud).get_json()["id"]
    r = c.put(f"/bills/{bill_id}", headers=AUTH, json={"totals": {"total_amount": "abc"}})
    assert r.status_code == 400 and r.get_json()["field"] == "total_amount"


def test_duplicate_invoice_is_flagged(fake_cloud):
    c = api.app.test_client()
    first = _scan(c, fake_cloud).get_json()["id"]
    second = _scan(c, fake_cloud).get_json()
    dup = next(i for i in second["bill"]["issues"] if i["code"] == "duplicate")
    assert dup["duplicate_of"] == [first]

    # Deleting the duplicate clears the warning on the original
    c.delete(f"/bills/{second['id']}", headers=AUTH)
    assert c.post(f"/bills/{first}/approve", headers=AUTH).status_code == 200


def test_multi_page_photos_and_not_a_bill(fake_cloud):
    c = api.app.test_client()
    files = [(io.BytesIO(_jpeg()), "p1.jpg"), (io.BytesIO(_jpeg()), "p2.jpg")]
    body = _scan(c, fake_cloud, files=files).get_json()["bill"]
    assert body["mime_type"] == "application/pdf" and body["page_count"] == 2
    assert body["file_name"] == "2-page scan.pdf"

    r = _scan(c, fake_cloud, fields={"supplier_phone": "123"}, items=[])
    assert r.status_code == 422
    assert len(fake_cloud["bucket"].files) == 1  # nothing stored for the rejected upload


def test_unsupported_upload(fake_cloud):
    c = api.app.test_client()
    r = _scan(c, fake_cloud, files=[(io.BytesIO(b"hello"), "../../evil.jpg")])
    assert r.status_code == 415


def test_users_cannot_see_each_others_bills(fake_cloud):
    c = api.app.test_client()
    bill_id = _scan(c, fake_cloud).get_json()["id"]
    other = {"Authorization": "Bearer other-token"}
    assert c.get(f"/bills/{bill_id}", headers=other).status_code == 404
    assert c.delete(f"/bills/{bill_id}", headers=other).status_code == 404
    assert c.get("/bills", headers=other).get_json()["bills"] == []


def test_delete_removes_record_and_file(fake_cloud):
    c = api.app.test_client()
    bill_id = _scan(c, fake_cloud).get_json()["id"]
    assert c.delete(f"/bills/{bill_id}", headers=AUTH).status_code == 200
    assert c.get(f"/bills/{bill_id}", headers=AUTH).status_code == 404
    assert fake_cloud["bucket"].files == {}


def test_legacy_bills_still_load_and_export(fake_cloud):
    db = fake_cloud["db"]
    db.store[("users", "user1", "bills", "old1")] = {
        "File_Name": "old.jpg", "supplier_name": "Atlas", "invoice_id": "RB1", "invoice_date": "05/07/2025",
        "total_amount": "250.00", "timestamp": datetime(2025, 7, 5, tzinfo=timezone.utc),
        "image_url": "https://storage.googleapis.com/smart-bill-474414.firebasestorage.app/bills/user1/x.jpg",
        "line_items": [{"Item/Product Name": "Milk", "Amount": "250.00"}],
    }
    c = api.app.test_client()
    listed = c.get("/bills", headers=AUTH).get_json()["bills"]
    assert listed[0]["invoice_date"] == "2025-07-05" and listed[0]["total"] == 250.0
    assert listed[0]["image"] == "https://signed.example/bills/user1/x.jpg"
    assert c.get("/get-history", headers=AUTH).get_json()["history"][0]["supplier"] == "Atlas"
    r = c.put("/bills/old1", headers=AUTH, json={"header": {"supplier_gstin": "29AAHFU3053E1Z6"}})
    assert r.status_code == 200
    assert db.store[("users", "user1", "bills", "old1")]["schema_version"] == 2
