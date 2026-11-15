import csv
import hashlib
import io
import os
import subprocess
import sys

from google.cloud import documentai
from PIL import Image

from docai_fixtures import GOOD_BILL, GOOD_ITEMS, make_document
from evaluation import FIELDS, render_report, score_bill, score_field, summarize_scores
from extraction import extract_document
from normalize import bill_from_extraction

SERVER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _bill(fields=GOOD_BILL, items=GOOD_ITEMS):
    return bill_from_extraction(extract_document(make_document(fields, items)))


def test_score_field_outcomes():
    assert score_field("invoice_id", "", "X") == "skipped"
    assert score_field("invoice_id", "inv 7561", "INV-7561") == "correct"       # punctuation / case ignored
    assert score_field("invoice_id", "INV-7562", "INV-7561") == "wrong"
    assert score_field("invoice_id", "INV-7561", None) == "missing"
    assert score_field("purchase_order", "NONE", None) == "correct_absent"
    assert score_field("purchase_order", "none", "PO-1") == "spurious"
    assert score_field("invoice_date", "25/07/2025", "2025-07-25") == "correct"
    assert score_field("total_amount", "1,180.00", 1180.0) == "correct"
    assert score_field("total_amount", "1180.50", 1180.0) == "wrong"
    assert score_field("supplier_gstin", "29ckppb2626c1zc", "29CKPPB2626C1ZC") == "correct"
    assert score_field("line_item_count", "2", 2) == "correct"
    assert score_field("line_item_count", "3", 0) == "missing"


def test_summary_and_report():
    truth_ok = {"invoice_id": "INV-7561", "invoice_date": "25/07/2025", "supplier_name": "Shree Bharath Distributor",
                "total_amount": "1180", "line_item_count": "2", "purchase_order": "NONE"}
    truth_bad = dict(truth_ok, invoice_id="INV-9999", total_amount="2000")
    per_bill = {"a.jpg": score_bill(truth_ok, _bill()), "b.jpg": score_bill(truth_bad, _bill())}
    summary = summarize_scores(per_bill)

    assert summary["bills"] == 2 and summary["bills_fully_correct"] == 1
    inv = summary["fields"]["invoice_id"]
    assert (inv["evaluated"], inv["correct"], inv["wrong"], inv["accuracy"]) == (2, 1, 1, 0.5)
    assert summary["fields"]["purchase_order"]["correct_absent"] == 2
    assert summary["fields"]["sub_total"]["evaluated"] == 0
    assert summary["header"] == {"evaluated": 10, "accuracy": 0.8}
    assert summary["line_items"]["accuracy"] == 1.0

    report = render_report(summary, per_bill, {"a.jpg": [], "b.jpg": ["totals_mismatch"]}, [1200, 1800])
    assert "| Header field accuracy | ≥ 95.0% | 80.0% | FAIL |" in report
    assert "| Invoices needing manual review | ≤ 10.0% | 50.0% | FAIL |" in report
    assert "| b.jpg | invoice_id (wrong), total_amount (wrong) | totals_mismatch |" in report
    assert "a.jpg" not in report.split("## Failure cases")[1]
    assert "average 1.5s" in report


def test_cli_template_and_offline_run(tmp_path):
    bills = tmp_path / "bills"
    bills.mkdir()
    out = io.BytesIO()
    Image.new("RGB", (40, 40), "white").save(out, "JPEG")
    (bills / "one.jpg").write_bytes(out.getvalue())
    (bills / "notes.txt").write_text("ignore me")
    truth = tmp_path / "gt" / "ground_truth.csv"

    def run(*args):
        return subprocess.run([sys.executable, "tools/evaluate.py", *args], cwd=SERVER, capture_output=True,
                              text=True, encoding="utf-8", env=dict(os.environ, PYTHONIOENCODING="utf-8"))

    r = run("template", "--bills", str(bills), "--out", str(truth))
    assert r.returncode == 0, r.stderr
    rows = list(csv.DictReader(open(truth, encoding="utf-8-sig")))
    assert [row["file"] for row in rows] == ["one.jpg"] and list(rows[0]) == ["file"] + FIELDS
    assert run("template", "--bills", str(bills), "--out", str(truth)).returncode != 0  # no silent overwrite

    # Fill in the sheet and seed the Document AI cache, as a first online run would
    rows[0].update({"invoice_id": "INV-7561", "invoice_date": "25/07/2025", "total_amount": "1180.00",
                    "supplier_gstin": "29CKPPB2626C1ZC", "line_item_count": "3"})
    with open(truth, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["file"] + FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    cache = tmp_path / "gt" / "docai-cache"
    cache.mkdir()
    key = hashlib.sha256(out.getvalue()).hexdigest()[:24]
    (cache / f"{key}.json").write_text(documentai.Document.to_json(make_document(GOOD_BILL, GOOD_ITEMS)), encoding="utf-8")

    r = run("run", "--truth", str(truth), "--bills", str(bills), "--offline")
    assert r.returncode == 0, r.stderr + r.stdout
    assert "line_item_count=wrong" in r.stdout
    report = (tmp_path / "gt" / "accuracy_report.md").read_text(encoding="utf-8")
    assert "| Header field accuracy | ≥ 95.0% | 100.0% | PASS |" in report
    assert "| one.jpg | line_item_count (wrong) | — |" in report
    assert "no processing time was measured" in report
