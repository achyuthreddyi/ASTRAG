"""Lifecycle identities from ADR-002.

Corpus → LogicalDocument → DocumentVersion (immutable source bytes), plus the
two immutable generation identities that processed and represented artifacts
reference. Three architecture rules are enforced here in DDL rather than in
application code: exact-byte idempotency, one replacement processing at a time,
and generation validity.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from astrag.models.base import Base

class VersionStatus(StrEnum):
    """Externally visible searchability state of a source version.

    The fourteen conceptual states in 02-ingestion.md §19 are pipeline stages,
    not a demand for fourteen enum values; the current step lives in
    ingestion_runs.stage as plain text (rung 5).
    """

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    READY = "READY"
    READY_DEGRADED = "READY_DEGRADED"
    FAILED = "FAILED"

_UUID_PK = {"primary_key": True, "default": uuid.uuid4}


def _timestamp(**kwargs) -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), **kwargs
    )


class Corpus(Base):
    __tablename__ = "corpora"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **_UUID_PK)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _timestamp()


class Document(Base):
    """Stable logical source identity. One corpus owns it (§ Corpus ownership)."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **_UUID_PK)
    corpus_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("corpora.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _timestamp()
    updated_at: Mapped[datetime] = _timestamp(onupdate=func.now())

    __table_args__ = (
        # Redundant as a key, but it is what lets document_versions reference the
        # (document, corpus) pair as a unit; see the composite FK there.
        UniqueConstraint("id", "corpus_id", name="uq_documents_id_corpus_id"),
    )


class DocumentVersion(Base):
    """Immutable source-content version. Never created by a processing change."""

    __tablename__ = "document_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **_UUID_PK)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    # Denormalized from documents so the idempotency unique constraint below can
    # exist at all, and so Stage 3 filters the corpus boundary without a join.
    # The composite FK is what makes the copy trustworthy: a version cannot claim
    # a corpus its own document does not belong to.
    corpus_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_artifact_key: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    media_type: Mapped[str] = mapped_column(Text, nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[VersionStatus] = mapped_column(
        Enum(VersionStatus, name="document_version_status"),
        nullable=False,
        server_default=VersionStatus.PENDING,
    )
    # Only the degraded capabilities: {} means fully ready (§20). SEMANTIC and
    # LEXICAL can never be degraded, so they never appear here.
    degraded_capabilities: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    # The *published* chunk set's generation — the third component of ADR-002's
    # published searchable identity. NULL until publication; written only at
    # cutover (rung 10), never when processing starts, or an unvalidated private
    # build would become the selector. In-progress runs carry their own
    # generation on the run and the chunks.
    published_processing_generation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("processing_generations.id")
    )
    error_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _timestamp()
    updated_at: Mapped[datetime] = _timestamp(onupdate=func.now())

    __table_args__ = (
        # A version belongs to its document *and* that document's corpus, as one
        # fact. Deleting either cascades: corpus → documents → versions.
        ForeignKeyConstraint(
            ["document_id", "corpus_id"],
            ["documents.id", "documents.corpus_id"],
            ondelete="CASCADE",
            name="fk_document_versions_document_corpus",
        ),
        # Invariant 1: exact-byte idempotency within a corpus. The same bytes in
        # a different corpus are a distinct logical document by design.
        UniqueConstraint(
            "corpus_id", "source_hash", name="uq_document_versions_corpus_source_hash"
        ),
        # Invariant 2: only one replacement version may process at a time for a
        # logical document (§4).
        Index(
            "uq_document_versions_one_in_flight",
            "document_id",
            unique=True,
            postgresql_where=text("status IN ('PENDING', 'RUNNING')"),
        ),
    )


class ProcessingGeneration(Base):
    """Immutable parser/normalizer/chunker configuration identity."""

    __tablename__ = "processing_generations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **_UUID_PK)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = _timestamp()


class SearchRepresentationGeneration(Base):
    """Immutable dense/lexical search-representation configuration identity."""

    __tablename__ = "search_representation_generations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **_UUID_PK)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = _timestamp()


class ActiveGenerationPointer(Base):
    """Exactly one row: the global generation pointers.

    `search_representation_generation_id` is the globally active SRG that Stage 3
    eligibility requires. `processing_generation_id` is the preferred generation
    for *new* processing (§3) — changing it does not reprocess anything.
    """

    __tablename__ = "active_generation_pointer"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False, default=1)
    processing_generation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("processing_generations.id"), nullable=False
    )
    search_representation_generation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("search_representation_generations.id"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = _timestamp(onupdate=func.now())

    __table_args__ = (
        CheckConstraint("id = 1", name="ck_active_generation_pointer_single_row"),
    )
