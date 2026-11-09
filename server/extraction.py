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


def extract_document(doc):
    """Return {"entities": {type: {text, confidence, normalized}}, "line_items": [...], "page_count"}.

    If an entity type appears more than once, the most confident one wins.
    Each line item is {property_name: text}; a line_item entity holding several
    descriptions is split into several rows (matched by position).
    """
    entities = {}
    line_items = []

    for entity in doc.entities:
        etype = entity.type_
        if etype == "line_item":
            columns = {}
            for prop in entity.properties:
                name = prop.type_.split("/", 1)[-1]
                columns.setdefault(name, []).append(_entity_text(doc, prop))
            rows = max((len(v) for v in columns.values()), default=0)
            for i in range(rows):
                line_items.append({name: values[i] if i < len(values) else None for name, values in columns.items()})
            continue

        text = _entity_text(doc, entity)
        if not text:
            continue
        current = entities.get(etype)
        confidence = float(entity.confidence) if entity.confidence else None
        if current is None or (confidence or 0) > (current["confidence"] or 0):
            entities[etype] = {"text": text, "confidence": confidence, "normalized": _normalized(entity)}

    return {"entities": entities, "line_items": line_items, "page_count": len(doc.pages) or 1}
