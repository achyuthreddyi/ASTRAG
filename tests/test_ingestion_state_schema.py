"""Execution-state invariants that must hold in DDL, not in worker code: one
queue row per version, one active attempt per version/generation, and no
attempt numbered twice.
"""

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from astrag.models import (
    ActiveGenerationPointer,
    IngestionJob,
    IngestionRun,
    JobState,
)
from test_lifecycle_schema import make_corpus, make_document, make_version


@pytest.fixture
def version(db):
    return make_version(db, make_document(db, make_corpus(db)))


@pytest.fixture
def generations(db):
    return db.scalars(select(ActiveGenerationPointer)).one()


def func_now(db):
    return db.scalar(select(func.now()))


def make_run(db, version, generations, attempt=1, **kwargs):
    run = IngestionRun(
        document_version_id=version.id,
        attempt=attempt,
        stage="parse",
        **{
            "processing_generation_id": generations.processing_generation_id,
            "search_representation_generation_id": (
                generations.search_representation_generation_id
            ),
            **kwargs,
        },
    )
    db.add(run)
    db.flush()
    return run


def test_a_version_is_enqueued_once(db, version):
    db.add(IngestionJob(document_version_id=version.id))
    db.flush()

    db.add(IngestionJob(document_version_id=version.id))
    with pytest.raises(IntegrityError):
        db.flush()


def test_a_new_job_is_pending_and_immediately_due(db, version):
    job = IngestionJob(document_version_id=version.id)
    db.add(job)
    db.flush()
    db.refresh(job)

    assert (job.state, job.attempts) == (JobState.PENDING, 0)
    assert job.retry_after is not None


def test_two_active_attempts_for_one_version_and_generation_are_rejected(
    db, version, generations
):
    """§22: only one attempt per version/generation may execute at once."""
    make_run(db, version, generations, attempt=1)

    with pytest.raises(IntegrityError, match="uq_ingestion_runs_one_active"):
        make_run(db, version, generations, attempt=2)


def test_a_new_attempt_may_start_once_the_previous_one_finished(
    db, version, generations
):
    make_run(db, version, generations, attempt=1, finished_at=func_now(db))
    second = make_run(db, version, generations, attempt=2)

    assert second.finished_at is None


def test_an_attempt_number_cannot_repeat(db, version, generations):
    """Attempt history is history: it never rewrites a numbered attempt."""
    make_run(db, version, generations, attempt=1, finished_at=func_now(db))

    with pytest.raises(IntegrityError, match="uq_ingestion_runs_version_attempt"):
        make_run(db, version, generations, attempt=1, finished_at=func_now(db))


def test_deleting_a_version_removes_its_queue_row_and_attempts(
    db, version, generations
):
    db.add(IngestionJob(document_version_id=version.id))
    run = make_run(db, version, generations)
    version_id = version.id

    db.delete(version)
    db.flush()

    assert db.scalars(
        select(IngestionRun).where(IngestionRun.id == run.id)
    ).all() == []
    assert db.scalars(
        select(IngestionJob).where(IngestionJob.document_version_id == version_id)
    ).all() == []


def test_a_run_cannot_reference_an_unknown_generation(db, version, generations):
    with pytest.raises(IntegrityError, match="processing_generation_id"):
        make_run(
            db,
            version,
            generations,
            processing_generation_id=uuid.uuid4(),
        )
