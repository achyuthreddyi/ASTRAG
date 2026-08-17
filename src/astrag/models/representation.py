"""Search representations (§14, §16).

Derived, rebuildable projections of canonical chunks, scoped by the
SearchRepresentationGeneration that produced them — so re-embedding under a new
generation never overwrites the vectors the published one is still serving.

The lexical half is not here: it is a generated tsvector column on `chunks`
itself. A generated column cannot drift from the text it derives from, and
Postgres only lets it read its own row — which is where `contextualized_text`
lives. The cost is that a different text-search configuration needs a migration
rather than a new SRG; the benefit is that publication never has to verify by
hand that the lexical projection still matches its source text.
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from astrag.models.base import Base
from astrag.models.lifecycle import _timestamp

# Fixed-width by construction: pgvector columns declare their dimension, so an
# SRG on a differently sized model needs a migration adding a column. That is
# the plan's accepted constraint, not an oversight.
# It is DDL, so it is a constant here and settings.embedding_dimensions is
# checked against it rather than the other way round.
DIMENSIONS = 1536


class ChunkRepresentation(Base):
    __tablename__ = "chunk_representations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False
    )
    search_representation_generation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("search_representation_generations.id"),
        nullable=False,
    )
    embedding: Mapped[list[float]] = mapped_column(Vector(DIMENSIONS), nullable=False)
    # What produced this vector, denormalized from the generation config so a
    # mismatched provider is visible without joining and parsing JSONB.
    model: Mapped[str] = mapped_column(Text, nullable=False)
    # Input token count, for cost accounting and for spotting a chunk whose
    # contextualized text outgrew the model's window.
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = _timestamp()

    __table_args__ = (
        # One vector per chunk per generation: retrying an embedding batch
        # updates the row rather than growing a second candidate.
        UniqueConstraint(
            "chunk_id",
            "search_representation_generation_id",
            name="uq_chunk_representations_chunk_generation",
        ),
        Index(
            "ix_chunk_representations_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
