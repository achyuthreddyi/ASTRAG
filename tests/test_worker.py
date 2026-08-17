"""Worker behaviour that must survive a process dying at the worst moment:
checkpointed resume, bounded retry, and reclaiming a job whose worker stopped
beating. The stages are injected, so this tests the executor and not the
pipeline that rungs 6-10 fill in.
"""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from astrag.ingest.executor import StageContext, StageError, run_once
from astrag.models import (
    ActiveGenerationPointer,
    DocumentVersion,
    IngestionJob,
    IngestionRun,
    JobState,
    VersionStatus,
)
from test_lifecycle_schema import make_corpus, make_document, make_version


@pytest.fixture
def version(db):
    return make_version(db, make_document(db, make_corpus(db)))


@pytest.fixture
def job(db, version):
    job = IngestionJob(document_version_id=version.id)
    db.add(job)
    db.commit()
    return job


def recorder(calls):
    def stage(name):
        return (name, lambda ctx: calls.append(name))

    return [stage("parse"), stage("chunk"), stage("represent")]


def failing(code="boom", retryable=False):
    def raiser(ctx: StageContext) -> None:
        raise StageError(code, "stage exploded", retryable=retryable)

    return [("parse", lambda ctx: None), ("chunk", raiser)]


def latest_run(db, version) -> IngestionRun:
    return db.scalars(
        select(IngestionRun)
        .where(IngestionRun.document_version_id == version.id)
        .order_by(IngestionRun.attempt.desc())
    ).first()


def test_an_empty_queue_returns_nothing(db, store):
    assert run_once(db, store, stages=[]) is None


def test_stages_run_in_order_and_the_version_becomes_ready(db, store, version, job):
    calls = []

    assert run_once(db, store, stages=recorder(calls)) is not None

    assert calls == ["parse", "chunk", "represent"]
    assert job.state == JobState.DONE
    assert version.status == VersionStatus.READY
    assert latest_run(db, version).finished_at is not None


def test_a_degraded_capability_publishes_as_degraded(db, store, version, job):
    def degrade(ctx):
        ctx.version.degraded_capabilities = {"temporal": "degraded"}

    run_once(db, store, stages=[("enrich", degrade)])

    assert version.status == VersionStatus.READY_DEGRADED


def test_a_job_is_claimed_only_once(db, store, version, job):
    run_once(db, store, stages=recorder([]))

    assert run_once(db, store, stages=recorder([])) is None


def test_a_job_is_not_claimed_before_its_backoff_expires(db, store, version, job):
    job.retry_after = db.scalar(select(func.now())) + timedelta(minutes=5)
    db.commit()

    assert run_once(db, store, stages=recorder([])) is None


def test_a_non_retryable_failure_fails_the_version(db, store, version, job):
    run_once(db, store, stages=failing())

    assert job.state == JobState.FAILED
    assert version.status == VersionStatus.FAILED
    assert "boom" in version.error_summary

    run = latest_run(db, version)
    assert (run.error_stage, run.error_code, run.error_retryable) == ("chunk", "boom", False)
    assert run.finished_at is not None


def test_an_unclassified_exception_is_treated_as_non_retryable(db, store, version, job):
    def broken(ctx):
        raise ZeroDivisionError("not a StageError")

    run_once(db, store, stages=[("chunk", broken)])

    assert job.state == JobState.FAILED
    assert latest_run(db, version).error_code == "unexpected"


def test_a_retryable_failure_is_requeued_with_backoff(db, store, version, job):
    now = db.scalar(select(func.now()))

    run_once(db, store, stages=failing(retryable=True))

    assert job.state == JobState.PENDING
    assert job.attempts == 1
    assert job.retry_after > now
    assert version.status == VersionStatus.PENDING


def test_retries_are_bounded(db, store, version, job, monkeypatch):
    from astrag.settings import get_settings

    monkeypatch.setattr(get_settings(), "max_attempts", 2)

    for _ in range(2):
        job.retry_after = db.scalar(select(func.now()))
        db.commit()
        run_once(db, store, stages=failing(retryable=True))

    assert job.attempts == 2
    assert job.state == JobState.FAILED
    assert version.status == VersionStatus.FAILED


def test_a_retry_resumes_from_the_checkpointed_stage(db, store, version, job):
    calls = []
    run_once(db, store, stages=failing(retryable=True))
    job.retry_after = db.scalar(select(func.now()))
    db.commit()

    run_once(db, store, stages=recorder(calls))

    # The failed stage reruns from its start; the stage before it does not.
    assert calls == ["chunk", "represent"]


def test_a_stale_claim_is_reclaimed_and_resumed(db, store, version, job, generations):
    """The worker died mid-stage: job still CLAIMED, attempt still unfinished."""
    old = db.scalar(select(func.now())) - timedelta(hours=1)
    job.state, job.heartbeat_at, job.attempts = JobState.CLAIMED, old, 1
    db.add(
        IngestionRun(
            document_version_id=version.id,
            processing_generation_id=generations.processing_generation_id,
            search_representation_generation_id=(
                generations.search_representation_generation_id
            ),
            attempt=1,
            stage="chunk",
            heartbeat_at=old,
        )
    )
    db.commit()

    calls = []
    assert run_once(db, store, stages=recorder(calls)) is not None

    assert calls == ["chunk", "represent"]
    # The crashed attempt is continued, not restarted as a fresh attempt.
    assert job.attempts == 1
    assert db.scalars(
        select(func.count()).select_from(IngestionRun).where(
            IngestionRun.document_version_id == version.id
        )
    ).one() == 1
    assert version.status == VersionStatus.READY


def test_a_freshly_claimed_job_beats_before_stages_run(db, store, version, job):
    run_once(db, store, stages=recorder([]))

    assert job.claimed_at is not None
    assert job.heartbeat_at is not None


@pytest.fixture
def generations(db):
    return db.scalars(select(ActiveGenerationPointer)).one()


def test_a_deleted_version_takes_its_queue_row_with_it(db, store, version, job):
    version_id = version.id
    db.delete(version)
    db.commit()

    assert db.scalars(
        select(IngestionJob).where(IngestionJob.document_version_id == version_id)
    ).all() == []
    assert db.get(DocumentVersion, uuid.uuid4()) is None
