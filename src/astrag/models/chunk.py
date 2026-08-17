"""Canonical chunks (§10, §11).

The authoritative evidence unit. Every lineage identifier Stage 3's searchable
contract needs lives on the row itself — corpus, document, version, processing
generation — so the corpus boundary is a column filter and never a join.

Identity is (document_version_id, processing_generation_id, ordinal): the
architecture's conceptual key, made a real unique constraint so a re-run that
rebuilds a chunk set cannot leave two of them behind.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from astrag.models.base import Base
from astrag.models.lifecycle import _timestamp


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Denormalized lineage. corpus_id is bound to the version's own corpus by the
    # composite FK below, so the Stage 3 boundary filter cannot read a stale copy.
    corpus_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    processing_generation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("processing_generations.id"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    # Authoritative source prose, kept apart from the retrieval text so citation
    # never quotes a heading the chunker prepended (§9).
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    contextualized_text: Mapped[str] = mapped_column(Text, nullable=False)
    section_path: Mapped[list] = mapped_column(JSONB, nullable=False)
    # [{"block_id": "b0007", "start": 0, "end": 412}] — block ids plus per-block
    # normalized offsets, which is all V1 lineage requires (§11).
    source_spans: Mapped[list] = mapped_column(JSONB, nullable=False)
    # Nullable: only paginated formats have meaningful pages, and a chunk may
    # span two of them.
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    # Separate from identity on purpose: identical text in two places stays two
    # distinct chunk occurrences (§10).
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = _timestamp()

    __table_args__ = (
        # A chunk belongs to its version *and* that version's document and corpus
        # as one fact. Cascade: corpus → documents → versions → chunks.
        ForeignKeyConstraint(
            ["document_version_id", "document_id", "corpus_id"],
            [
                "document_versions.id",
                "document_versions.document_id",
                "document_versions.corpus_id",
            ],
            ondelete="CASCADE",
            name="fk_chunks_version_document_corpus",
        ),
        UniqueConstraint(
            "document_version_id",
            "processing_generation_id",
            "ordinal",
            name="uq_chunks_version_generation_ordinal",
        ),
    )
