"""The chunk stage inside the real executor: rows written with full lineage,
and a re-run that rebuilds rather than duplicates.
"""

from sqlalchemy import select

from astrag.ingest.executor import run_once
from astrag.ingest.pipeline import STAGES
from astrag.models import Chunk, IngestionJob, JobState, VersionStatus
from test_pipeline_parse import enqueued, latest_run  # noqa: F401 — fixtures


def chunks_of(db, version) -> list[Chunk]:
    return list(
        db.scalars(
            select(Chunk)
            .where(Chunk.document_version_id == version.id)
            .order_by(Chunk.ordinal)
        )
    )


def test_the_chunk_stage_writes_chunks_with_full_lineage(db, store, enqueued):
    version = enqueued()

    run_once(db, store, STAGES)

    chunks = chunks_of(db, version)
    run = latest_run(db, version)
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))
    assert chunks[0].source_text.startswith("Republic")
    assert chunks[0].section_path == ["Republic"]
    assert chunks[0].source_spans[0]["block_id"] == "b0000"
    assert {c.corpus_id for c in chunks} == {version.corpus_id}
    assert {c.processing_generation_id for c in chunks} == {run.processing_generation_id}
    assert version.status == VersionStatus.READY


def test_a_re_run_rebuilds_the_chunk_set_instead_of_duplicating_it(db, store, enqueued):
    """Stage granularity is the whole stage, so it must be idempotent (§22).

    Identity is reconciled by ordinal, not recreated: the rows keep their ids so
    the representations hanging off them survive the retry.
    """
    version = enqueued()
    run_once(db, store, STAGES)
    identities = [c.id for c in chunks_of(db, version)]
    first = [c.content_hash for c in chunks_of(db, version)]

    version.status = VersionStatus.PENDING
    job = db.scalars(
        select(IngestionJob).where(IngestionJob.document_version_id == version.id)
    ).one()
    job.state, job.attempts = JobState.PENDING, 1
    db.commit()
    run_once(db, store, STAGES)

    assert [c.content_hash for c in chunks_of(db, version)] == first
    assert [c.id for c in chunks_of(db, version)] == identities
