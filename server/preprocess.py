"""Prepare uploaded files for Document AI.

- Detects the real file type from its bytes (never trusts the filename).
- Fixes photo rotation from EXIF and shrinks very large photos.
- Combines several photos (pages of one bill) into a single PDF.

Deskewing, de-noising and orientation of the page contents are handled by
Document AI's own OCR, so they are not repeated here.
"""
import io

from PIL import Image, ImageOps

MAX_PAGES = 10            # Document AI processes up to 15 pages per synchronous request
MAX_IMAGE_SIDE = 3000     # px; larger photos are scaled down (saves upload time, no OCR loss)

EXTENSIONS = {
    "image/jpeg": "jpg", "image/png": "png", "image/tiff": "tiff", "image/webp": "webp",
    "image/gif": "gif", "image/bmp": "bmp", "application/pdf": "pdf",
}


class UploadError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def detect_mime_type(data: bytes):
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"%PDF"):
        return "application/pdf"
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return "image/tiff"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data.startswith(b"BM"):
        return "image/bmp"
    return None


def _open_image(data):
    try:
        original = Image.open(io.BytesIO(data))
        image = ImageOps.exif_transpose(original)
    except Exception as e:
        raise UploadError("One of the images could not be opened. It may be damaged.") from e
    changed = original.getexif().get(0x0112, 1) != 1  # EXIF orientation tag said "rotate"
    if max(image.size) > MAX_IMAGE_SIDE:
        image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
        changed = True
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    return image, changed


def prepare_upload(files):
    """files: list of raw bytes. Returns (content, mime_type, page_count_hint)."""
    files = [f for f in files if f]
    if not files:
        raise UploadError("No file was uploaded.")
    if len(files) > MAX_PAGES:
        raise UploadError(f"A bill can have at most {MAX_PAGES} pages.")

    types = [detect_mime_type(f) for f in files]
    if any(t is None for t in types):
        raise UploadError("Unsupported file type. Use JPEG, PNG, TIFF, WEBP or PDF.", 415)

    if len(files) == 1:
        data, mime = files[0], types[0]
        if mime in ("application/pdf", "image/tiff"):
            return data, mime, None
        image, changed = _open_image(data)
        if not changed and mime in ("image/jpeg", "image/png"):
            return data, mime, 1
        out = io.BytesIO()
        image.save(out, format="JPEG", quality=90)
        return out.getvalue(), "image/jpeg", 1

    if "application/pdf" in types:
        raise UploadError("Upload either one PDF or several photos, not both.")
    pages = [_open_image(f)[0] for f in files]
    out = io.BytesIO()
    pages[0].save(out, format="PDF", save_all=True, append_images=pages[1:], resolution=200)
    return out.getvalue(), "application/pdf", len(pages)
