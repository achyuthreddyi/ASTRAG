"""Golden-file tests for the temporal extractor, plus the rules behind them.

The goldens pin what is recognized and how it is normalized, because a silent
change there changes what evidence a temporal query can find. Regenerate with
UPDATE_GOLDEN=1.
"""

import json
import os
from dataclasses import asdict
from pathlib import Path

import pytest

from astrag.ingest.parsers import parse
from astrag.ingest.temporal import extract, extract_from
from astrag.models import TemporalCertainty, TemporalOrigin, TemporalPrecision

GOLDEN = Path(__file__).parent / "golden"
MEDIA_TYPES = {".txt": "text/plain", ".md": "text/markdown"}


def only(text: str):
    mentions = extract_from("b0000", text)
    assert len(mentions) == 1, [m.text for m in mentions]
    return mentions[0]


@pytest.mark.parametrize(
    "source",
    sorted(p for p in GOLDEN.iterdir() if p.suffix in MEDIA_TYPES),
    ids=lambda p: p.name,
)
def test_extraction_matches_the_golden_mentions(source: Path):
    parsed = parse(source.read_bytes(), MEDIA_TYPES[source.suffix], source.name)

    mentions = extract(parsed)

    expected = GOLDEN / f"{source.name}.temporal.json"
    actual = json.dumps([asdict(m) for m in mentions], indent=2, default=str) + "\n"
    if os.environ.get("UPDATE_GOLDEN"):
        expected.write_text(actual)
    assert json.loads(actual) == json.loads(expected.read_text())


def test_bce_is_a_negative_year():
    mention = only("The Republic was founded in 509 BCE.")

    assert (mention.precision, mention.start_year) == (TemporalPrecision.YEAR, -509)
    assert mention.text == "509 BCE"


def test_a_full_date_keeps_day_month_and_era():
    mention = only("On 15 March 44 BCE, Caesar was killed.")

    assert mention.precision == TemporalPrecision.DAY
    assert (mention.start_year, mention.start_month, mention.start_day) == (-44, 3, 15)


def test_a_range_is_one_mention_with_both_bounds():
    """§12: ranges are one mention, not two dates that a reader must pair up."""
    mention = only("Augustus held power from 27 BCE until 14 CE.")

    assert mention.precision == TemporalPrecision.RANGE
    assert (mention.start_year, mention.end_year) == (-27, 14)


@pytest.mark.parametrize(
    ("text", "precision", "bounds"),
    [
        ("the 1940s", TemporalPrecision.DECADE, (1940, 1949)),
        ("the 5th century BCE", TemporalPrecision.CENTURY, (-500, -401)),
        ("in summer 1944", TemporalPrecision.SEASON, (1944, None)),
        ("on 1944-06-06", TemporalPrecision.DAY, (1944, None)),
        ("in March 1944", TemporalPrecision.MONTH, (1944, None)),
    ],
)
def test_precision_categories_carry_their_own_bounds(text, precision, bounds):
    mention = only(text)

    assert mention.precision == precision
    assert (mention.start_year, mention.end_year) == bounds


@pytest.mark.parametrize(
    ("text", "certainty"),
    [
        ("in 121 CE", TemporalCertainty.EXACT),
        ("c. 121 CE", TemporalCertainty.APPROXIMATE),
        ("roughly 121 CE", TemporalCertainty.APPROXIMATE),
        ("possibly 121 CE", TemporalCertainty.UNCERTAIN),
    ],
)
def test_hedging_before_a_date_lowers_its_certainty(text, certainty):
    assert only(text).certainty == certainty


def test_an_unresolved_relative_expression_survives_without_values():
    """§12: never discarded, never assigned an invented date."""
    mention = only("Civil war followed within two years later.")

    assert mention.precision == TemporalPrecision.UNKNOWN
    assert mention.certainty == TemporalCertainty.UNCERTAIN
    assert mention.start_year is None
    assert mention.text == "two years later"


def test_a_bare_small_number_after_a_month_is_not_a_year():
    """Inventing 15 CE out of "March 15" would be worse than finding nothing."""
    assert extract_from("b0000", "March 15 was unseasonably warm.") == []


def test_content_dates_are_marked_as_content():
    """Origin keeps a document's own metadata date distinguishable from a date
    the document talks about (§12)."""
    assert only("in 121 CE").origin == TemporalOrigin.CONTENT_MENTION


def test_offsets_locate_the_wording_in_its_block():
    text = "The Republic was founded in 509 BCE."

    mention = only(text)

    assert text[mention.start_offset : mention.end_offset] == mention.text
