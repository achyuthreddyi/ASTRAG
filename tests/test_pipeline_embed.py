"""The embed stage inside the real executor: one vector per chunk, already-paid
work never re-bought, and a provider outage retried rather than failed."""

import pytest
from sqlalchemy import select

from astrag.ingest.embedding import EmbeddingError
from astrag.ingest.executor import run_once
from astrag.ingest.pipeline import STAGES
from astrag.models import Chunk, ChunkRepresentation, JobState, VersionStatus
from astrag.models.representation import DIMENSIONS
from test_pipeline_chunk import chunks_of
from test_pipeline_parse import enqueued, latest_run  # noqa: F401 — fixtures


def representations_of(db, version) -> list[ChunkRepresentation]:
    return list(
        db.scalars(
            select(ChunkRepresentation)
            .join(Chunk, Chunk.id == ChunkRepresentation.chunk_id)
            .where(Chunk.document_version_id == version.id)
        )
    )


def test_every_chunk_gets_a_vector_under_the_run_generation(db, store, enqueued):
    version = enqueued()

    run_once(db, store, STAGES)

    representations = representations_of(db, version)
    run = latest_run(db, version)
    assert len(representations) == len(chunks_of(db, version))
    assert {len(r.embedding) for r in representations} == {DIMENSIONS}
    assert {r.search_representation_generation_id for r in representations} == {
        run.search_representation_generation_id
    }
    assert all(r.input_tokens > 0 for r in representations)
    assert version.status == VersionStatus.READY


def test_a_retry_does_not_re_embed_what_is_already_stored(db, store, enqueued, monkeypatch):
    """Provider calls cost money; durable vectors are not bought twice."""
    version = enqueued()
    run_once(db, store, STAGES)
    before = {r.chunk_id: r.id for r in representations_of(db, version)}

    monkeypatch.setattr(
        "astrag.ingest.pipeline.get_embedder",
        lambda: pytest.fail("re-embedded chunks that already had vectors"),
    )
    requeue(db, version)
    run_once(db, store, STAGES)

    assert {r.chunk_id: r.id for r in representations_of(db, version)} == before


def test_a_provider_failure_is_retryable(db, store, enqueued, monkeypatch):
    """§14 makes the dense vector mandatory, but a down provider is transient."""
    version = enqueued()

    class Down:
        model = "down"

        def embed(self, texts):
            raise EmbeddingError("provider is down")

    monkeypatch.setattr("astrag.ingest.pipeline.get_embedder", Down)

    run_once(db, store, STAGES)

    run = latest_run(db, version)
    assert (run.error_stage, run.error_code, run.error_retryable) == (
        "embed",
        "embedding_failed",
        True,
    )
    assert version.status == VersionStatus.PENDING


def requeue(db, version):
    from astrag.models import IngestionJob

    version.status = VersionStatus.PENDING
    job = db.scalars(
        select(IngestionJob).where(IngestionJob.document_version_id == version.id)
    ).one()
    job.state, job.attempts = JobState.PENDING, 1
    db.commit()
