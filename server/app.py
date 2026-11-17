"""SmartBill API.

Flow: scan -> extracted bill saved as "draft" with validation issues -> user reviews and
corrects it in the app -> user approves it -> approved bills are exported for accounting.

Local development: `python app.py`. Production: gunicorn on Cloud Run (see Dockerfile).
"""
import io
import logging
import os
import time
import uuid
from datetime import date, datetime, timezone

from flask import Flask, jsonify, request, send_file
from werkzeug.exceptions import HTTPException

import exporters
import reports
import services
import pages as page_images
import vendors
from extraction import extract_document
from normalize import (SCHEMA_VERSION, InvalidValue, apply_edits, bill_from_extraction,
                       bill_from_legacy, duplicate_key, is_iso_date)
from preprocess import EXTENSIONS, UploadError, prepare_upload
from validation import summarize, validate

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("smartbill")

MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "25"))
APP_IMAGE_LINK_HOURS = int(os.environ.get("APP_IMAGE_LINK_HOURS", "1"))
EXPORT_IMAGE_LINK_HOURS = 24 * 7  # 7 days is the maximum for V4 signed URLs
# Standard invoices (no issues, known supplier, confident OCR) are approved without manual review.
AUTO_APPROVE = os.environ.get("AUTO_APPROVE", "true").lower() in ("1", "true", "yes")
AUTO_APPROVE_MIN_CONFIDENCE = float(os.environ.get("AUTO_APPROVE_MIN_CONFIDENCE", "0.9"))

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
app.json.ensure_ascii = False


# --- helpers -------------------------------------------------------------------------

def _now():
    return datetime.now(timezone.utc)


def _server_timestamp():
    from firebase_admin import firestore
    return firestore.SERVER_TIMESTAMP


def get_user_id_from_token(req):
    auth_header = req.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    try:
        return services.verify_id_token(auth_header[len("Bearer "):])
    except Exception as e:
        log.warning("Rejected auth token: %s", e)
        return None


def _bills(uid):
    return services.db().collection("users").document(uid).collection("bills")


def _vendors(uid):
    return services.db().collection("users").document(uid).collection("vendors")


def lookup_vendor(uid, header):
    """Compare the bill's supplier with the user's vendor master list."""
    from google.cloud.firestore_v1.base_query import FieldFilter
    vid = vendors.vendor_id(header)
    by_id = None
    if vid:
        snap = _vendors(uid).document(vid).get()
        by_id = dict(snap.to_dict(), id=snap.id) if snap.exists else None
    by_name = []
    key = vendors.name_key(header.get("supplier_name"))
    if by_id is None and key:
        by_name = [dict(m.to_dict(), id=m.id)
                   for m in _vendors(uid).where(filter=FieldFilter("name_key", "==", key)).stream()]
    return vendors.match_vendor(header, by_id, by_name)


def record_vendor(uid, bill):
    """Add or update the supplier in the vendor master list when a bill is approved."""
    match = lookup_vendor(uid, bill["header"])
    if match["status"] == "unknown":
        return
    existing = match["vendor"]
    if existing:
        vid = existing["id"]
        data = vendors.record_bill({k: v for k, v in existing.items() if k != "id"}, bill["header"], bill["id"], _now())
    else:
        vid = vendors.vendor_id(bill["header"])
        data = vendors.vendor_from_bill(bill["header"], bill["id"], _now())
    _vendors(uid).document(vid).set(data)


def _jsonable(value):
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _guess_mime(path):
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return next((m for m, e in EXTENSIONS.items() if e == ext), "image/jpeg")


def load_bill(snapshot):
    """Firestore document -> bill dict (schema v2), converting first-version bills on the fly."""
    data = snapshot.to_dict() or {}
    if data.get("schema_version") == SCHEMA_VERSION:
        bill = data
    else:
        bill = bill_from_legacy(data)
        bill["image_path"] = services.legacy_image_path(data.get("image_url", ""))
        bill["mime_type"] = _guess_mime(bill["image_path"])
        bill["status"] = "draft"
        bill["timestamp"] = data.get("timestamp")
        bill["issues"] = validate(bill)
        bill.update(summarize(bill["issues"]))
    bill["id"] = snapshot.id
    return bill


def find_duplicates(uid, key, exclude_id=None):
    if not key:
        return []
    from google.cloud.firestore_v1.base_query import FieldFilter
    matches = _bills(uid).where(filter=FieldFilter("dup_key", "==", key)).stream()
    return [m.id for m in matches if m.id != exclude_id]


def revalidate(uid, bill, exclude_id=None):
    bill["dup_key"] = duplicate_key(bill["header"])
    match = lookup_vendor(uid, bill["header"])
    bill["vendor_status"] = match["status"]
    bill["issues"] = validate(bill, find_duplicates(uid, bill["dup_key"], exclude_id), vendor_match=match)
    bill.update(summarize(bill["issues"]))


def can_auto_approve(bill):
    if not AUTO_APPROVE or bill["issue_count"] or bill.get("vendor_status") != "match":
        return False
    confidences = list((bill.get("confidence") or {}).values())
    return bool(confidences) and min(confidences) >= AUTO_APPROVE_MIN_CONFIDENCE


def summary(bill, with_image=True):
    h, t = bill["header"], bill["totals"]
    is_image = (bill.get("mime_type") or "").startswith("image/")
    return {
        "id": bill["id"],
        "status": bill.get("status", "draft"),
        "supplier": h.get("supplier_name") or "Unknown supplier",
        "invoice_id": h.get("invoice_id"),
        "invoice_date": h.get("invoice_date"),
        "total": t.get("total_amount"),
        "items_count": len(bill["line_items"]),
        "issue_count": bill.get("issue_count", 0),
        "error_count": bill.get("error_count", 0),
        "mime_type": bill.get("mime_type"),
        "auto_approved": bool((bill.get("metrics") or {}).get("auto_approved")) and bill.get("status") == "approved",
        "image": services.signed_url(bill.get("image_path"), APP_IMAGE_LINK_HOURS) if with_image and is_image else "",
        "scanned_at": bill.get("timestamp"),
    }


def page_views(bill, image_url):
    """Images of each page for the review screen, as short-lived links.

    Bills scanned before page images existed fall back to the original file when it is
    a photo; for older PDFs the list is empty and the app offers to open the PDF instead.
    """
    stored = bill.get("pages") or []
    if stored:
        return [{"url": services.signed_url(p["path"], APP_IMAGE_LINK_HOURS),
                 "width": p.get("width"), "height": p.get("height")} for p in stored]
    if (bill.get("mime_type") or "").startswith("image/") and image_url:
        return [{"url": image_url, "width": None, "height": None}]
    return []


def store_page_images(uid, blob_path, content, mime_type):
    """Save displayable page images next to the original. Never fails the scan."""
    try:
        if mime_type in page_images.DISPLAYABLE:
            width, height = page_images.image_size(content)
            return [{"path": blob_path, "width": width, "height": height}]
        stored = []
        stem = blob_path.rsplit(".", 1)[0]
        for n, page in enumerate(page_images.render_pages(content, mime_type), 1):
            path = f"{stem}-p{n}.jpg"
            services.bucket().blob(path).upload_from_string(page.data, content_type="image/jpeg")
            stored.append({"path": path, "width": page.width, "height": page.height})
        return stored
    except Exception:
        log.exception("Could not create page images for %s", blob_path)
        return []


def detail(bill):
    out = {k: v for k, v in bill.items() if k not in ("raw", "dup_key", "audit", "pages")}
    out["image_url"] = services.signed_url(bill.get("image_path"), APP_IMAGE_LINK_HOURS)
    out["pages"] = page_views(bill, out["image_url"])
    out["locations"] = bill.get("locations") or {}
    out["audit"] = bill.get("audit", [])
    return _jsonable(out)


def _stored(bill):
    return {k: v for k, v in bill.items() if k not in ("id", "image_url")}


def _get_owned_bill(uid, bill_id):
    ref = _bills(uid).document(bill_id)
    snapshot = ref.get()
    if not snapshot.exists:
        return ref, None
    return ref, load_bill(snapshot)


def _unauthorized():
    return jsonify({"message": "Please sign in again."}), 401


# --- error handlers ------------------------------------------------------------------

@app.errorhandler(413)
def too_large(_e):
    return jsonify({"message": f"Upload is too large. Maximum is {MAX_UPLOAD_MB} MB."}), 413


@app.errorhandler(Exception)
def unexpected(e):
    if isinstance(e, HTTPException):
        return jsonify({"message": e.description}), e.code
    log.exception("Unhandled error")
    return jsonify({"message": "Something went wrong. Please try again."}), 500


@app.route("/healthz", methods=["GET"])
def healthz():
    return jsonify({"status": "ok"}), 200


# --- scanning ------------------------------------------------------------------------

@app.route("/scan-bill", methods=["POST"])
def scan_bill():
    """Upload one image, one PDF, or several photos (pages of the same bill) as `image`."""
    uid = get_user_id_from_token(request)
    if not uid:
        return _unauthorized()

    uploads = request.files.getlist("image")
    try:
        content, mime_type, pages = prepare_upload([f.read() for f in uploads])
    except UploadError as e:
        return jsonify({"message": e.message}), e.status

    names = [os.path.basename(f.filename or "") for f in uploads if f.filename]
    file_name = names[0] if len(names) == 1 else f"{len(uploads)}-page scan.pdf"
    log.info("Processing %s (%s, %d bytes) for user %s", file_name, mime_type, len(content), uid)

    started = time.perf_counter()
    document = services.process_document(content, mime_type)
    ocr_ms = round((time.perf_counter() - started) * 1000)
    extracted = extract_document(document)
    bill = bill_from_extraction(extracted)

    found = sum(1 for v in (bill["totals"]["total_amount"], bill["header"]["supplier_name"],
                            bill["line_items"], bill["header"]["supplier_gstin"],
                            bill["header"]["invoice_id"]) if v)
    if found < 2:
        return jsonify({"message": "This doesn't look like a bill. Try a clearer photo of the whole page."}), 422

    blob_path = f"bills/{uid}/{uuid.uuid4()}.{EXTENSIONS[mime_type]}"
    services.bucket().blob(blob_path).upload_from_string(content, content_type=mime_type)
    stored_pages = store_page_images(uid, blob_path, content, mime_type)

    bill.update({
        "file_name": file_name,
        "mime_type": mime_type,
        "page_count": pages or extracted["page_count"],
        "image_path": blob_path,
        "pages": stored_pages,
        "status": "draft",
        "audit": [{"action": "scanned", "at": _now(), "by": uid}],
    })
    revalidate(uid, bill)

    auto = can_auto_approve(bill)
    if auto:
        bill["status"] = "approved"
        bill["approved_at"] = _now()
        bill["audit"].append({"action": "auto_approved", "at": _now(), "by": "system"})
    bill["metrics"] = {
        "ocr_ms": ocr_ms,
        "total_ms": round((time.perf_counter() - started) * 1000),
        "pages": bill["page_count"],
        "initial_issue_codes": sorted({i["code"] for i in bill["issues"]}),
        "initial_error_count": bill["error_count"],
        "auto_approved": auto,
    }

    stored = dict(_stored(bill), timestamp=_server_timestamp(), updated_at=_server_timestamp())
    _, ref = _bills(uid).add(stored)
    bill["id"] = ref.id
    bill["timestamp"] = _now()
    if auto:
        record_vendor(uid, bill)
    log.info("Saved bill %s for user %s (%d issues, auto_approved=%s, ocr=%dms)",
             ref.id, uid, bill["issue_count"], auto, ocr_ms)

    return jsonify({
        "status": "success",
        "message": ("Bill scanned and approved automatically." if auto
                    else "Bill scanned. Please review it before approving."),
        "auto_approved": auto,
        "id": ref.id,
        "bill": detail(bill),
    }), 201


# --- review --------------------------------------------------------------------------

@app.route("/bills", methods=["GET"])
def list_bills():
    uid = get_user_id_from_token(request)
    if not uid:
        return _unauthorized()
    from firebase_admin import firestore
    snapshots = _bills(uid).order_by("timestamp", direction=firestore.Query.DESCENDING).limit(500).stream()
    return jsonify({"bills": [_jsonable(summary(load_bill(s))) for s in snapshots]}), 200


@app.route("/bills/<bill_id>", methods=["GET"])
def get_bill(bill_id):
    uid = get_user_id_from_token(request)
    if not uid:
        return _unauthorized()
    _, bill = _get_owned_bill(uid, bill_id)
    if bill is None:
        return jsonify({"message": "Bill not found."}), 404
    return jsonify({"bill": detail(bill)}), 200


@app.route("/bills/<bill_id>", methods=["PUT"])
def update_bill(bill_id):
    """Save corrections: {"header": {...}, "totals": {...}, "line_items": [...]} (all optional)."""
    uid = get_user_id_from_token(request)
    if not uid:
        return _unauthorized()
    ref, bill = _get_owned_bill(uid, bill_id)
    if bill is None:
        return jsonify({"message": "Bill not found."}), 404

    edits = request.get_json(silent=True) or {}
    try:
        changed = apply_edits(bill, edits)
    except InvalidValue as e:
        return jsonify({"message": e.message, "field": e.field}), 400

    if changed:
        bill["status"] = "draft"  # an edited bill must be approved again
        bill.pop("approved_at", None)
        bill.setdefault("audit", []).append({"action": "edited", "at": _now(), "by": uid, "fields": sorted(changed)})
    revalidate(uid, bill, exclude_id=bill_id)
    bill["schema_version"] = SCHEMA_VERSION
    ref.set(dict(_stored(bill), updated_at=_server_timestamp()))
    return jsonify({"bill": detail(bill), "changed": sorted(changed)}), 200


@app.route("/bills/<bill_id>/approve", methods=["POST"])
def approve_bill(bill_id):
    uid = get_user_id_from_token(request)
    if not uid:
        return _unauthorized()
    ref, bill = _get_owned_bill(uid, bill_id)
    if bill is None:
        return jsonify({"message": "Bill not found."}), 404

    revalidate(uid, bill, exclude_id=bill_id)
    errors = [i for i in bill["issues"] if i["severity"] == "error"]
    if errors:
        return jsonify({"message": "Fix the highlighted problems before approving.",
                        "bill": detail(bill)}), 409

    bill["status"] = "approved"
    bill["approved_at"] = _now()
    bill["schema_version"] = SCHEMA_VERSION
    bill.setdefault("audit", []).append({"action": "approved", "at": _now(), "by": uid})
    ref.set(dict(_stored(bill), updated_at=_server_timestamp()))
    record_vendor(uid, bill)
    return jsonify({"bill": detail(bill), "message": "Bill approved."}), 200


@app.route("/bills/<bill_id>", methods=["DELETE"])
def delete_bill(bill_id):
    uid = get_user_id_from_token(request)
    if not uid:
        return _unauthorized()
    ref, bill = _get_owned_bill(uid, bill_id)
    if bill is None:
        return jsonify({"message": "Bill not found."}), 404
    paths = {bill.get("image_path")} | {p.get("path") for p in bill.get("pages") or []}
    for path in sorted(p for p in paths if p):
        try:
            services.bucket().blob(path).delete()
        except Exception:
            log.warning("Could not delete file %s", path)
    ref.delete()
    log.info("Deleted bill %s for user %s", bill_id, uid)
    return jsonify({"message": "Bill deleted."}), 200


# --- vendor master -------------------------------------------------------------------

def _vendor_json(snapshot):
    data = snapshot.to_dict() or {}
    data.pop("bill_ids", None)
    data.pop("name_key", None)
    return _jsonable(dict(data, id=snapshot.id))


@app.route("/vendors", methods=["GET"])
def list_vendors():
    uid = get_user_id_from_token(request)
    if not uid:
        return _unauthorized()
    items = [_vendor_json(s) for s in _vendors(uid).stream()]
    items.sort(key=lambda v: (v.get("name") or "").lower())
    return jsonify({"vendors": items}), 200


@app.route("/vendors", methods=["POST"])
def create_vendor():
    uid = get_user_id_from_token(request)
    if not uid:
        return _unauthorized()
    body = request.get_json(silent=True) or {}
    try:
        data = vendors.apply_vendor_edits({"blocked": False, "bill_ids": [], "bill_count": 0,
                                           "first_seen": _now(), "last_seen": None}, body)
    except ValueError as e:
        return jsonify({"message": str(e), "field": "gstin"}), 400
    if not data.get("name"):
        return jsonify({"message": "Supplier name is required.", "field": "name"}), 400
    vid = vendors.vendor_id({"supplier_gstin": data.get("gstin"), "supplier_name": data["name"]})
    ref = _vendors(uid).document(vid)
    if ref.get().exists:
        return jsonify({"message": "This supplier is already in your vendor list."}), 409
    ref.set(data)
    return jsonify({"vendor": _vendor_json(ref.get())}), 201


@app.route("/vendors/<vendor_id>", methods=["PUT"])
def update_vendor(vendor_id):
    uid = get_user_id_from_token(request)
    if not uid:
        return _unauthorized()
    ref = _vendors(uid).document(vendor_id)
    snap = ref.get()
    if not snap.exists:
        return jsonify({"message": "Supplier not found."}), 404
    try:
        data = vendors.apply_vendor_edits(snap.to_dict(), request.get_json(silent=True) or {})
    except ValueError as e:
        return jsonify({"message": str(e), "field": "gstin"}), 400
    if not data.get("name"):
        return jsonify({"message": "Supplier name is required.", "field": "name"}), 400
    ref.set(data)
    return jsonify({"vendor": _vendor_json(ref.get())}), 200


@app.route("/vendors/<vendor_id>", methods=["DELETE"])
def delete_vendor(vendor_id):
    uid = get_user_id_from_token(request)
    if not uid:
        return _unauthorized()
    ref = _vendors(uid).document(vendor_id)
    if not ref.get().exists:
        return jsonify({"message": "Supplier not found."}), 404
    ref.delete()
    return jsonify({"message": "Supplier removed."}), 200


# --- quality report ------------------------------------------------------------------

@app.route("/reports/quality", methods=["GET"])
def quality_report():
    """Exception rate, corrections and processing time, for the Phase 2 test report."""
    uid = get_user_id_from_token(request)
    if not uid:
        return _unauthorized()
    bills = [load_bill(s) for s in _bills(uid).stream()]
    return jsonify({"report": reports.quality_report(bills)}), 200


# --- export --------------------------------------------------------------------------

def _filtered_bills(uid, status, date_from, date_to):
    bills = [load_bill(s) for s in _bills(uid).stream()]
    if status == "approved":
        bills = [b for b in bills if b.get("status") == "approved"]
    if date_from or date_to:
        def in_range(b):
            d = b["header"].get("invoice_date")
            if not is_iso_date(d):
                return False
            return (not date_from or d >= date_from) and (not date_to or d <= date_to)
        bills = [b for b in bills if in_range(b)]
    bills.sort(key=lambda b: (b["header"].get("invoice_date") or "", b["header"].get("invoice_id") or ""))
    for b in bills:
        b["image_url"] = services.signed_url(b.get("image_path"), EXPORT_IMAGE_LINK_HOURS)
    return bills


@app.route("/export", methods=["GET"])
def export():
    """?format=xlsx|csv|json &status=all|approved &from=YYYY-MM-DD &to=YYYY-MM-DD"""
    uid = get_user_id_from_token(request)
    if not uid:
        return _unauthorized()

    fmt = request.args.get("format", "xlsx").lower()
    status = request.args.get("status", "all").lower()
    date_from, date_to = request.args.get("from") or None, request.args.get("to") or None
    if fmt not in exporters.FORMATS:
        return jsonify({"message": "format must be xlsx, csv or json."}), 400
    if status not in ("all", "approved"):
        return jsonify({"message": "status must be all or approved."}), 400
    for d in (date_from, date_to):
        if d and not is_iso_date(d):
            return jsonify({"message": "Dates must be YYYY-MM-DD."}), 400

    bills = _filtered_bills(uid, status, date_from, date_to)
    if not bills:
        return jsonify({"message": "No bills match these filters."}), 404

    build, mimetype = exporters.FORMATS[fmt]
    stamp = date.today().isoformat()
    return send_file(
        io.BytesIO(build(bills)),
        mimetype=mimetype,
        as_attachment=True,
        download_name=f"SmartBill_{stamp}.{fmt}",
    )


# --- endpoints kept for app versions released before the review flow -----------------

@app.route("/export-bills", methods=["GET"])
def export_bills_legacy():
    return export()


@app.route("/get-history", methods=["GET"])
def get_history_legacy():
    uid = get_user_id_from_token(request)
    if not uid:
        return _unauthorized()
    from firebase_admin import firestore
    snapshots = _bills(uid).order_by("timestamp", direction=firestore.Query.DESCENDING).stream()
    history = []
    for s in snapshots:
        item = summary(load_bill(s))
        history.append({"id": item["id"], "supplier": item["supplier"], "date": item["invoice_date"] or "Unknown Date",
                        "total": item["total"] or 0, "image": item["image"], "items_count": item["items_count"]})
    return jsonify({"history": history}), 200


if __name__ == "__main__":
    # Local development only. The interactive debugger is never enabled.
    app.run(host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "5000")), debug=False)
