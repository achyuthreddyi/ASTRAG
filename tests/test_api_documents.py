"""The synchronous half of ingestion: cheap validation, exact-byte hashing,
idempotency, and PENDING version state. The worker does the rest (rung 5).
"""

import hashlib
import uuid

import pytest

from astrag.models import DocumentVersion, VersionStatus


@pytest.fixture
def corpus_id(client):
    response = client.post("/corpora", json={"name": f"c-{uuid.uuid4()}"})
    return response.json()["id"]


def upload(client, corpus_id, content=b"On 15 March 44 BCE, Caesar was killed.", name="doc.txt"):
    return client.post(
        f"/corpora/{corpus_id}/documents", files={"file": (name, content, "text/plain")}
    )


def replace(client, document_id, content, name="doc.txt"):
    return client.put(
        f"/documents/{document_id}", files={"file": (name, content, "text/plain")}
    )


def publish(db, body):
    """Stand in for the worker: a version must leave PENDING before it can be
    replaced at all, since only one version per document may be in flight."""
    version = db.get(DocumentVersion, uuid.UUID(body["document_version_id"]))
    version.status = VersionStatus.READY
    db.commit()
    return body


def test_upload_creates_a_pending_version(client, corpus_id, db):
    response = upload(client, corpus_id)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == VersionStatus.PENDING

    version = db.get(DocumentVersion, uuid.UUID(body["document_version_id"]))
    assert version.source_hash == hashlib.sha256(b"On 15 March 44 BCE, Caesar was killed.").hexdigest()
    assert version.corpus_id == uuid.UUID(corpus_id)
    assert version.media_type == "text/plain"
    assert version.byte_size == 38


def test_uploaded_bytes_are_retrievable_from_the_artifact_store(client, corpus_id, db, store):
    body = upload(client, corpus_id, b"stored bytes").json()

    version = db.get(DocumentVersion, uuid.UUID(body["document_version_id"]))
    assert store.get(version.source_artifact_key) == b"stored bytes"


def test_the_same_bytes_twice_returns_the_existing_document(client, corpus_id):
    first = upload(client, corpus_id)
    second = upload(client, corpus_id)

    assert second.status_code == 200
    assert second.json() == first.json()


def test_the_same_bytes_in_another_corpus_is_a_distinct_document(client, corpus_id):
    other = client.post("/corpora", json={"name": f"c-{uuid.uuid4()}"}).json()["id"]

    first = upload(client, corpus_id).json()
    second = upload(client, other).json()

    assert second["document_id"] != first["document_id"]


def test_unknown_corpus_is_not_found(client):
    assert upload(client, str(uuid.uuid4())).status_code == 404


@pytest.mark.parametrize("name", ["scan.pdf", "notes.docx", "noextension"])
def test_unsupported_types_are_rejected(client, corpus_id, name):
    assert upload(client, corpus_id, b"content", name=name).status_code == 415


@pytest.mark.parametrize("content", [b"", b"   \n\t "])
def test_empty_input_is_rejected(client, corpus_id, content):
    assert upload(client, corpus_id, content).status_code == 400


def test_oversized_input_is_rejected(client, corpus_id, monkeypatch):
    from astrag.settings import get_settings

    monkeypatch.setattr(get_settings(), "max_upload_bytes", 8)
    assert upload(client, corpus_id, b"nine bytes").status_code == 413


def test_update_creates_a_new_version_of_the_same_document(client, corpus_id, db):
    created = publish(db, upload(client, corpus_id).json())

    updated = replace(client, created["document_id"], b"corrected text")

    assert updated.status_code == 201
    assert updated.json()["document_id"] == created["document_id"]
    assert updated.json()["document_version_id"] != created["document_version_id"]


def test_update_with_identical_bytes_returns_the_existing_version(client, corpus_id, db):
    """Identical bytes are not a version: no fake version is created (§2)."""
    created = publish(db, upload(client, corpus_id).json())

    unchanged = replace(client, created["document_id"], b"On 15 March 44 BCE, Caesar was killed.")

    assert unchanged.status_code == 200
    assert unchanged.json()["document_version_id"] == created["document_version_id"]


def test_update_is_rejected_while_a_replacement_is_processing(client, corpus_id, db):
    """V1 defers a second concurrent replacement rather than queueing it (§4)."""
    created = publish(db, upload(client, corpus_id).json())
    assert replace(client, created["document_id"], b"first replacement").status_code == 201

    second = replace(client, created["document_id"], b"second replacement")
    assert second.status_code == 409


def test_update_cannot_steal_bytes_owned_by_another_document(client, corpus_id, db):
    """Those bytes are already a distinct logical document in this corpus."""
    upload(client, corpus_id, b"first document")
    second = publish(db, upload(client, corpus_id, b"second document").json())

    conflict = replace(client, second["document_id"], b"first document")
    assert conflict.status_code == 409


def test_update_of_an_unknown_document_is_not_found(client):
    assert replace(client, str(uuid.uuid4()), b"content").status_code == 404
