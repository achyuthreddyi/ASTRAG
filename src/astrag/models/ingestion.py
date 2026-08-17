"""Durable ingestion execution state.

Two tables with distinct jobs. `ingestion_jobs` is the work queue the worker
claims from — one row per version, mutated in place. `ingestion_runs` is attempt
history — one row per attempt, never rewritten, carrying the checkpoint, the
heartbeat that makes a dead worker detectable, and the structured failure (§21).

Correctness does not depend on worker memory: every stage boundary is a row
update, so a restarted worker resumes from the checkpoint (§22).
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from astrag.models.base import Base
from astrag.models.lifecycle import _timestamp


class JobState(StrEnum):
    PENDING = "PENDING"
    CLAIMED = "CLAIMED"
    DONE = "DONE"
    FAILED = "FAILED"


class IngestionJob(Base):
    """The queue. One row per document version, claimed with SKIP LOCKED."""

    __tablename__ = "ingestion_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    state: Mapped[JobState] = mapped_column(
        Enum(JobState, name="ingestion_job_state"),
        nullable=False,
        server_default=JobState.PENDING,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    # Bounded backoff for retryable failures. Due immediately on first enqueue.
    retry_after: Mapped[datetime] = _timestamp()
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _timestamp()
    updated_at: Mapped[datetime] = _timestamp(onupdate=func.now())

    __table_args__ = (
        # The claim query's only access path: due pending work, oldest first.
        Index(
            "ix_ingestion_jobs_claimable",
            "retry_after",
            postgresql_where=text("state = 'PENDING'"),
        ),
    )


class IngestionRun(Base):
    """One processing attempt. Immutable history once finished."""

    __tablename__ = "ingestion_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Which generations this attempt is building under. Not the published ones:
    # document_versions records those only at cutover.
    processing_generation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("processing_generations.id"), nullable=False
    )
    search_representation_generation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("search_representation_generations.id"),
        nullable=False,
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    # The pipeline step in progress, as plain text: the fourteen conceptual
    # states in §19 are stages, not an enum. A retry resumes from this stage.
    stage: Mapped[str] = mapped_column(Text, nullable=False)
    # The normalized document this attempt produced. Recorded on the run rather
    # than the version because it belongs to a (version, processing generation)
    # pair: a later attempt under the same generation reuses it instead of
    # reparsing, and one under a new generation must not.
    normalized_artifact_key: Mapped[str | None] = mapped_column(Text)
    heartbeat_at: Mapped[datetime] = _timestamp()
    started_at: Mapped[datetime] = _timestamp()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Structured failure (§21): stage, code, message, retryable. The timestamp is
    # finished_at and the generation identity is on this row already.
    error_stage: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    error_retryable: Mapped[bool | None] = mapped_column(Boolean)

    __table_args__ = (
        UniqueConstraint(
            "document_version_id", "attempt", name="uq_ingestion_runs_version_attempt"
        ),
        # §22: only one active attempt per version/generation may execute at once.
        Index(
            "uq_ingestion_runs_one_active",
            "document_version_id",
            "processing_generation_id",
            unique=True,
            postgresql_where=text("finished_at IS NULL"),
        ),
    )
