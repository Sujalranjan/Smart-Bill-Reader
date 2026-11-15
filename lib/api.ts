import { getAuth } from '@react-native-firebase/auth';
import * as FileSystem from 'expo-file-system/legacy';

import { API_URL } from '../constants/Config';
import type { Bill, BillSummary, QualityReport, Vendor } from './types';

export class ApiError extends Error {
  status: number;
  field?: string;
  bill?: Bill;

  constructor(message: string, status: number, body?: any) {
    super(message);
    this.status = status;
    this.field = body?.field;
    this.bill = body?.bill;
  }
}

async function authHeader(): Promise<Record<string, string>> {
  const user = getAuth().currentUser;
  if (!user) throw new ApiError('Please sign in again.', 401);
  return { Authorization: `Bearer ${await user.getIdToken()}` };
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { ...(init.headers as Record<string, string>), ...(await authHeader()) },
    });
  } catch {
    throw new ApiError('Could not reach the server. Check your internet connection.', 0);
  }
  let body: any = null;
  try {
    body = await response.json();
  } catch {
    // non-JSON response
  }
  if (!response.ok) {
    throw new ApiError(body?.message ?? `Server error (${response.status}).`, response.status, body);
  }
  return body as T;
}

export interface UploadFile {
  uri: string;
  name: string;
  mimeType: string;
}

/** Upload one PDF/image, or several photos that are pages of the same bill. */
export async function scanBill(files: UploadFile[]) {
  const form = new FormData();
  files.forEach((f) => form.append('image', { uri: f.uri, name: f.name, type: f.mimeType } as any));
  return request<{ id: string; bill: Bill; message: string; auto_approved: boolean }>('/scan-bill', { method: 'POST', body: form });
}

export async function listBills() {
  return (await request<{ bills: BillSummary[] }>('/bills')).bills;
}

export async function getBill(id: string) {
  return (await request<{ bill: Bill }>(`/bills/${encodeURIComponent(id)}`)).bill;
}

export async function updateBill(id: string, edits: object) {
  return (
    await request<{ bill: Bill }>(`/bills/${encodeURIComponent(id)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(edits),
    })
  ).bill;
}

export async function approveBill(id: string) {
  return (await request<{ bill: Bill }>(`/bills/${encodeURIComponent(id)}/approve`, { method: 'POST' })).bill;
}

export async function deleteBill(id: string) {
  await request(`/bills/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

export type VendorInput = Partial<Pick<Vendor, 'name' | 'gstin' | 'address' | 'phone' | 'email' | 'blocked'>>;

const JSON_HEADERS = { 'Content-Type': 'application/json' };

export async function listVendors() {
  return (await request<{ vendors: Vendor[] }>('/vendors')).vendors;
}

export async function createVendor(input: VendorInput) {
  return (await request<{ vendor: Vendor }>('/vendors', { method: 'POST', headers: JSON_HEADERS, body: JSON.stringify(input) })).vendor;
}

export async function updateVendor(id: string, input: VendorInput) {
  return (
    await request<{ vendor: Vendor }>(`/vendors/${encodeURIComponent(id)}`, {
      method: 'PUT',
      headers: JSON_HEADERS,
      body: JSON.stringify(input),
    })
  ).vendor;
}

export async function deleteVendor(id: string) {
  await request(`/vendors/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

export async function getQualityReport() {
  return (await request<{ report: QualityReport }>('/reports/quality')).report;
}

export type ExportFormat = 'xlsx' | 'csv' | 'json';

export interface ExportOptions {
  format: ExportFormat;
  approvedOnly: boolean;
  from?: string; // YYYY-MM-DD
  to?: string;
}

export const EXPORT_MIME: Record<ExportFormat, string> = {
  xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  csv: 'text/csv',
  json: 'application/json',
};

/** Downloads the export into the app's cache and returns the local file URI. */
export async function downloadExport(opts: ExportOptions): Promise<string> {
  const params = new URLSearchParams({ format: opts.format, status: opts.approvedOnly ? 'approved' : 'all' });
  if (opts.from) params.set('from', opts.from);
  if (opts.to) params.set('to', opts.to);

  const today = new Date().toISOString().slice(0, 10);
  const target = `${FileSystem.cacheDirectory}SmartBill_${today}.${opts.format}`;
  let result: FileSystem.FileSystemDownloadResult;
  try {
    result = await FileSystem.downloadAsync(`${API_URL}/export?${params}`, target, { headers: await authHeader() });
  } catch {
    throw new ApiError('Could not reach the server. Check your internet connection.', 0);
  }
  if (result.status !== 200) {
    let message = `Export failed (${result.status}).`;
    try {
      message = JSON.parse(await FileSystem.readAsStringAsync(target)).message ?? message;
    } catch {
      // keep default
    }
    await FileSystem.deleteAsync(target, { idempotent: true });
    throw new ApiError(message, result.status);
  }
  return result.uri;
}
