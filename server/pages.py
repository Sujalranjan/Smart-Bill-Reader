"""Page images for the review screen.

The app shows the bill next to the extracted fields so a reviewer can compare them.
Phones can display JPEG and PNG directly, but not PDF or TIFF, so those are rendered
to one JPEG per page here. Field positions from Document AI are fractions of the
page size, so they line up with these images regardless of resolution.
"""
import io

from PIL import Image, ImageOps

MAX_SIDE = 2000      # px; enough to read small print when zoomed in
RENDER_DPI = 150
DISPLAYABLE = ("image/jpeg", "image/png")


class RenderedPage:
    def __init__(self, data, width, height):
        self.data, self.width, self.height = data, width, height


def _to_jpeg(image):
    image = ImageOps.exif_transpose(image)
    if max(image.size) > MAX_SIDE:
        image.thumbnail((MAX_SIDE, MAX_SIDE))
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=85)
    return RenderedPage(out.getvalue(), image.width, image.height)


def image_size(content):
    with Image.open(io.BytesIO(content)) as image:
        return image.size


def render_pages(content, mime_type, max_pages=15):
    """Return a list of RenderedPage for a PDF or a non-displayable image (TIFF, WEBP, GIF, BMP).

    JPEG and PNG are returned as an empty list: the uploaded file is shown as-is.
    """
    if mime_type in DISPLAYABLE:
        return []
    if mime_type == "application/pdf":
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(content)
        try:
            pages = []
            for index in range(min(len(pdf), max_pages)):
                page = pdf[index]
                try:
                    bitmap = page.render(scale=RENDER_DPI / 72)
                    pages.append(_to_jpeg(bitmap.to_pil()))
                finally:
                    page.close()
            return pages
        finally:
            pdf.close()

    pages = []
    with Image.open(io.BytesIO(content)) as image:
        for index in range(min(getattr(image, "n_frames", 1), max_pages)):
            image.seek(index)
            pages.append(_to_jpeg(image.copy()))
    return pages
