"""Fakes for Firestore, Cloud Storage, Firebase Auth and Document AI so the API can be
tested without a Google Cloud account."""
import copy
import itertools
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import services  # noqa: E402
from firebase_admin import firestore  # noqa: E402

_ids = itertools.count(1)


def _resolve(data):
    if data is firestore.SERVER_TIMESTAMP:
        return datetime.now(timezone.utc)
    if isinstance(data, dict):
        return {k: _resolve(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_resolve(v) for v in data]
    return copy.deepcopy(data)


class Snapshot:
    def __init__(self, id_, data):
        self.id, self._data = id_, data
        self.exists = data is not None

    def to_dict(self):
        return copy.deepcopy(self._data)


class DocRef:
    def __init__(self, store, path):
        self.store, self.path = store, path
        self.id = path[-1]

    def collection(self, name):
        return Collection(self.store, self.path + (name,))

    def get(self):
        return Snapshot(self.id, self.store.get(self.path))

    def set(self, data):
        self.store[self.path] = _resolve(data)

    def delete(self):
        self.store.pop(self.path, None)


class Query:
    def __init__(self, collection, filters=(), order=None, limit=None):
        self.collection, self.filters, self.order, self._limit = collection, list(filters), order, limit

    def where(self, filter=None):
        return Query(self.collection, self.filters + [filter], self.order, self._limit)

    def order_by(self, field, direction=None):
        return Query(self.collection, self.filters, (field, direction), self._limit)

    def limit(self, n):
        return Query(self.collection, self.filters, self.order, n)

    def stream(self):
        docs = self.collection._docs()
        for f in self.filters:
            assert f.op_string == "=="
            docs = [d for d in docs if d[1].get(f.field_path) == f.value]
        if self.order:
            field, direction = self.order
            docs.sort(key=lambda d: d[1].get(field) or datetime.min.replace(tzinfo=timezone.utc),
                      reverse=direction == firestore.Query.DESCENDING)
        if self._limit:
            docs = docs[: self._limit]
        return [Snapshot(i, copy.deepcopy(d)) for i, d in docs]


class Collection(Query):
    def __init__(self, store, path):
        self.store, self.path = store, path
        super().__init__(self)

    def _docs(self):
        n = len(self.path)
        return [(p[-1], d) for p, d in self.store.items() if len(p) == n + 1 and p[:n] == self.path]

    def document(self, id_):
        return DocRef(self.store, self.path + (id_,))

    def add(self, data):
        ref = self.document(f"bill{next(_ids)}")
        ref.set(data)
        return None, ref


class FakeDB:
    def __init__(self):
        self.store = {}

    def collection(self, name):
        return Collection(self.store, (name,))


class Blob:
    def __init__(self, bucket, name):
        self.bucket, self.name = bucket, name

    def upload_from_string(self, content, content_type=None):
        self.bucket.files[self.name] = (content, content_type)

    def delete(self):
        self.bucket.files.pop(self.name, None)

    def generate_signed_url(self, **kwargs):
        return f"https://signed.example/{self.name}?X-Goog-Signature=x"


class FakeBucket:
    def __init__(self):
        self.files = {}

    def blob(self, name):
        return Blob(self, name)


@pytest.fixture
def fake_cloud(monkeypatch):
    db, bucket = FakeDB(), FakeBucket()
    state = {"document": None}
    monkeypatch.setattr(services, "db", lambda: db)
    monkeypatch.setattr(services, "bucket", lambda: bucket)
    monkeypatch.setattr(services, "verify_id_token",
                        lambda token: {"good-token": "user1", "other-token": "user2"}[token])
    monkeypatch.setattr(services, "signed_url",
                        lambda path, hours: f"https://signed.example/{path}" if path else "")
    monkeypatch.setattr(services, "process_document", lambda content, mime: state["document"])
    return {"db": db, "bucket": bucket, "state": state}
