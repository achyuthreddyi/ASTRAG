"""Publication: what it refuses, and what activation actually changes (§23)."""

import pytest
from sqlalchemy import delete, select

from astrag.ingest.executor import run_once
from astrag.ingest.normalized import NormalizedDocument
from astrag.ingest.pipeline import STAGES
from astrag.ingest.publish import validate
from astrag.models import (
    ActiveGenerationPointer,
    ChunkRepresentation,
    Document,
    SearchRepresentationGeneration,
    VersionStatus,
)
from test_pipeline_chunk import chunks_of
from test_pipeline_parse import enqueued, latest_run  # noqa: F401 — fixtures


@pytest.fixture
def published(db, store, enqueued):
    """A version taken all the way through the real pipeline."""
    version = enqueued()
    run_once(db, store, STAGES)
    return version


def revalidate(db, store, version):
    run = latest_run(db, version)
    document = NormalizedDocument.model_validate_json(
        store.get(run.normalized_artifact_key)
    )
    return validate(db, version, run, document)


def test_publication_activates_the_version_and_its_generation(db, store, published):
    document = db.get(Document, published.document_id)
    run = latest_run(db, published)

    assert document.active_version_id == published.id
    assert published.published_processing_generation_id == run.processing_generation_id
    assert published.status == VersionStatus.READY


def test_a_healthy_build_has_nothing_to_report(db, store, published):
    assert revalidate(db, store, published) == []


def test_a_chunk_without_a_vector_is_refused(db, store, published):
    """§14: a chunk missing a required representation is not partially published."""
    orphan = chunks_of(db, published)[0]
    db.execute(
        delete(ChunkRepresentation).where(ChunkRepresentation.chunk_id == orphan.id)
    )

    assert revalidate(db, store, published) == [
        f"chunks [{orphan.ordinal}] have no dense representation"
    ]


def test_a_span_outside_the_normalized_source_is_refused(db, store, published):
    """A span nobody can resolve is a citation that cannot be checked."""
    chunk = chunks_of(db, published)[0]
    chunk.source_spans = [{"block_id": "b9999", "start": 0, "end": 5}]
    db.flush()

    assert revalidate(db, store, published) == [
        f"chunks [{chunk.ordinal}] have spans outside the normalized source"
    ]


def test_a_gap_in_the_ordinals_is_refused(db, store, published):
    """The count Stage 3 can see must equal the count that was built."""
    chunk = chunks_of(db, published)[0]
    chunk.ordinal = chunk.ordinal + 5
    db.flush()

    assert "chunk ordinals are not a complete sequence" in revalidate(db, store, published)


def test_a_superseded_search_generation_is_refused(db, store, published):
    """Publishing under an inactive SRG reads as a document that finds nothing."""
    successor = SearchRepresentationGeneration(config={"model": "next"})
    db.add(successor)
    db.flush()
    db.scalars(select(ActiveGenerationPointer)).one().search_representation_generation_id = successor.id

    assert revalidate(db, store, published) == [
        "this run's search representation generation is not the active one"
    ]


def test_a_failed_validation_fails_the_version_non_retryably(db, store, enqueued, monkeypatch):
    version = enqueued()
    monkeypatch.setattr(
        "astrag.ingest.pipeline.validate", lambda *_: ["chunks [3] have no dense representation"]
    )

    run_once(db, store, STAGES)

    run = latest_run(db, version)
    assert (run.error_stage, run.error_code, run.error_retryable) == (
        "publish",
        "publication_invalid",
        False,
    )
    assert version.status == VersionStatus.FAILED
    assert db.get(Document, version.document_id).active_version_id is None
