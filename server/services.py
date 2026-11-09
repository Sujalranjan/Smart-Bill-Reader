"""Google Cloud / Firebase clients, created on first use (tests replace them with fakes)."""
import logging
import os
from datetime import timedelta
from urllib.parse import unquote

log = logging.getLogger("smartbill")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "smart-bill-474414")
LOCATION = os.environ.get("DOCAI_LOCATION", "us")
PROCESSOR_ID = os.environ.get("DOCAI_PROCESSOR_ID", "6ecef783e423a671")
STORAGE_BUCKET = os.environ.get("STORAGE_BUCKET", "smart-bill-474414.firebasestorage.app")

_state = {}


def _credentials():
    if "creds" in _state:
        return _state["creds"]
    # Local development convenience: use server/credentials.json if present.
    # On Cloud Run leave GOOGLE_APPLICATION_CREDENTIALS unset (service identity is used).
    local_key = os.path.join(BASE_DIR, "credentials.json")
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") and os.path.exists(local_key):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = local_key

    import firebase_admin
    import google.auth
    from firebase_admin import credentials
    from google.oauth2 import service_account

    scopes = ["https://www.googleapis.com/auth/cloud-platform"]
    key_file = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if key_file:
        fb_cred = credentials.Certificate(key_file)
        gcp_creds = service_account.Credentials.from_service_account_file(key_file, scopes=scopes)
    else:
        fb_cred = credentials.ApplicationDefault()
        gcp_creds, _ = google.auth.default(scopes=scopes)

    if not firebase_admin._apps:
        firebase_admin.initialize_app(fb_cred, {"storageBucket": STORAGE_BUCKET, "projectId": PROJECT_ID})
    _state["creds"] = gcp_creds
    return gcp_creds


def db():
    if "db" not in _state:
        _credentials()
        from firebase_admin import firestore
        _state["db"] = firestore.client()
    return _state["db"]


def bucket():
    if "bucket" not in _state:
        _credentials()
        from firebase_admin import storage
        _state["bucket"] = storage.bucket()
    return _state["bucket"]


def process_document(content: bytes, mime_type: str):
    """Run the Document AI processor and return the `Document`."""
    from google.cloud import documentai
    if "docai" not in _state:
        _state["docai"] = documentai.DocumentProcessorServiceClient(
            credentials=_credentials(),
            client_options={"api_endpoint": f"{LOCATION}-documentai.googleapis.com"},
        )
    client = _state["docai"]
    name = client.processor_path(PROJECT_ID, LOCATION, PROCESSOR_ID)
    raw = documentai.RawDocument(content=content, mime_type=mime_type)
    return client.process_document(request=documentai.ProcessRequest(name=name, raw_document=raw)).document


def verify_id_token(token: str) -> str:
    _credentials()
    from firebase_admin import auth
    return auth.verify_id_token(token)["uid"]


def signed_url(blob_path: str, hours: int) -> str:
    """Short-lived link to a private bill file."""
    if not blob_path:
        return ""
    import google.auth.transport.requests
    from google.oauth2 import service_account

    creds = _credentials()
    kwargs = {"version": "v4", "expiration": timedelta(hours=hours), "method": "GET"}
    if not isinstance(creds, service_account.Credentials):
        # Cloud Run credentials have no private key: sign through the IAM API
        # (needs roles/iam.serviceAccountTokenCreator for the service account on itself).
        if not creds.valid:
            creds.refresh(google.auth.transport.requests.Request())
        kwargs["service_account_email"] = creds.service_account_email
        kwargs["access_token"] = creds.token
    try:
        return bucket().blob(blob_path).generate_signed_url(**kwargs)
    except Exception:
        log.exception("Could not sign URL for %s", blob_path)
        return ""


def legacy_image_path(image_url: str) -> str:
    """Older bills stored a public URL instead of the storage path."""
    prefix = f"https://storage.googleapis.com/{STORAGE_BUCKET}/"
    return unquote(image_url[len(prefix):]) if image_url and image_url.startswith(prefix) else ""
