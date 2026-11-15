# Proposal: retention, archival, backup and purge of invoice records

**Status: draft for client decision.** Nothing in this document is enforced by the software yet, except where the "Today" column says so. Section 5 lists the decisions needed before it can be built.

The requirement letter asks for backup, archival and purge policies for invoice records, covering the original scans and the structured data.

## 1. What is stored

| Data | Where | Contains |
| --- | --- | --- |
| Original bill (image or PDF) | Cloud Storage, private bucket | The document as scanned |
| Structured bill | Firestore, `users/{uid}/bills` | Extracted fields, line items, validation issues, status, audit log |
| Vendor list | Firestore, `users/{uid}/vendors` | Supplier name, GSTIN, contact details |
| Exports | The user's device or wherever they share it | Copies of the above. Outside the system's control |

## 2. Proposed retention periods

Indian law sets minimum periods for keeping purchase invoices. The figures below are our understanding and **must be confirmed by the client's accountant** before adoption:

- GST law (CGST Act, section 36): 72 months from the due date of the annual return for the year the invoice belongs to.
- Companies Act, 2013 (section 128): books of account and supporting vouchers for 8 financial years.

Proposal: one period that satisfies both.

| Record | Keep for | Then |
| --- | --- | --- |
| Approved bills (original + data) | **8 financial years** after the financial year of the invoice date | Purge |
| Draft bills never approved | 12 months after scanning | Purge, after a reminder to the user |
| Deleted bills | Removed immediately (as today) | — |
| Vendor records | While the vendor has any retained bill, plus 12 months | Purge |
| Server logs | 90 days | Purge |

## 3. Archival

Bills are rarely opened after the year's accounts are closed, so older originals can move to cheaper storage without changing how the app behaves.

| Age of invoice | Storage class for the original | Effect |
| --- | --- | --- |
| Current and previous financial year | Standard | Opens instantly |
| Older than that | Coldline (or Archive) | Still opens from the app. Lower storage cost, small retrieval fee |

This is a Cloud Storage lifecycle rule on the bucket. The structured data stays in Firestore throughout, so search, Insights and exports are unaffected.

## 4. Backup and recovery

| Risk | Proposed protection | Today |
| --- | --- | --- |
| A bill is deleted by mistake | Soft delete: keep deleted bills for 30 days in a "recently deleted" list before final removal | Not built. Delete is immediate and permanent |
| A bill is edited wrongly | Audit log on each bill shows what changed and when | Built (fields changed are recorded, previous values are not) |
| Data corruption or a bad release | Firestore scheduled daily backups, kept 30 days. Point-in-time recovery for the last 7 days | Not configured |
| Original files lost or overwritten | Cloud Storage object versioning plus bucket soft-delete (30 days) | Not configured |
| Whole-project loss | Weekly export of Firestore to a bucket in a second region | Not configured |

Suggested targets: lose at most 24 hours of data (recovery point), restore within 1 working day (recovery time).

## 5. Purge process

1. A scheduled monthly job lists records past their retention date.
2. The finance lead receives the list and has 30 days to place a **hold** on any record (audit, dispute, litigation).
3. Records not on hold are purged: the original file, the structured data, and any backups as they age out.
4. The job writes a purge log (bill id, supplier, invoice number, invoice date, purge date). The log itself is kept permanently and contains no line-item detail.

## 6. Access and audit

| Control | Today | Proposed |
| --- | --- | --- |
| Who can see a bill | Only the signed-in user who scanned it | Company workspace with roles (scanner, reviewer, finance lead, read-only auditor) |
| Direct database access from the app | Blocked by Firestore and Storage rules (deploy with `firebase deploy --only firestore:rules,storage`) | Same |
| Links to original files | Expire after 1 hour (7 days inside exports) | Same |
| Change history | Per bill: scanned, edited (which fields), approved | Also record previous values, and who viewed or exported |
| Encryption | At rest and in transit, by Google Cloud default | Same. Customer-managed keys only if the client requires it |

## 7. Decisions needed from the client

1. Confirm the retention period (8 financial years proposed) with the accountant.
2. Should drafts that were never approved be purged after 12 months?
3. Is a 30-day "recently deleted" list wanted?
4. Who approves purges and places holds?
5. Does the data have to stay in India? The project's Document AI processor is in the `us` region today, so bills are processed there. Moving storage and processing to an India or other region is possible but needs to be planned.
6. Backup targets: are 24 hours (data loss) and 1 working day (restore time) acceptable?
7. Budget: backups, versioning and a second region add storage cost. For the expected volume this should be small, but it needs the billing account to be active.

## 8. What building this involves

| Item | Effort | Needs |
| --- | --- | --- |
| Storage lifecycle rule (archival) | Configuration only | Access to the Google Cloud project |
| Firestore backups, storage versioning | Configuration only | Access to the Google Cloud project, billing enabled |
| Soft delete with "recently deleted" list | Small server and app change | Decision 3 |
| Retention dates, holds and the monthly purge job | Medium server change plus a scheduled job | Decisions 1, 2, 4 |
| Roles and company workspace | Large change (data model and app) | Separate planning |
