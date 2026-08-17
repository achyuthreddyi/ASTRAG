"""What the temporal_mentions table guarantees: mentions live with their chunk,
unresolved wording is still storable, and one span is one mention.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from astrag.models import (
    TemporalCertainty,
    TemporalMention,
    TemporalOrigin,
    TemporalPrecision,
)
from test_chunk_schema import make_chunk
from test_lifecycle_schema import make_corpus, make_document, make_version


def make_mention(db, chunk, **kwargs):
    mention = TemporalMention(
        chunk_id=chunk.id,
        block_id="b0001",
        start_offset=kwargs.pop("start_offset", 24),
        end_offset=kwargs.pop("end_offset", 31),
        text=kwargs.pop("text", "509 BCE"),
        origin=TemporalOrigin.CONTENT_MENTION,
        precision=kwargs.pop("precision", TemporalPrecision.YEAR),
        certainty=kwargs.pop("certainty", TemporalCertainty.EXACT),
        start_year=kwargs.pop("start_year", -509),
        **kwargs,
    )
    db.add(mention)
    db.flush()
    return mention


@pytest.fixture
def chunk(db):
    return make_chunk(db, make_version(db, make_document(db, make_corpus(db))))


def test_a_bce_year_is_stored_as_a_signed_year(db, chunk):
    """BCE stays machine-comparable without a timestamp type that cannot hold it."""
    mention = make_mention(db, chunk)

    assert (mention.start_year, mention.start_month) == (-509, None)
    assert mention.text == "509 BCE"


def test_an_unresolved_expression_is_kept_as_evidence(db, chunk):
    """§12: never discarded, never given an invented date."""
    mention = make_mention(
        db,
        chunk,
        text="two years later",
        precision=TemporalPrecision.UNKNOWN,
        certainty=TemporalCertainty.UNCERTAIN,
        start_year=None,
    )

    assert mention.start_year is None


def test_one_chunk_holds_many_mentions(db, chunk):
    make_mention(db, chunk, start_offset=0, end_offset=7)
    make_mention(db, chunk, start_offset=24, end_offset=31)

    # Scoped to this chunk: a global count would also see whatever the developer
    # left in their database.
    assert len(
        db.scalars(
            select(TemporalMention).where(TemporalMention.chunk_id == chunk.id)
        ).all()
    ) == 2


def test_the_same_span_twice_in_one_chunk_is_rejected(db, chunk):
    """Extraction is deterministic: a duplicate row is a bug, not a reading."""
    make_mention(db, chunk)

    with pytest.raises(IntegrityError, match="uq_temporal_mentions_chunk_span"):
        make_mention(db, chunk)


def test_dropping_the_chunk_drops_its_mentions(db, chunk):
    mention = make_mention(db, chunk)

    db.delete(chunk)
    db.flush()

    assert db.scalars(
        select(TemporalMention).where(TemporalMention.id == mention.id)
    ).all() == []
