# Google Cloud setup: steps for the account owner

SmartBill runs on the Google Cloud project **`smart-bill-474414`**. It needs an active payment method (a "billing account") on that project before bills can be scanned. These steps take about 20 minutes.

Sign in with the Google account that owns the project for every step.

Menu names in the Google console change from time to time. If a label differs slightly, the direct links below still go to the right page.

## Part A. Steps for the account owner

### 1. Confirm the project still exists

1. Open <https://console.cloud.google.com/cloud-resource-manager>.
2. Look for **smart-bill-474414** in the list.
3. If it is not there, click **Resources pending deletion** on the same page. A project deleted in the last 30 days can be restored from there.

If the project cannot be found or restored, stop here and tell the developer. A new project would be needed, and the bill-reading model would have to be trained again.

### 2. Add a payment method

1. Open <https://console.cloud.google.com/billing>.
2. If a billing account is listed and shows as **Closed** or suspended, open it and choose **Reopen**, then add or update the payment method under **Payment method**.
3. If no billing account is listed, click **Create account** (or **Add billing account**) and fill in:
   - **Country:** India. Charges are then in INR, and 18% GST is added to the bill.
   - **Account type:** Business (enter the company's GSTIN if you want GST invoices in the company's name).
   - **Payment method:** a credit or debit card, or another method offered for India.

Notes for Indian cards:

- The card must allow online recurring payments (e-mandate). Some debit cards do not.
- Google may place a small temporary charge to verify the card. It is reversed.
- Your bank may ask you to approve the mandate by OTP.

### 3. Link the payment method to the project

1. Open <https://console.cloud.google.com/billing/linkedaccount?project=smart-bill-474414>.
2. If it says the project has no billing account, click **Link a billing account** and pick the one from step 2.
3. The page should now show the billing account's name.

### 4. Set a spending alert (recommended)

1. Open <https://console.cloud.google.com/billing/budgets>.
2. Click **Create budget**.
3. Scope: project **smart-bill-474414**. Amount: for example **₹3,000 per month**.
4. Keep the alerts at 50%, 90% and 100%, and make sure the emails go to someone who reads them.

A budget only sends emails. It does not stop spending.

### 5. Tell the developer it is done

Send the developer:

- Confirmation that steps 1 to 4 are complete.
- Whether the billing account was new or reopened.

The developer then completes Part B using the same Google account.

## Part B. Steps for the developer (after billing is active)

1. **APIs.** In <https://console.cloud.google.com/apis/dashboard?project=smart-bill-474414>, confirm these are enabled: Cloud Document AI, Cloud Firestore, Cloud Storage, Cloud Run, Cloud Build, Artifact Registry, IAM Service Account Credentials.
2. **Bill-reading model.** In <https://console.cloud.google.com/ai/document-ai/processors?project=smart-bill-474414>, confirm processor `6ecef783e423a671` exists and has a deployed version. Note any hourly hosting charge shown for deployed versions.
3. **Firebase.** In <https://console.firebase.google.com/project/smart-bill-474414>, confirm the Firestore database and the storage bucket `smart-bill-474414.firebasestorage.app` exist, and note the bucket's region.
4. **Service account.** In <https://console.cloud.google.com/iam-admin/serviceaccounts?project=smart-bill-474414>, create `smartbill-api` with the roles **Document AI API User**, **Cloud Datastore User** and **Storage Object Admin**. The old account (`document-ai-editor`) was deleted and cannot be reused.
5. **Local key.** For development only: on that service account, **Keys → Add key → JSON**. Save the file as `SmartBillApp/server/credentials.json`. Never email it or commit it.
6. **Verify.** Run one bill through the server, then follow `server/README.md` to deploy to Cloud Run and deploy the security rules.

## What it will cost

Costs depend on use. Our estimates, to be confirmed in Google's pricing calculator:

| Item | Estimate |
| --- | --- |
| Reading bills (Document AI) | About $30 per 1,000 pages. Roughly $10 to $15 a month during development, about $45 a month at 1,000 bills |
| Hosting the trained model | Possibly about $36 a month while a version is deployed. To be confirmed in step B2 |
| Database, file storage, server, sign-in | Expected to stay within Google's free allowances at this volume |
| GST | 18% on top, for an India billing account |

## If something goes wrong

| Problem | What to do |
| --- | --- |
| Card is declined | Try a credit card, or ask the bank to allow international or recurring online payments |
| "You don't have permission" | You are signed in with a different Google account. Switch to the one that owns the project |
| Project not found | See step 1, then contact the developer |
| Billing account stays "Closed" after reopening | Contact Google Cloud billing support from the billing page (**Help → Contact support**) |
