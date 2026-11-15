"""Measure extraction accuracy against hand-checked bills (requirement letter, Phase 2).

Run from the server/ folder.

1. Create a sheet to fill in (one row per bill; open it in Excel):

     python tools/evaluate.py template --bills ../../data/ml-split/test --out ../../data/ground-truth/ground_truth.csv

   Fill each cell with what you read on the bill. Leave a cell empty to skip that
   field, or write NONE when the bill does not show it. Dates: DD/MM/YYYY.

2. Run the evaluation and write the report:

     python tools/evaluate.py run --truth ../../data/ground-truth/ground_truth.csv --bills ../../data/ml-split/test

   Each bill is sent to Document AI once and the response is saved next to the
   ground truth (docai-cache/), so later runs are free and need no connection.
   Use --offline to forbid any Document AI call.
"""
import argparse
import csv
import hashlib
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluation import FIELDS, render_report, score_bill, summarize_scores  # noqa: E402
from extraction import extract_document  # noqa: E402
from normalize import bill_from_extraction  # noqa: E402
from preprocess import UploadError, prepare_upload  # noqa: E402
from validation import validate  # noqa: E402

BILL_EXTENSIONS = (".jpg", ".jpeg", ".png", ".pdf", ".tif", ".tiff", ".webp")
# The vendor list is empty during evaluation, so "new supplier" is not an extraction problem.
IGNORED_CODES = {"new_vendor"}


def cmd_template(args):
    files = sorted(f for f in os.listdir(args.bills) if f.lower().endswith(BILL_EXTENSIONS))
    if args.limit:
        files = files[: args.limit]
    if os.path.exists(args.out) and not args.force:
        sys.exit(f"{args.out} already exists. Use --force to overwrite it.")
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["file"] + FIELDS)
        for name in files:
            writer.writerow([name] + [""] * len(FIELDS))
    print(f"Wrote {len(files)} rows to {args.out}. Fill it in, then run: python tools/evaluate.py run --truth {args.out} --bills {args.bills}")


def load_document(path, cache_dir, offline):
    """Return (Document, ocr_ms or None). Cached responses are keyed by file content."""
    from google.cloud import documentai

    data = open(path, "rb").read()
    cache_file = os.path.join(cache_dir, hashlib.sha256(data).hexdigest()[:24] + ".json")
    if os.path.exists(cache_file):
        return documentai.Document.from_json(open(cache_file, encoding="utf-8").read()), None
    if offline:
        raise FileNotFoundError("not in cache (run once without --offline)")

    import services
    content, mime_type, _ = prepare_upload([data])
    started = time.perf_counter()
    document = services.process_document(content, mime_type)
    ocr_ms = round((time.perf_counter() - started) * 1000)
    os.makedirs(cache_dir, exist_ok=True)
    with open(cache_file, "w", encoding="utf-8") as f:
        f.write(documentai.Document.to_json(document))
    return document, ocr_ms


def cmd_run(args):
    with open(args.truth, newline="", encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("file") or "").strip()]
    rows = [r for r in rows if any((r.get(field) or "").strip() for field in FIELDS)]
    if not rows:
        sys.exit("The ground truth file has no filled-in rows.")

    cache_dir = args.cache or os.path.join(os.path.dirname(os.path.abspath(args.truth)), "docai-cache")
    per_bill, exceptions, timings, skipped = {}, {}, [], []
    for row in rows:
        name = row["file"].strip()
        path = os.path.join(args.bills, name)
        if not os.path.exists(path):
            skipped.append((name, "file not found"))
            continue
        try:
            document, ocr_ms = load_document(path, cache_dir, args.offline)
        except (UploadError, FileNotFoundError) as e:
            skipped.append((name, str(e)))
            continue
        if ocr_ms is not None:
            timings.append(ocr_ms)
        bill = bill_from_extraction(extract_document(document))
        per_bill[name] = score_bill(row, bill)
        exceptions[name] = sorted({i["code"] for i in validate(bill)} - IGNORED_CODES)
        problems = [f"{f}={o}" for f, o in per_bill[name].items() if o in ("wrong", "missing", "spurious")]
        print(f"  {name}: {', '.join(problems) or 'all correct'}")

    if not per_bill:
        sys.exit("No bills could be evaluated: " + "; ".join(f"{n} ({why})" for n, why in skipped))

    summary = summarize_scores(per_bill)
    report = render_report(summary, per_bill, exceptions, timings,
                           thresholds=(args.header_target, args.exception_target))
    if skipped:
        report += "\n## Skipped\n\n" + "\n".join(f"- {n}: {why}" for n, why in skipped) + "\n"
    out = args.report or os.path.join(os.path.dirname(os.path.abspath(args.truth)), "accuracy_report.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(report)
    header = summary["header"]["accuracy"]
    print(f"\n{summary['bills']} bills evaluated, header accuracy "
          f"{'n/a' if header is None else format(header, '.1%')}. Report: {out}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    t = sub.add_parser("template", help="create an empty ground-truth sheet for a folder of bills")
    t.add_argument("--bills", required=True, help="folder with bill images / PDFs")
    t.add_argument("--out", required=True, help="CSV file to create")
    t.add_argument("--limit", type=int, help="only the first N bills")
    t.add_argument("--force", action="store_true", help="overwrite an existing file")
    t.set_defaults(func=cmd_template)

    r = sub.add_parser("run", help="score extraction against the ground truth and write a report")
    r.add_argument("--truth", required=True, help="filled-in ground-truth CSV")
    r.add_argument("--bills", required=True, help="folder with the bill files named in the CSV")
    r.add_argument("--cache", help="folder for cached Document AI responses (default: next to the CSV)")
    r.add_argument("--report", help="report file (default: accuracy_report.md next to the CSV)")
    r.add_argument("--offline", action="store_true", help="never call Document AI; use the cache only")
    r.add_argument("--header-target", type=float, default=0.95, help="required header accuracy (default 0.95)")
    r.add_argument("--exception-target", type=float, default=0.10, help="allowed share needing review (default 0.10)")
    r.set_defaults(func=cmd_run)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
