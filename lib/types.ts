export type BillStatus = 'draft' | 'approved';

export type Severity = 'error' | 'warning';

export interface Issue {
  code: string;
  field: string;
  message: string;
  severity: Severity;
  duplicate_of?: string[];
}

export interface BillHeader {
  invoice_id: string | null;
  invoice_date: string | null;
  due_date: string | null;
  supplier_name: string | null;
  supplier_address: string | null;
  supplier_gstin: string | null;
  supplier_phone: string | null;
  supplier_email: string | null;
  buyer_name: string | null;
  buyer_gstin: string | null;
  purchase_order: string | null;
  payment_terms: string | null;
}

export interface BillTotals {
  sub_total: number | null;
  cgst_amount: number | null;
  sgst_amount: number | null;
  igst_amount: number | null;
  total_tax: number | null;
  total_amount: number | null;
}

export interface LineItem {
  description: string | null;
  hsn_sac: string | null;
  quantity: number | null;
  rate: number | null;
  discount_pct: number | null;
  cgst_pct: number | null;
  cgst_amount: number | null;
  sgst_pct: number | null;
  sgst_amount: number | null;
  amount: number | null;
}

export interface AuditEntry {
  action: 'scanned' | 'edited' | 'approved' | 'auto_approved';
  at: string;
  by: string;
  fields?: string[];
}

export interface Bill {
  id: string;
  status: BillStatus;
  header: BillHeader;
  totals: BillTotals;
  line_items: LineItem[];
  issues: Issue[];
  issue_count: number;
  error_count: number;
  warning_count: number;
  confidence: Record<string, number>;
  file_name: string | null;
  mime_type: string | null;
  page_count?: number;
  image_url: string;
  timestamp?: string;
  approved_at?: string;
  audit: AuditEntry[];
}

export interface BillSummary {
  id: string;
  status: BillStatus;
  supplier: string;
  invoice_id: string | null;
  invoice_date: string | null;
  total: number | null;
  items_count: number;
  issue_count: number;
  error_count: number;
  mime_type: string | null;
  auto_approved: boolean;
  image: string;
  scanned_at: string | null;
}

export interface Vendor {
  id: string;
  name: string | null;
  gstin: string | null;
  address: string | null;
  phone: string | null;
  email: string | null;
  blocked: boolean;
  bill_count: number;
  last_seen: string | null;
  source: 'auto' | 'manual';
}

export interface QualityReport {
  bills_total: number;
  bills_measured: number;
  approved: number;
  auto_approved: number;
  manually_approved: number;
  waiting_for_review: number;
  exception_rate: number | null;
  straight_through_rate: number | null;
  blocked_by_error_rate: number | null;
  manual_correction_rate: number | null;
  exception_reasons: { code: string; bills: number }[];
  most_corrected_fields: { field: string; bills: number }[];
  processing: { pages: number; avg_ocr_ms: number | null; p95_ocr_ms: number | null; max_ocr_ms: number | null };
}

/** What the edit form holds: everything as text, exactly as the user typed it. */
export type EditableLine = Record<keyof LineItem, string>;
