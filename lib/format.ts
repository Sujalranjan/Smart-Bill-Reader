const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function formatMoney(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return `₹${value.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** 2025-07-25 -> 25 Jul 2025 (other text is shown as-is). */
export function formatDate(value: string | null | undefined): string {
  if (!value) return 'No date';
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!m) return value;
  return `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${m[1]}`;
}

/** 2025-07-25 -> 25/07/2025, the format users type in. */
export function toInputDate(value: string | null | undefined): string {
  const m = value ? /^(\d{4})-(\d{2})-(\d{2})$/.exec(value) : null;
  return m ? `${m[3]}/${m[2]}/${m[1]}` : value ?? '';
}

export function numberToInput(value: number | null | undefined): string {
  return value === null || value === undefined ? '' : String(value);
}

export function isoDate(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export const FIELD_LABELS: Record<string, string> = {
  invoice_id: 'Invoice No',
  invoice_date: 'Invoice Date',
  due_date: 'Due Date',
  supplier_name: 'Supplier Name',
  supplier_address: 'Supplier Address',
  supplier_gstin: 'Supplier GSTIN',
  supplier_phone: 'Supplier Phone',
  supplier_email: 'Supplier Email',
  buyer_name: 'Buyer Name',
  buyer_gstin: 'Buyer GSTIN',
  purchase_order: 'PO Reference',
  payment_terms: 'Payment Terms',
  sub_total: 'Subtotal',
  cgst_amount: 'CGST Amount',
  sgst_amount: 'SGST Amount',
  igst_amount: 'IGST Amount',
  total_tax: 'Total Tax',
  total_amount: 'Total Amount',
  line_items: 'Line Items',
};
