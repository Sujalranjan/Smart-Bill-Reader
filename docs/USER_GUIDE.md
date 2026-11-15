# SmartBill user guide

SmartBill turns supplier bills (paper, photos or PDFs) into checked, structured data that can be exported for accounting and inventory.

## The four tabs

| Tab | What it is for |
| --- | --- |
| **Scan** | Add a bill, and export bills |
| **History** | Every bill you have scanned, with search and filters |
| **Vendors** | Your list of known suppliers |
| **Insights** | Spending totals and processing quality |

## 1. Add a bill

On the **Scan** tab choose one of:

- **Scan with camera.** Take a photo of the bill. After each photo the app asks whether the bill has another page. Tap **Add page** for multi-page bills, or **Done** to finish. Up to 10 pages.
- **Upload photos.** Pick one photo, or several photos that are pages of the same bill.
- **Upload PDF.** Pick an e-invoice or a scanned PDF.

Tips for a good scan:

- Put the bill on a flat surface with good light and no shadow across it.
- Fit the whole page in the photo, including the totals at the bottom.
- One bill per scan. Do not photograph two bills together.

Reading a bill usually takes a few seconds.

## 2. What happens after a scan

The app checks every bill automatically. There are two outcomes:

**Approved automatically.** If the bill has no problems and comes from a supplier already in your vendor list, it is approved without any action from you. You will see a message saying so. You can still open the bill to look at it.

**Needs review.** Otherwise the review screen opens. This always happens for:

- the first bill from a new supplier,
- any bill where something is missing, does not add up, or was hard to read.

## 3. Review a bill

The review screen shows the original scan, a list of things to check, and all the extracted details.

- Tap the picture at the top to see the original bill full screen. For PDFs it opens the file.
- **Red** items must be fixed before the bill can be approved.
- **Amber** items should be checked. If the value is right, you can approve anyway.
- Fields with a problem are outlined in the same colour.

| Message | What to do |
| --- | --- |
| Invoice number / date / supplier / total is missing | Type the value from the bill |
| Could not read the date or amount | Type it. Dates are DD/MM/YYYY |
| This invoice number from this supplier has already been scanned | It is a duplicate. Delete this bill, or correct the invoice number if it was read wrongly |
| Supplier is blocked in your vendor list | Do not approve. Speak to your supervisor, or unblock the supplier in the Vendors tab |
| Subtotal + tax does not equal total | Compare the totals with the bill and correct the wrong figure |
| Line items do not match the bill total | Check for a missing or misread line. Use **Add line** or correct the amounts |
| Quantity × rate does not match amount | Check that line's quantity, rate and amount |
| Not a valid GSTIN | Compare the GSTIN with the bill, character by character |
| New supplier | Check the supplier name and GSTIN carefully. They are saved to your vendor list when you approve |
| GSTIN is registered under a different name / different GSTIN for this supplier | Confirm which is right. Correct the bill, or update the supplier in the Vendors tab |
| Low reading confidence | The app was unsure. Compare that value with the bill |

To correct something, tap the field and type. For line items you can edit any value, remove a line with the bin icon, or tap **Add line**.

Then:

- **Save** keeps your corrections without approving.
- **Approve** (or **Save & Approve**) confirms the bill is correct.
- **Delete this bill** removes the scan and its data permanently.

If you change an approved bill, it goes back to "to review" and must be approved again. The **History** section at the bottom of the screen shows when the bill was scanned, edited and approved.

## 4. Find a bill

On the **History** tab:

- Type in the search box to find a bill by supplier, invoice number or amount.
- Use **All / To review / Approved** to filter. The number next to "To review" is how many bills are waiting.
- Tap a bill to open it.

Status labels:

| Label | Meaning |
| --- | --- |
| Needs fixing | Has red problems. Cannot be approved yet |
| Check | Has amber items to look at |
| Ready to approve | No problems found, waiting for your approval |
| Approved | Approved by a person |
| Auto-approved | Approved automatically |

## 5. Manage suppliers

The **Vendors** tab lists every supplier you have approved a bill from.

- Suppliers are added automatically. You can also add one with the **+** button.
- Tap a supplier to correct its details.
- Turn on **Block this supplier** to stop its bills from being approved.
- Removing a supplier does not delete its bills. Its next bill will be treated as a new supplier.

## 6. Export

On the **Scan** tab tap **Export bills**, then choose:

- **Format.** Excel for reading and sharing. CSV for importing into accounting software (one row per line item). JSON for system integration.
- **Invoice date.** All time, this month, last month, this financial year or last financial year.
- **Approved bills only.** Leave this on for anything that goes into the accounts.

Tap **Share** to send the file (email, WhatsApp, Drive), or **Save to device** on Android.

Links to the original bill inside an export work for 7 days. After that, open the bill in the app to see the original.

## Problems

| Problem | What to try |
| --- | --- |
| "Could not reach the server" | Check your internet connection and try again |
| "This doesn't look like a bill" | Retake the photo with the whole page visible and in focus |
| "Unsupported file type" | Use a JPEG or PNG photo, a TIFF, or a PDF |
| "Upload is too large" | Scan fewer pages at once, or use a smaller PDF (limit 25 MB) |
| "Please sign in again" | Sign out with the icon at the top right of the Scan tab, then sign in again |
