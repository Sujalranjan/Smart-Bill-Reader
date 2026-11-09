import csv
import io
import json

import openpyxl
import pytest
from PIL import Image

import exporters
from preprocess import UploadError, prepare_upload


def _jpeg(size=(100, 140), orientation=None):
    out = io.BytesIO()
    img = Image.new("RGB", size, "white")
    if orientation:
        exif = img.getexif()
        exif[0x0112] = orientation
        img.save(out, "JPEG", exif=exif)
    else:
        img.save(out, "JPEG")
    return out.getvalue()


def test_single_jpeg_is_passed_through_unchanged():
    data = _jpeg()
    assert prepare_upload([data]) == (data, "image/jpeg", 1)


def test_rotated_photo_is_straightened():
    content, mime, _ = prepare_upload([_jpeg((100, 140), orientation=6)])
    assert mime == "image/jpeg"
    assert Image.open(io.BytesIO(content)).size == (140, 100)


def test_huge_photo_is_downscaled():
    content, _, _ = prepare_upload([_jpeg((5000, 3000))])
    assert max(Image.open(io.BytesIO(content)).size) == 3000


def test_several_photos_become_one_pdf():
    content, mime, pages = prepare_upload([_jpeg(), _jpeg(), _jpeg()])
    assert mime == "application/pdf" and pages == 3 and content.startswith(b"%PDF")


def test_pdf_passes_through():
    assert prepare_upload([b"%PDF-1.7 ..."])[1] == "application/pdf"


@pytest.mark.parametrize("files, status", [
    ([], 400), ([b"hello"], 415), ([b"%PDF-1.7", _jpeg()], 400), ([_jpeg()] * 11, 400),
])
def test_bad_uploads(files, status):
    with pytest.raises(UploadError) as e:
        prepare_upload(files)
    assert e.value.status == status


def _bills():
    header = {"invoice_id": "INV-1", "invoice_date": "2025-07-25", "supplier_name": "Shree Bharath",
              "supplier_gstin": "29CKPPB2626C1ZC"}
    totals = {"total_amount": 1180.0, "total_tax": 180.0}
    long_name = "A" * 40
    return [
        {"id": "b1", "status": "approved", "header": header, "totals": totals, "image_url": "https://x/1",
         "line_items": [{"description": "Tea ₹", "quantity": 2.0, "amount": 600.0},
                        {"description": "Sugar", "amount": 400.0}]},
        {"id": "b2", "status": "draft", "header": {"supplier_name": long_name + "1"}, "totals": {}, "line_items": []},
        {"id": "b3", "status": "draft", "header": {"supplier_name": long_name + "2"}, "totals": {}, "line_items": []},
    ]


def test_csv_has_one_row_per_line_item():
    rows = list(csv.DictReader(io.StringIO(exporters.to_csv(_bills()).decode("utf-8-sig"))))
    assert len(rows) == 4  # 2 items + 1 row for each bill without items
    assert rows[0]["bill_id"] == "b1" and rows[0]["description"] == "Tea ₹" and rows[0]["quantity"] == "2.0"
    assert rows[0]["supplier_gstin"] == "29CKPPB2626C1ZC"
    assert rows[2]["line_no"] == ""


def test_json_export():
    data = json.loads(exporters.to_json(_bills()))
    assert data["bills"][0]["totals"]["total_amount"] == 1180.0


def test_xlsx_has_summary_sheets_and_unique_supplier_sheets():
    wb = openpyxl.load_workbook(io.BytesIO(exporters.to_xlsx(_bills())))
    assert wb.sheetnames[:2] == ["Invoices", "Line Items"]
    supplier_sheets = wb.sheetnames[2:]
    # the two 41-character names collide after truncation to 31 and must not overwrite each other
    assert len(supplier_sheets) == 3 and len({s.lower() for s in supplier_sheets}) == 3
    assert all(len(s) <= 31 for s in supplier_sheets)
    assert wb["Invoices"].max_row == 4 and wb["Line Items"].max_row == 5
