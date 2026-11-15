# SmartBill

Mobile app (Expo SDK 54 / React Native 0.81) that scans supplier invoices. A Python server reads them with Google Document AI and validates them. Standard invoices are approved automatically; the rest are reviewed and approved by a person. Approved data is exported for accounting.

```
SmartBillApp/
  app/            Expo Router screens
    (tabs)/       Scan & export, History, Vendors, Insights
    bill/[id].tsx Review screen: check, correct, approve or delete a bill
    login.tsx     Google sign-in
  components/     Shared UI (status badge, ...)
  lib/            API client, types, formatting helpers
  server/         Flask API: Document AI + Firestore + Cloud Storage (see server/README.md)
  docs/           User guide, SOP, retention policy proposal
  firestore.rules, storage.rules   Deny direct client access (see server/README.md)
```

## What the app does

1. **Capture.** Scan with the camera (multi-page bills supported), pick photos, or upload a PDF.
2. **Automatic approval.** A bill with no problems from a supplier already in the vendor list is approved without review.
3. **Review.** Every other scan opens the review screen:
   - Problems are listed at the top: red must be fixed, amber should be checked, and the matching fields are highlighted.
   - Any field or line item can be corrected, and the original scan can be opened alongside.
4. **Approve.** Approved bills are marked as such in History, which can be searched and filtered. Editing a bill again sends it back for approval.
5. **Vendors.** Suppliers are added to the vendor list on approval. They can be edited, added by hand, or blocked.
6. **Insights.** Spend totals, plus how many bills were auto-approved, needed review (and why) or needed correction.
7. **Export.** Excel, CSV or JSON, filtered by period (month or Indian financial year), optionally approved bills only. Share it or save it to the device.

For end users, see [docs/USER_GUIDE.md](docs/USER_GUIDE.md) and [docs/SOP.md](docs/SOP.md).

## Run the app in development

```bash
npm install
cp .env.example .env.local        # then edit EXPO_PUBLIC_API_URL
npx expo prebuild --clean          # regenerate android/ after dependency changes
npx expo run:android               # builds and installs the dev client
```

The app uses native modules (Firebase, Google Sign-In), so it **does not run in Expo Go**. You need a development build.

## Pointing the app at the server

The app reads the server address from `EXPO_PUBLIC_API_URL` when it is built:

- **Local development:** in `.env.local`, set `EXPO_PUBLIC_API_URL=http://<PC LAN IP>:5000`. Start the server with `python server/app.py`. Phone and PC must be on the same network.
- **EAS builds (preview/production):** point it at the Cloud Run HTTPS URL.

  ```bash
  eas env:create --name EXPO_PUBLIC_API_URL --value https://smartbill-api-xxxxx.a.run.app --environment preview --environment production --visibility plaintext
  ```

## Google Sign-In in release builds

Google Sign-In only works for app builds whose signing-certificate SHA-1 is registered in Firebase. The debug key is not enough for release builds.

1. Run `eas credentials` → Android → production and copy the **SHA-1** fingerprint. If you publish on Google Play, also copy the **App signing key** SHA-1 from Play Console → Test and release → App integrity.
2. In Firebase console → Project settings → Your apps → Android (`com.sujal.smartbillapp`), choose **Add fingerprint** and add each SHA-1.
3. Download the updated `google-services.json` and replace the one in the project root.
4. Rebuild: `eas build -p android --profile production`.

## Secrets

- `server/credentials.json` is a service-account private key. Only the server uses it, it is git-ignored, and it must never be placed in the app.
- `google-services.json` / `GoogleService-Info.plist` hold public client config, not secrets.
