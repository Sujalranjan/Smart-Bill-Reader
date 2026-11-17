import io
from datetime import datetime, timezone

from google.cloud import documentai
from PIL import Image

import app as api
import pages
from docai_fixtures import GOOD_BILL, GOOD_ITEMS, make_document, page_box
from extraction import extract_document, merge_locations
from normalize import apply_edits, bill_from_extraction, clean_location

AUTH = {"Authorization": "Bearer good-token"}


def _image(fmt="JPEG", size=(60, 80)):
    out = io.BytesIO()
    Image.new("RGB", size, "white").save(out, fmt)
    return out.getvalue()


def _pdf(n_pages=2):
    out = io.BytesIO()
    frames = [Image.new("RGB", (200, 280), "white") for _ in range(n_pages)]
    frames[0].save(out, "PDF", save_all=True, append_images=frames[1:])
    return out.getvalue()


def _scan(client, fake_cloud, data, name):
    fake_cloud["state"]["document"] = make_document(GOOD_BILL, GOOD_ITEMS)
    return client.post("/scan-bill", headers=AUTH, data={"image": [(io.BytesIO(data), name)]},
                       content_type="multipart/form-data")


# --- where each value was read ---------------------------------------------------------

def test_header_and_line_locations_are_extracted():
    bill = bill_from_extraction(extract_document(make_document(GOOD_BILL, GOOD_ITEMS)))
    loc = bill["locations"]
    assert set(loc) == {"invoice_id", "invoice_date", "supplier_name", "supplier_gstin", "sub_total",
                        "cgst_amount", "sgst_amount", "total_tax", "total_amount"}
    assert loc["invoice_id"] == {"page": 0, "box": [0.1, 0.02, 0.6, 0.04]}
    # a line's box covers all of its cells
    first = bill["line_items"][0]["location"]
    assert first["page"] == 0 and first["box"][1] < first["box"][3]
    cells = 7  # description, product_code, quantity, unit_price, cgst, sgst, amount
    assert round(first["box"][3] - first["box"][1], 4) == round(0.02 + (cells - 1) * 0.025, 4)


def test_entity_on_second_page_and_merge():
    doc = make_document({}, [])
    doc.text = "INV-9"
    doc.entities.append(documentai.Document.Entity(
        type_="invoice_id", mention_text="INV-9", confidence=0.9, page_anchor=page_box(1, [0.5, 0.1, 0.9, 0.15])))
    loc = bill_from_extraction(extract_document(doc))["locations"]["invoice_id"]
    assert loc == {"page": 1, "box": [0.5, 0.1, 0.9, 0.15]}
    assert merge_locations([None, {"page": 0, "box": [0.1, 0.1, 0.2, 0.2]}, {"page": 0, "box": [0.3, 0.05, 0.4, 0.15]},
                            {"page": 1, "box": [0, 0, 1, 1]}]) == {"page": 0, "box": [0.1, 0.05, 0.4, 0.2]}


def test_clean_location_rejects_bad_shapes():
    good = {"page": 0, "box": [0.1, 0.2, 0.3, 0.4]}
    assert clean_location(good) == good
    for bad in (None, "x", {"page": -1, "box": [0, 0, 1, 1]}, {"page": True, "box": [0, 0, 1, 1]},
                {"page": 0, "box": [0.5, 0, 0.4, 1]}, {"page": 0, "box": [0, 0, 1.5, 1]}, {"page": 0, "box": [0, 0, 1]},
                {"page": 0, "box": ["a", 0, 1, 1]}):
        assert clean_location(bad) is None, bad


def test_line_locations_survive_edits():
    bill = bill_from_extraction(extract_document(make_document(GOOD_BILL, GOOD_ITEMS)))
    first, second = bill["line_items"]
    # the user deletes the first row and fixes the second; the second keeps its own position
    edits = [dict(second, quantity="2")]
    apply_edits(bill, {"line_items": edits})
    assert bill["line_items"][0]["location"] == second["location"]
    # a row added by hand has no position, and junk positions are dropped
    apply_edits(bill, {"line_items": [dict(second), {"description": "Extra", "amount": "5",
                                                     "location": {"page": 0, "box": [9, 9, 9, 9]}}]})
    assert "location" not in bill["line_items"][1]


# --- page images for the review screen ------------------------------------------------

def test_render_pages():
    assert pages.render_pages(_image(), "image/jpeg") == []
    rendered = pages.render_pages(_pdf(3), "application/pdf")
    assert len(rendered) == 3 and rendered[0].data.startswith(b"\xff\xd8")
    # 200x280 pt page at 150 dpi (pdfium rounds each side independently)
    assert abs(rendered[0].width - 417) <= 1 and abs(rendered[0].height - 583) <= 1
    tiff = pages.render_pages(_image("TIFF"), "image/tiff")
    assert len(tiff) == 1 and (tiff[0].width, tiff[0].height) == (60, 80)


def test_photo_bill_uses_the_original_as_its_page(fake_cloud):
    c = api.app.test_client()
    body = _scan(c, fake_cloud, _image(), "bill.jpg").get_json()["bill"]
    assert body["pages"] == [{"url": f"https://signed.example/{body['image_path']}", "width": 60, "height": 80}]
    assert body["locations"]["total_amount"]["page"] == 0
    assert len(fake_cloud["bucket"].files) == 1


def test_pdf_bill_gets_page_images_which_are_deleted_with_it(fake_cloud):
    c = api.app.test_client()
    r = _scan(c, fake_cloud, _pdf(2), "bill.pdf").get_json()
    detail = c.get(f"/bills/{r['id']}", headers=AUTH).get_json()["bill"]
    assert [p["url"].rsplit("-", 1)[-1] for p in detail["pages"]] == ["p1.jpg", "p2.jpg"]
    assert "path" not in detail["pages"][0]
    assert len(fake_cloud["bucket"].files) == 3
    c.delete(f"/bills/{r['id']}", headers=AUTH)
    assert fake_cloud["bucket"].files == {}


def test_page_rendering_failure_does_not_block_the_scan(fake_cloud, monkeypatch):
    def broken(*_args, **_kwargs):
        raise RuntimeError("renderer crashed")
    monkeypatch.setattr(pages, "render_pages", broken)
    c = api.app.test_client()
    r = _scan(c, fake_cloud, _pdf(1), "bill.pdf")
    assert r.status_code == 201 and r.get_json()["bill"]["pages"] == []


def test_line_location_round_trip_through_the_api(fake_cloud):
    c = api.app.test_client()
    bill = _scan(c, fake_cloud, _image(), "bill.jpg").get_json()["bill"]
    lines = bill["line_items"]
    assert all("location" in line for line in lines)
    r = c.put(f"/bills/{bill['id']}", headers=AUTH, json={"line_items": [dict(lines[1], quantity=1)]})
    saved = r.get_json()["bill"]["line_items"]
    assert saved[0]["location"] == lines[1]["location"]


def test_older_bills_fall_back_to_the_original_photo(fake_cloud):
    db = fake_cloud["db"]
    db.store[("users", "user1", "bills", "old1")] = {
        "supplier_name": "Atlas", "invoice_id": "RB1", "total_amount": "250.00",
        "timestamp": datetime(2025, 7, 5, tzinfo=timezone.utc),
        "image_url": "https://storage.googleapis.com/smart-bill-474414.firebasestorage.app/bills/user1/x.jpg",
    }
    c = api.app.test_client()
    bill = c.get("/bills/old1", headers=AUTH).get_json()["bill"]
    assert bill["pages"] == [{"url": "https://signed.example/bills/user1/x.jpg", "width": None, "height": None}]
    assert bill["locations"] == {}
