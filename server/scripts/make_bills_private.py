"""One-time cleanup: remove public access from bill images uploaded by older
versions of the server (which called blob.make_public()).

Run from the server/ folder:  python scripts/make_bills_private.py           (dry run)
                              python scripts/make_bills_private.py --apply   (make changes)
"""
import os
import sys

from google.cloud import storage

BUCKET = os.environ.get("STORAGE_BUCKET", "smart-bill-474414.firebasestorage.app")
KEY = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "credentials.json"
)


def main(apply: bool):
    client = storage.Client.from_service_account_json(KEY) if os.path.exists(KEY) else storage.Client()
    count = 0
    for blob in client.list_blobs(BUCKET, prefix="bills/"):
        acl = blob.acl
        acl.reload()
        if any(entry.get("entity") == "allUsers" for entry in acl):
            count += 1
            print(("Making private: " if apply else "Public: ") + blob.name)
            if apply:
                blob.make_private()
    print(f"{count} public bill image(s) {'fixed' if apply else 'found (dry run; pass --apply to fix)'}.")


if __name__ == "__main__":
    main("--apply" in sys.argv)
