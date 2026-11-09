# SmartBill server

A Flask API that the mobile app calls. It:

- checks the Firebase ID token on every request,
- sends the uploaded bill to Document AI for extraction,
- saves the result in Firestore under `users/{uid}/bills`,
- stores the original file **privately** in Cloud Storage. The app only gets short-lived signed links to it.

### Bill workflow

1. **Scan.** The app uploads a bill. The server extracts it, converts amounts to numbers and dates to `YYYY-MM-DD`, validates it, and saves it with status `draft`.
2. **Review.** The app shows the extracted data together with a list of *issues*:
   - **Errors** block approval: missing invoice number, date, supplier or total; unreadable date or total; a duplicate invoice (same number from the same supplier).
   - **Warnings** are shown, but the user can still approve: totals that don't add up, line quantity × rate ≠ amount, invalid GSTIN check digit, future or very old dates, and low OCR confidence (below 70%).
3. **Correct.** The user edits fields. Editing an approved bill sends it back to `draft`, and every edit is recorded in the bill's `audit` list.
4. **Approve.** The bill is approved once no errors remain.
5. **Export.** CSV and JSON exports have one row per line item and are meant for import into accounting software. The Excel export has summary sheets plus a sheet per supplier.

| Endpoint | Purpose |
| --- | --- |
| `POST /scan-bill` | multipart field `image`: one JPEG/PNG/TIFF/WEBP/PDF, or up to 10 photos (pages of one bill, merged into a PDF). Max 25 MB. Returns the new bill. |
| `GET /bills` | the user's bills (summary), newest first |
| `GET /bills/<id>` | full bill with issues, audit log and a 1-hour link to the original file |
| `PUT /bills/<id>` | save corrections: `{"header": {...}, "totals": {...}, "line_items": [...]}` |
| `POST /bills/<id>/approve` | approve; `409` with the issues if errors remain |
| `DELETE /bills/<id>` | delete the bill and its file |
| `GET /export?format=xlsx\|csv\|json&status=all\|approved&from=YYYY-MM-DD&to=YYYY-MM-DD` | export |
| `GET /healthz` | health check |
| `GET /get-history`, `GET /export-bills` | kept for app builds released before the review workflow |

Bills saved by the first server version (flat OCR strings) are converted when they're read. They're stored in the new format the first time they are edited or approved.

Code layout: `app.py` (routes), `extraction.py` (Document AI → plain data), `normalize.py` (numbers, dates, GSTIN, schema), `validation.py` (checks), `preprocess.py` (file type, rotation, multi-page), `exporters.py`, `services.py` (Google Cloud clients).

## Tests

The tests use in-memory fakes for Firestore, Storage, Auth and Document AI, so they don't need a Google Cloud account:

```bash
pip install -r requirements-dev.txt
python -m pytest tests
```

## Run locally (development)

```bash
cd server
python -m venv .venv
.venv\Scripts\activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python app.py                  # listens on http://0.0.0.0:5000
```

Locally the server uses `server/credentials.json` (a service-account key). This file is git-ignored. **Never commit it or put it in the app folder.**

Set the app's `EXPO_PUBLIC_API_URL` (in `SmartBillApp/.env.local`) to `http://<your-PC-LAN-IP>:5000`. The Flask debugger is always off, even locally.

## Deploy to Cloud Run (production)

One-time setup. Run these in Cloud Shell or anywhere `gcloud` is installed and logged in:

```bash
PROJECT=smart-bill-474414
SA=smartbill-api@$PROJECT.iam.gserviceaccount.com

gcloud config set project $PROJECT
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com iamcredentials.googleapis.com

gcloud iam service-accounts create smartbill-api --display-name "SmartBill API"
for ROLE in roles/documentai.apiUser roles/datastore.user roles/storage.objectAdmin; do
  gcloud projects add-iam-policy-binding $PROJECT --member serviceAccount:$SA --role $ROLE
done
# Lets the service sign image URLs without a key file
gcloud iam service-accounts add-iam-policy-binding $SA --member serviceAccount:$SA --role roles/iam.serviceAccountTokenCreator
```

Deploy (run again after each change), from the `server/` folder:

```bash
gcloud run deploy smartbill-api --source . --region asia-south1 --service-account $SA --allow-unauthenticated --memory 1Gi --timeout 120
```

`--allow-unauthenticated` is required because the app authenticates with Firebase ID tokens. The API rejects requests that don't carry a valid token.

The command prints a URL such as `https://smartbill-api-xxxxx.a.run.app`. Put it in the app build (see the app README section "Pointing the app at the server").

No key file is uploaded: `.dockerignore` excludes it, and on Cloud Run the service uses its own identity.

## Cleaning up older uploads

Earlier versions made every bill image public. To find those images (dry run), then lock them down:

```bash
python scripts/make_bills_private.py
python scripts/make_bills_private.py --apply
```

Old Firestore records keep working: the server works out the file path from the old public URL and signs it.

## If the key was ever shared

If `credentials.json` was ever shared (sent to someone, included in a zip, or pushed to Git), create a new key and delete the old one in **IAM → Service Accounts → Keys**.
