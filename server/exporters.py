"""Exports of bills: flat CSV / JSON for import into accounting systems, and an Excel workbook.

`bills` is a list of dicts shaped like normalize.py's schema, each with "id",
"status" and "image_url" (a signed link, may be empty).
"""
import csv
import io
import json

import pandas as pd

from normalize import HEADER_FIELDS, LINE_FIELDS, TOTAL_FIELDS

BILL_COLUMNS = ["bill_id", "status"] + HEADER_FIELDS + TOTAL_FIELDS + ["file_name", "image_url"]
LINE_COLUMNS = BILL_COLUMNS[:2] + ["invoice_id", "invoice_date", "supplier_name", "supplier_gstin",
                                    "line_no"] + LINE_FIELDS

_LABELS = {
    "bill_id": "Bill ID", "status": "Status", "invoice_id": "Invoice No", "invoice_date": "Invoice Date",
    "due_date": "Due Date", "supplier_name": "Supplier Name", "supplier_address": "Supplier Address",
    "supplier_gstin": "Supplier GSTIN", "supplier_phone": "Supplier Phone", "supplier_email": "Supplier Email",
    "buyer_name": "Buyer Name", "buyer_gstin": "Buyer GSTIN", "purchase_order": "PO Reference",
    "payment_terms": "Payment Terms", "sub_total": "Subtotal", "cgst_amount": "CGST Amount",
    "sgst_amount": "SGST Amount", "igst_amount": "IGST Amount", "total_tax": "Total Tax",
    "total_amount": "Total Amount", "file_name": "File Name", "image_url": "Original Bill (link valid 7 days)",
    "line_no": "Line No", "description": "Item/Product Name", "hsn_sac": "HSN/SAC", "quantity": "Quantity",
    "rate": "Rate", "discount_pct": "Discount %", "cgst_pct": "CGST %", "sgst_pct": "SGST %",
    "amount": "Amount",
}


def _bill_row(bill):
    return {
        "bill_id": bill["id"], "status": bill.get("status"),
        **{f: bill["header"].get(f) for f in HEADER_FIELDS},
        **{f: bill["totals"].get(f) for f in TOTAL_FIELDS},
        "file_name": bill.get("file_name"), "image_url": bill.get("image_url"),
    }


def bill_rows(bills):
    return [_bill_row(b) for b in bills]


def line_rows(bills):
    """One row per line item; a bill without line items still gets one row."""
    rows = []
    for bill in bills:
        base = {k: v for k, v in _bill_row(bill).items() if k in LINE_COLUMNS}
        items = bill["line_items"] or [{}]
        for n, item in enumerate(items, 1):
            rows.append({**base, "line_no": n if item else None, **{f: item.get(f) for f in LINE_FIELDS}})
    return rows


def to_csv(bills):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=LINE_COLUMNS)
    writer.writeheader()
    for row in line_rows(bills):
        writer.writerow({k: "" if v is None else v for k, v in row.items()})
    # BOM so Excel opens the UTF-8 file (₹, Kannada names) correctly
    return ("﻿" + out.getvalue()).encode("utf-8")


def to_json(bills):
    payload = [{
        "id": b["id"], "status": b.get("status"), "header": b["header"], "totals": b["totals"],
        "line_items": b["line_items"], "file_name": b.get("file_name"), "image_url": b.get("image_url"),
    } for b in bills]
    return json.dumps({"bills": payload}, ensure_ascii=False, indent=2).encode("utf-8")


def _sheet_name(title, used):
    for ch in ':\\/?*[]':
        title = title.replace(ch, "")
    title = title.strip()[:31] or "Unknown Supplier"
    name, n = title, 2
    while name.lower() in used:
        suffix = f" ({n})"
        name = title[:31 - len(suffix)] + suffix
        n += 1
    used.add(name.lower())
    return name


def to_xlsx(bills):
    output = io.BytesIO()
    used = {"invoices", "line items"}
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(bill_rows(bills), columns=BILL_COLUMNS).rename(columns=_LABELS) \
            .to_excel(writer, sheet_name="Invoices", index=False)
        pd.DataFrame(line_rows(bills), columns=LINE_COLUMNS).rename(columns=_LABELS) \
            .to_excel(writer, sheet_name="Line Items", index=False)

        # One readable sheet per supplier, laid out like the paper bill.
        by_supplier = {}
        for bill in bills:
            h = bill["header"]
            key = (h.get("supplier_gstin") or "", (h.get("supplier_name") or "").strip().lower())
            by_supplier.setdefault(key, []).append(bill)

        for (gstin, _), group in by_supplier.items():
            name = group[0]["header"].get("supplier_name") or ""
            title = f"{name}_{gstin}" if name and gstin else (name or gstin or "Unknown Supplier")
            rows = []
            for bill in group:
                h, t = bill["header"], bill["totals"]
                rows += [
                    [],
                    ["--- BILL ---", "Status:", bill.get("status")],
                    ["Supplier Name:", h.get("supplier_name")],
                    ["Supplier Address:", h.get("supplier_address")],
                    ["Supplier GSTIN:", h.get("supplier_gstin")],
                    ["Invoice No:", h.get("invoice_id")],
                    ["Invoice Date:", h.get("invoice_date")],
                    ["PO Reference:", h.get("purchase_order")],
                    ["Payment Terms:", h.get("payment_terms")],
                    ["Original Bill (link valid 7 days):", bill.get("image_url")],
                    [],
                    ["S No.", "Item/Product Name", "HSN/SAC", "Quantity", "Rate", "Discount %",
                     "CGST %", "SGST %", "Amount"],
                ]
                if not bill["line_items"]:
                    rows.append(["No line items found."])
                for n, item in enumerate(bill["line_items"], 1):
                    rows.append([n, item.get("description"), item.get("hsn_sac"), item.get("quantity"),
                                 item.get("rate"), item.get("discount_pct"), item.get("cgst_pct"),
                                 item.get("sgst_pct"), item.get("amount")])
                rows += [
                    [],
                    ["", "", "", "", "", "", "", "Subtotal:", t.get("sub_total")],
                    ["", "", "", "", "", "", "", "Total CGST:", t.get("cgst_amount")],
                    ["", "", "", "", "", "", "", "Total SGST:", t.get("sgst_amount")],
                    ["", "", "", "", "", "", "", "Total IGST:", t.get("igst_amount")],
                    ["", "", "", "", "", "", "", "Total Tax:", t.get("total_tax")],
                    ["", "", "", "", "", "", "", "TOTAL AMOUNT:", t.get("total_amount")],
                ]
            pd.DataFrame(rows).to_excel(writer, sheet_name=_sheet_name(title, used), index=False, header=False)
    return output.getvalue()


FORMATS = {
    "xlsx": (to_xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    "csv": (to_csv, "text/csv"),
    "json": (to_json, "application/json"),
}
