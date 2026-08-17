"""The parse stage inside the real executor: artifact written, failures
classified, and reparsing skipped when an earlier attempt already did it.
"""

import hashlib

import pytest
from sqlalchemy import select

from astrag.ingest.executor import run_once
from astrag.ingest.normalized import NormalizedDocument
from astrag.ingest.pipeline import STAGES
from astrag.models import (
    Document,
    DocumentVersion,
    IngestionJob,
    IngestionRun,
    JobState,
    VersionStatus,
)
from test_lifecycle_schema import make_corpus, make_document

SOURCE = b"# Republic\n\nThe Republic was founded in 509 BCE.\n"


@pytest.fixture
def enqueued(db, store):
    """A version whose source bytes are really in the store, like an upload."""

    def enqueue(data=SOURCE, media_type="text/markdown", filename="timeline.md"):
        document: Document = make_document(db, make_corpus(db))
        version = DocumentVersion(
            document_id=document.id,
            corpus_id=document.corpus_id,
            source_hash=hashlib.sha256(data).hexdigest(),
            source_artifact_key=store.put(data),
            filename=filename,
            media_type=media_type,
            byte_size=len(data),
        )
        db.add(version)
        db.flush()
        db.add(IngestionJob(document_version_id=version.id))
        db.commit()
        return version

    return enqueue


def latest_run(db, version) -> IngestionRun:
    return db.scalars(
        select(IngestionRun)
        .where(IngestionRun.document_version_id == version.id)
        .order_by(IngestionRun.attempt.desc())
    ).first()


def test_the_parse_stage_stores_a_normalized_document(db, store, enqueued):
    version = enqueued()

    run_once(db, store, STAGES)

    run = latest_run(db, version)
    document = NormalizedDocument.model_validate_json(
        store.get(run.normalized_artifact_key)
    )
    assert document.title == "timeline.md"
    assert [b.text for b in document.blocks] == [
        "Republic",
        "The Republic was founded in 509 BCE.",
    ]
    assert version.status == VersionStatus.READY


def test_unusable_input_fails_the_version_non_retryably(db, store, enqueued):
    version = enqueued(data=b"tiny", media_type="text/plain", filename="short.txt")

    run_once(db, store, STAGES)

    run = latest_run(db, version)
    assert (run.error_stage, run.error_code, run.error_retryable) == (
        "parse",
        "empty_extraction",
        False,
    )
    assert version.status == VersionStatus.FAILED


def test_a_media_type_without_a_parser_fails_the_version(db, store, enqueued):
    version = enqueued(media_type="application/zip", filename="archive.zip")

    run_once(db, store, STAGES)

    assert latest_run(db, version).error_code == "unsupported_media_type"
    assert version.status == VersionStatus.FAILED


def test_a_later_attempt_reuses_the_normalized_document(db, store, enqueued, monkeypatch):
    """Source bytes are immutable, so reparsing under the same generation could
    only produce the same artifact."""
    version = enqueued()
    run_once(db, store, STAGES)
    first = latest_run(db, version).normalized_artifact_key

    # A fresh attempt on the same version, with parsing made to fail loudly if
    # it is attempted at all.
    monkeypatch.setattr(
        "astrag.ingest.pipeline.parse",
        lambda *_: pytest.fail("reparsed a version that was already normalized"),
    )
    version.status = VersionStatus.PENDING
    job = db.scalars(
        select(IngestionJob).where(IngestionJob.document_version_id == version.id)
    ).one()
    job.state, job.attempts = JobState.PENDING, 1
    db.commit()

    run_once(db, store, STAGES)

    assert latest_run(db, version).normalized_artifact_key == first
    assert version.status == VersionStatus.READY
