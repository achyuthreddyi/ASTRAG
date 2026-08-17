"""Temporal mentions (§12).

Extracted against normalized source structure, then associated with the chunk
whose source span contains them — so a mention is always evidence with a
location, never a floating date.

Normalized values are stored as year/month/day components with a signed year
rather than a timestamp: `datetime` cannot represent BCE at all, and the
architecture asks only for machine-comparable ordering, not calendar arithmetic.
Unresolved expressions keep their wording with every component NULL; §12 is
explicit that they stay evidence rather than being discarded or invented.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Enum, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from astrag.models.base import Base
from astrag.models.lifecycle import _timestamp


class TemporalOrigin(StrEnum):
    """Where the date came from. Kept explicit so a file's own metadata date can
    never be mistaken for a date the document talks about."""

    SOURCE_METADATA = "SOURCE_METADATA"
    CONTENT_MENTION = "CONTENT_MENTION"


class TemporalPrecision(StrEnum):
    DAY = "DAY"
    MONTH = "MONTH"
    YEAR = "YEAR"
    SEASON = "SEASON"
    DECADE = "DECADE"
    CENTURY = "CENTURY"
    RANGE = "RANGE"
    UNKNOWN = "UNKNOWN"


class TemporalCertainty(StrEnum):
    EXACT = "EXACT"
    APPROXIMATE = "APPROXIMATE"
    UNCERTAIN = "UNCERTAIN"


class TemporalMention(Base):
    __tablename__ = "temporal_mentions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    # The block the wording sits in, with its offsets inside that block, so the
    # mention survives a re-chunk that moves it into a different chunk.
    block_id: Mapped[str] = mapped_column(Text, nullable=False)
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    # Original wording, always: normalized values are stored only where safe.
    text: Mapped[str] = mapped_column(Text, nullable=False)
    origin: Mapped[TemporalOrigin] = mapped_column(
        Enum(TemporalOrigin, name="temporal_origin"), nullable=False
    )
    precision: Mapped[TemporalPrecision] = mapped_column(
        Enum(TemporalPrecision, name="temporal_precision"), nullable=False
    )
    certainty: Mapped[TemporalCertainty] = mapped_column(
        Enum(TemporalCertainty, name="temporal_certainty"), nullable=False
    )
    # Signed year: negative is BCE, and there is no year zero in the source era
    # convention, so -44 is 44 BCE. A range fills both bounds; a single date
    # fills only the start.
    start_year: Mapped[int | None] = mapped_column(Integer)
    start_month: Mapped[int | None] = mapped_column(Integer)
    start_day: Mapped[int | None] = mapped_column(Integer)
    end_year: Mapped[int | None] = mapped_column(Integer)
    end_month: Mapped[int | None] = mapped_column(Integer)
    end_day: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = _timestamp()

    __table_args__ = (
        # Extraction is deterministic, so a re-run producing a second row for
        # the same wording in the same place is a bug, not a variant reading.
        UniqueConstraint(
            "chunk_id",
            "block_id",
            "start_offset",
            "end_offset",
            name="uq_temporal_mentions_chunk_span",
        ),
    )
