"""Build Document AI `Document` objects like the SmartBill processor returns."""
from google.cloud import documentai


def page_box(page, box):
    x0, y0, x1, y1 = box
    vertices = [documentai.NormalizedVertex(x=x, y=y) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    return documentai.Document.PageAnchor(page_refs=[documentai.Document.PageAnchor.PageRef(
        page=page, bounding_poly=documentai.BoundingPoly(normalized_vertices=vertices))])


def make_document(fields, line_items=(), pages=1):
    """fields: {type: text or (text, confidence)}; line_items: [{prop: text}]."""
    text_parts, entities = [], []

    def anchored(etype, value, confidence=0.95):
        # Each value gets its own row on page 1: x 0.1-0.6, height 0.02, stacked downwards.
        start = sum(len(p) for p in text_parts)
        y0 = round(0.02 + len(text_parts) * 0.025, 4)
        text_parts.append(value + "\n")
        return documentai.Document.Entity(
            type_=etype, confidence=confidence, mention_text=value,
            text_anchor=documentai.Document.TextAnchor(
                text_segments=[documentai.Document.TextAnchor.TextSegment(start_index=start, end_index=start + len(value))]),
            page_anchor=page_box(0, [0.1, y0, 0.6, round(y0 + 0.02, 4)]),
        )

    for etype, value in fields.items():
        text, conf = value if isinstance(value, tuple) else (value, 0.95)
        entities.append(anchored(etype, text, conf))
    for item in line_items:
        props = [anchored(f"line_item/{k}", v) for k, v in item.items()]
        entities.append(documentai.Document.Entity(type_="line_item", properties=props, confidence=0.9))

    return documentai.Document(text="".join(text_parts), entities=entities,
                               pages=[documentai.Document.Page(page_number=i + 1) for i in range(pages)])


GOOD_BILL = {
    "invoice_id": "INV-7561",
    "invoice_date": "25-Jul-2025",
    "supplier_name": "Shree Bharath Distributor",
    "supplier_gst_number": "29CKPPB2626C1ZC",
    "sub_total": "1,000.00",
    "cgst_amount": "90.00",
    "sgst_amount": "90.00",
    "total_gst_amount": "180.00",
    "total_amount": "₹1,180.00",
}
GOOD_ITEMS = [
    {"description": "Tea Powder 1kg", "product_code": "0902", "quantity": "2", "unit_price": "300.00",
     "cgst": "9%", "sgst": "9%", "amount": "600.00"},
    {"description": "Sugar 5kg", "product_code": "1701", "quantity": "1", "unit_price": "400",
     "gst": "18", "amount": "400.00"},
]
