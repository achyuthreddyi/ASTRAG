"""The sequential checkpointed pipeline executor.

One unit of work: claim a due job, open an attempt, run the stages in order
committing after each, and settle the version. Nothing here holds state across
a crash — the claimed job and its run row are the whole recovery record (§22).

The stage list is passed in rather than imported: the executor knows how to run
and checkpoint stages, and `astrag.ingest.pipeline` decides what they are.
"""

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from astrag.models import (
    ActiveGenerationPointer,
    DocumentVersion,
    IngestionJob,
    IngestionRun,
    JobState,
    VersionStatus,
)
from astrag.settings import get_settings
from astrag.storage.artifacts import ArtifactStore

log = logging.getLogger(__name__)


class StageError(Exception):
    """A failure a stage understands well enough to classify (§21)."""

    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass
class StageContext:
    db: Session
    store: ArtifactStore
    version: DocumentVersion
    run: IngestionRun


Stage = tuple[str, Callable[[StageContext], None]]


def run_once(
    db: Session, store: ArtifactStore, stages: Sequence[Stage]
) -> IngestionJob | None:
    """Process one job. Returns None when the queue has nothing due."""
    job = _claim(db)
    if job is None:
        return None

    version = db.get(DocumentVersion, job.document_version_id)
    run = _open_run(db, job, version, stages)
    resume_from = _resume_index(run, stages)
    if resume_from:
        log.info("resuming version %s from stage %s", version.id, run.stage)

    for name, stage in list(stages)[resume_from:]:
        run.stage = name
        _beat(db, job, run)
        try:
            stage(StageContext(db=db, store=store, version=version, run=run))
        except Exception as error:  # noqa: BLE001 — classified below, never swallowed
            _fail(db, job, run, version, name, error)
            return job
        # One row update per completed stage: the checkpoint granularity is a
        # whole stage, and every stage is idempotent under stable identities.
        _beat(db, job, run)

    _settle(db, job, run, version)
    return job


def _claim(db: Session) -> IngestionJob | None:
    """Take the oldest due job, or reclaim one whose worker stopped beating."""
    stale_before = _now(db) - timedelta(seconds=get_settings().stale_job_seconds)
    claimable = (
        select(IngestionJob.id)
        .where(
            (
                (IngestionJob.state == JobState.PENDING)
                & (IngestionJob.retry_after <= func.now())
            )
            | (
                (IngestionJob.state == JobState.CLAIMED)
                & (IngestionJob.heartbeat_at < stale_before)
            )
        )
        .order_by(IngestionJob.retry_after)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    # SKIP LOCKED is what makes two workers safe without a lock table.
    claimed = db.execute(
        update(IngestionJob)
        .where(IngestionJob.id == claimable.scalar_subquery())
        .values(state=JobState.CLAIMED, claimed_at=func.now(), heartbeat_at=func.now())
        .returning(IngestionJob.id)
    ).scalar_one_or_none()
    db.commit()
    if claimed is None:
        return None
    return db.get(IngestionJob, claimed)


def _open_run(
    db: Session, job: IngestionJob, version: DocumentVersion, stages: Sequence[Stage]
) -> IngestionRun:
    """Reuse the unfinished attempt of a crashed worker; otherwise start one."""
    generations = db.scalars(select(ActiveGenerationPointer)).one()
    previous = db.scalars(
        select(IngestionRun)
        .where(IngestionRun.document_version_id == version.id)
        .order_by(IngestionRun.attempt.desc())
    ).first()
    # An unfinished attempt belongs to a worker that died: continue it rather
    # than burning an attempt number.
    existing = previous if previous is not None and previous.finished_at is None else None
    if existing is None:
        job.attempts += 1
        existing = IngestionRun(
            document_version_id=version.id,
            processing_generation_id=generations.processing_generation_id,
            search_representation_generation_id=(
                generations.search_representation_generation_id
            ),
            attempt=job.attempts,
            # A retry re-runs the stage that failed, not the ones that already
            # succeeded: their artifacts are reusable under stable identities.
            stage=(previous.error_stage if previous else None)
            or (stages[0][0] if stages else ""),
        )
        db.add(existing)
    version.status = VersionStatus.RUNNING
    db.commit()
    return existing


def _resume_index(run: IngestionRun, stages: Sequence[Stage]) -> int:
    """Resume at the checkpointed stage, never inside it."""
    names = [name for name, _ in stages]
    return names.index(run.stage) if run.stage in names else 0


def _beat(db: Session, job: IngestionJob, run: IngestionRun) -> None:
    job.heartbeat_at = func.now()
    run.heartbeat_at = func.now()
    db.commit()


def _fail(
    db: Session,
    job: IngestionJob,
    run: IngestionRun,
    version: DocumentVersion,
    stage: str,
    error: Exception,
) -> None:
    db.rollback()
    # An unclassified exception is not assumed transient: retrying an unknown
    # failure forever is worse than surfacing it once.
    code = error.code if isinstance(error, StageError) else "unexpected"
    retryable = error.retryable if isinstance(error, StageError) else False
    settings = get_settings()

    run.error_stage, run.error_code = stage, code
    run.error_message, run.error_retryable = str(error), retryable
    run.finished_at = func.now()

    if retryable and job.attempts < settings.max_attempts:
        job.state = JobState.PENDING
        job.retry_after = _now(db) + timedelta(
            seconds=settings.retry_backoff_seconds * job.attempts
        )
        version.status = VersionStatus.PENDING
    else:
        job.state = JobState.FAILED
        version.status = VersionStatus.FAILED
        version.error_summary = f"{stage}: {code}: {error}"
    db.commit()
    log.warning("version %s failed in %s: %s: %s", version.id, stage, code, error)


def _settle(
    db: Session, job: IngestionJob, run: IngestionRun, version: DocumentVersion
) -> None:
    run.finished_at = func.now()
    job.state = JobState.DONE
    # ponytail: rung 10 replaces this with publication validation and atomic
    # activation. Until then a completed pipeline is taken at its word.
    version.status = (
        VersionStatus.READY_DEGRADED
        if version.degraded_capabilities
        else VersionStatus.READY
    )
    db.commit()


def _now(db: Session):
    """Database clock, so a skewed worker cannot mis-time backoff or staleness."""
    return db.scalar(select(func.now()))
