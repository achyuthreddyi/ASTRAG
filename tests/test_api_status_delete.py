"""The ingestion status contract and V1 deletion (§23, §25)."""

import uuid

import pytest
from sqlalchemy import select

from astrag.ingest.executor import run_once
from astrag.ingest.pipeline import STAGES
from astrag.models import Chunk, Document, DocumentVersion, VersionStatus
from test_api_documents import corpus_id, publish, replace, upload  # noqa: F401 — fixtures

SOURCE = b"# Republic\n\nThe Republic was founded in 509 BCE.\n"


def ingested(client, db, store, corpus_id, content=SOURCE, name="timeline.md"):
    """Upload and then run the real worker over it, as the API's caller would."""
    body = upload(client, corpus_id, content, name).json()
    run_once(db, store, STAGES)
    return body


def test_status_reports_the_contract_fields(client, db, store, corpus_id):
    body = ingested(client, db, store, corpus_id)

    status = client.get(f"/documents/{body['document_id']}").json()

    assert status["document_version_id"] == body["document_version_id"]
    assert status["active_version_id"] == body["document_version_id"]
    assert status["status"] == VersionStatus.READY
    assert status["current_stage"] == "publish"
    assert status["degraded_capabilities"] == {}
    assert status["error_summary"] is None
    assert status["ingestion_run_id"] is not None


def test_status_reports_a_failure_with_its_summary(client, db, store, corpus_id):
    body = ingested(client, db, store, corpus_id, content=b"tiny", name="x.txt")

    status = client.get(f"/documents/{body['document_id']}").json()

    assert status["status"] == VersionStatus.FAILED
    assert "empty_extraction" in status["error_summary"]
    assert status["active_version_id"] is None


def test_status_distinguishes_the_processing_version_from_the_active_one(
    client, db, store, corpus_id
):
    """§4: the published version stays searchable while its replacement runs."""
    body = ingested(client, db, store, corpus_id)
    replacement = replace(client, body["document_id"], b"# Empire\n\nAugustus, 27 BCE.\n", "t.md").json()

    status = client.get(f"/documents/{body['document_id']}").json()

    assert status["document_version_id"] == replacement["document_version_id"]
    assert status["active_version_id"] == body["document_version_id"]
    assert status["status"] == VersionStatus.PENDING


def test_status_for_an_unknown_document_is_404(client):
    assert client.get(f"/documents/{uuid.uuid4()}").status_code == 404


def test_delete_removes_the_document_and_everything_derived(client, db, store, corpus_id):
    body = ingested(client, db, store, corpus_id)
    version_id = uuid.UUID(body["document_version_id"])

    assert client.delete(f"/documents/{body['document_id']}").status_code == 204

    assert db.get(Document, uuid.UUID(body["document_id"])) is None
    assert db.scalars(
        select(DocumentVersion).where(DocumentVersion.id == version_id)
    ).all() == []
    assert db.scalars(
        select(Chunk).where(Chunk.document_version_id == version_id)
    ).all() == []


def test_delete_sweeps_the_artifacts_it_alone_referenced(client, db, store, corpus_id):
    body = ingested(client, db, store, corpus_id)
    key = db.get(DocumentVersion, uuid.UUID(body["document_version_id"])).source_artifact_key

    client.delete(f"/documents/{body['document_id']}")

    with pytest.raises(KeyError):
        store.get(key)


def test_delete_keeps_an_artifact_another_document_still_points_at(
    client, db, store, corpus_id
):
    """Artifacts are content-addressed: the same bytes in two corpora share one
    blob, and deleting one document must not blind the other."""
    first = ingested(client, db, store, corpus_id)
    other_corpus = client.post("/corpora", json={"name": f"c-{uuid.uuid4()}"}).json()["id"]
    second = ingested(client, db, store, other_corpus)
    key = db.get(DocumentVersion, uuid.UUID(second["document_version_id"])).source_artifact_key

    client.delete(f"/documents/{first['document_id']}")

    assert store.get(key) == SOURCE


def test_delete_for_an_unknown_document_is_404(client):
    assert client.delete(f"/documents/{uuid.uuid4()}").status_code == 404
