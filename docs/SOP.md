# Standard operating procedure: processing supplier bills with SmartBill

**Purpose.** A single, repeatable way to capture supplier bills so that the data reaching accounts and inventory is complete, correct and traceable to the original document.

**Applies to.** Anyone who scans, reviews or exports bills. See the [user guide](USER_GUIDE.md) for how each screen works.

> Items marked **[to confirm]** are proposals. The finance lead should set them before go-live.

## Roles

| Role | Responsibility |
| --- | --- |
| Scanner | Scans bills on the day they are received |
| Reviewer | Checks flagged bills against the original, corrects and approves |
| Finance lead | Owns the vendor list, handles blocked suppliers and duplicates, runs exports |

One person may hold more than one role. The app does not yet enforce separate roles (each sign-in has its own bills), so this separation is by procedure for now.

## 1. Scanning (daily)

1. Scan each bill on the day it arrives **[to confirm: or within 1 working day]**.
2. One bill per scan. For multi-page bills, add every page in order.
3. Check the photo before moving on: whole page visible, readable, no shadow.
4. Write "Scanned" and the date on the paper bill, then file it **[to confirm: filing location]**.
5. If the app says the bill was **approved automatically**, nothing more is needed.
6. If the review screen opens and you are not the reviewer, leave the bill. It stays under **History → To review**.

## 2. Review (daily)

Open **History → To review** and work through every bill. Aim to finish the list each day **[to confirm]**.

For each bill:

1. Open the original (tap the picture).
2. Read the "Please check" list.
3. Fix every **red** item using the original bill.
4. Check every **amber** item against the original. Correct it if wrong.
5. Even when nothing is flagged, confirm these five values: supplier name, invoice number, invoice date, total amount, number of line items.
6. Tap **Approve**.

Never approve a bill you have not compared with the original.

## 3. Exceptions

| Situation | Action |
| --- | --- |
| **Duplicate invoice** | Open both bills. If they are the same document, delete the newer scan. If the invoice number was misread, correct it. |
| **New supplier** | Check the name and GSTIN character by character before approving. This is what future bills are matched against. |
| **Name or GSTIN differs from the vendor list** | Do not approve. Refer to the finance lead, who confirms with the supplier and updates either the bill or the vendor list. |
| **Blocked supplier** | Do not approve. Refer to the finance lead. |
| **Totals do not add up and the paper bill itself is wrong** | Enter the figures exactly as printed, approve, and tell the finance lead so the supplier can be asked for a corrected bill **[to confirm]**. |
| **Unreadable or damaged bill** | Rescan. If still unreadable, type the values by hand from the paper bill. If the paper is unreadable too, ask the supplier for a copy. |
| **Handwritten changes on the bill** | Enter the corrected (handwritten) values and tell the finance lead. |
| **Not a bill (delivery note, quotation, statement)** | Delete it. Only tax invoices and bills are processed here. |
| **Scanned by mistake** | Delete it from the review screen. |

## 4. Vendor list (finance lead)

- Review new suppliers weekly **[to confirm]** in the **Vendors** tab. Complete missing details.
- Block a supplier when trading with them is suspended.
- When a supplier's GSTIN or legal name changes, update the vendor record before approving their next bill.

## 5. Export (finance lead)

1. Before exporting, check that **History → To review** is empty for the period.
2. **Scan → Export bills**, choose the period, keep **Approved bills only** on.
3. Use CSV for import into the accounting system, Excel for reading.
4. Month-end: export "Last month" within **[to confirm: 3]** working days of month end and store the file with the month's records.

## 6. Corrections after approval

1. Open the bill from **History**, make the correction, and approve again.
2. If the bill was already exported, tell the finance lead so the accounting entry is corrected too.

Every edit and approval is recorded on the bill with the time and the fields that changed (see **History** at the bottom of the review screen).

## 7. Quality checks (monthly)

The **Insights** tab shows, for all scanned bills:

- how many were approved automatically,
- how many needed review, and why,
- how many needed a correction.

The finance lead reviews these monthly **[to confirm]**. A rising "needed correction" figure, or one supplier's bills being flagged repeatedly, should be reported to the development team so extraction can be improved.

## 8. Access and security

- Sign in only with your own company Google account. Do not share sign-ins.
- Do not forward exported files outside the company. Bills contain supplier and pricing information.
- Report a lost phone to the finance lead immediately **[to confirm: and IT]**.
