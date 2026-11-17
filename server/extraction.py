"""Read a Document AI `Document` into plain Python data (no GCP calls here)."""


def _entity_text(doc, entity):
    text = ""
    if entity.text_anchor and entity.text_anchor.text_segments:
        for segment in entity.text_anchor.text_segments:
            text += doc.text[int(segment.start_index):int(segment.end_index)]
    elif entity.mention_text:
        text = entity.mention_text
    return " ".join(text.split())


def _normalized(entity):
    """Document AI's own typed value when it has one: float for money, ISO for dates."""
    nv = entity.normalized_value
    if nv is None:
        return None
    money = nv.money_value
    if money and (money.units or money.nanos):
        return round(money.units + money.nanos / 1e9, 2)
    d = nv.date_value
    if d and d.year and d.month and d.day:
        return f"{d.year:04d}-{d.month:02d}-{d.day:02d}"
    return None


def _location(entity):
    """Where the value sits on the bill: {"page": 0-based, "box": [x0, y0, x1, y1]} as fractions
    of the page size, or None. Several boxes on the same page are merged into one."""
    anchor = entity.page_anchor
    if not anchor or not anchor.page_refs:
        return None
    page, xs, ys = None, [], []
    for ref in anchor.page_refs:
        ref_page = int(ref.page or 0)
        if page is None:
            page = ref_page
        if ref_page != page:
            continue
        for v in ref.bounding_poly.normalized_vertices:
            xs.append(v.x)
            ys.append(v.y)
    if not xs:
        return None
    clamp = lambda v: round(min(1.0, max(0.0, float(v))), 4)  # noqa: E731
    box = [clamp(min(xs)), clamp(min(ys)), clamp(max(xs)), clamp(max(ys))]
    if box[2] <= box[0] or box[3] <= box[1]:
        return None
    return {"page": page, "box": box}


def merge_locations(locations):
    """Smallest box covering all locations that are on the first location's page."""
    locations = [loc for loc in locations if loc]
    if not locations:
        return None
    page = locations[0]["page"]
    same = [loc["box"] for loc in locations if loc["page"] == page]
    return {"page": page, "box": [min(b[0] for b in same), min(b[1] for b in same),
                                  max(b[2] for b in same), max(b[3] for b in same)]}


def extract_document(doc):
    """Return {"entities": {type: {text, confidence, normalized, location}}, "line_items": [...], "page_count"}.

    If an entity type appears more than once, the most confident one wins.
    Each line item is {property_name: text, "_location": location}; a line_item entity
    holding several descriptions is split into several rows (matched by position).
    """
    entities = {}
    line_items = []

    for entity in doc.entities:
        etype = entity.type_
        if etype == "line_item":
            columns, places = {}, {}
            for prop in entity.properties:
                name = prop.type_.split("/", 1)[-1]
                columns.setdefault(name, []).append(_entity_text(doc, prop))
                places.setdefault(name, []).append(_location(prop))
            rows = max((len(v) for v in columns.values()), default=0)
            whole = _location(entity)
            for i in range(rows):
                row = {name: values[i] if i < len(values) else None for name, values in columns.items()}
                if rows == 1:
                    row_location = whole or merge_locations([loc for locs in places.values() for loc in locs])
                else:
                    row_location = merge_locations([locs[i] for locs in places.values() if i < len(locs)])
                row["_location"] = row_location
                line_items.append(row)
            continue

        text = _entity_text(doc, entity)
        if not text:
            continue
        current = entities.get(etype)
        confidence = float(entity.confidence) if entity.confidence else None
        if current is None or (confidence or 0) > (current["confidence"] or 0):
            entities[etype] = {"text": text, "confidence": confidence, "normalized": _normalized(entity),
                               "location": _location(entity)}

    return {"entities": entities, "line_items": line_items, "page_count": len(doc.pages) or 1}
