"""Deterministic temporal recognition (§12).

Regex recognition over normalized block text, producing mentions with explicit
precision, certainty, origin and — where safe — normalized values. Nothing here
guesses: an expression it cannot resolve keeps its wording and stores no values,
because §12 requires unresolved expressions to survive as evidence rather than
be discarded or given an invented date.

The controlled semantic-interpretation half of §12's hybrid architecture slots
in behind `extract` once there is a labelled set to score it against.

ponytail: no Julian/Gregorian conversion and no hemisphere-dependent season →
month mapping, both explicitly out of V1. Seasons store the year only.
"""

import re
from dataclasses import dataclass

from astrag.ingest.normalized import NormalizedDocument
from astrag.models.temporal import (
    TemporalCertainty,
    TemporalOrigin,
    TemporalPrecision,
)

MONTHS = {
    name: number
    for number, names in enumerate(
        [
            ("january", "jan"),
            ("february", "feb"),
            ("march", "mar"),
            ("april", "apr"),
            ("may",),
            ("june", "jun"),
            ("july", "jul"),
            ("august", "aug"),
            ("september", "sep", "sept"),
            ("october", "oct"),
            ("november", "nov"),
            ("december", "dec"),
        ],
        start=1,
    )
    for name in names
}

_MONTH = rf"(?:{'|'.join(sorted(MONTHS, key=len, reverse=True))})\.?"
_ERA = r"(?:BCE|BC|CE|AD)"
_YEAR = rf"\d{{1,4}}(?:\s*{_ERA})?"
# Where no day or month number precedes it, a bare 1-2 digit number is not a
# credible year: "March 15" must not be read as the year 15.
_YEAR4 = rf"(?:\d{{3,4}}|\d{{1,4}}\s*{_ERA})"
_SEASONS = r"(?:spring|summer|autumn|fall|winter)"
# Ordered by specificity: the first alternative that matches at a position wins,
# so "15 March 44 BCE" is one DAY mention and not a MONTH plus a YEAR.
_DATE = "|".join(
    [
        r"\d{4}-\d{2}-\d{2}",
        rf"\d{{1,2}}(?:st|nd|rd|th)?\s+{_MONTH}\s+{_YEAR}",
        rf"{_MONTH}\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+{_YEAR}",
        rf"{_SEASONS}\s+{_YEAR4}",
        rf"\d{{1,2}}(?:st|nd|rd|th)\s+century(?:\s*{_ERA})?",
        r"\d{3,4}s",
        rf"{_MONTH}\s+{_YEAR4}",
        rf"\d{{1,4}}\s*{_ERA}",
        r"(?:1\d{3}|20\d{2})",
    ]
)
_RELATIVE = (
    r"(?:\d+|a|one|two|three|four|five|several|many)\s+"
    r"(?:years?|months?|days?|decades?|centuries|century)\s+"
    r"(?:later|earlier|afterwards?|after|before|ago)"
)
_MENTION = re.compile(
    rf"(?P<span>(?:from|between)\s+(?:{_DATE})\s+(?:to|until|and|through)\s+(?:{_DATE}))"
    rf"|(?P<dashed>(?:{_DATE})\s*[–—]\s*(?:{_DATE}))"
    rf"|(?P<relative>{_RELATIVE})"
    rf"|(?P<single>{_DATE})",
    re.IGNORECASE,
)
_DATE_ONLY = re.compile(_DATE, re.IGNORECASE)

# Hedging words immediately before a date change how much it can be trusted.
_APPROXIMATE = re.compile(r"(?:\bc\.|\bca\.|circa|around|about|roughly|approx\w*)\s*$", re.I)
_UNCERTAIN = re.compile(
    r"(?:possibly|perhaps|probably|allegedly|reportedly|may have|might have)\b\W*$", re.I
)
_HEDGE_WINDOW = 24


@dataclass(frozen=True)
class Mention:
    """One recognized expression, located in the block it was read from."""

    block_id: str
    start_offset: int
    end_offset: int
    text: str
    origin: TemporalOrigin
    precision: TemporalPrecision
    certainty: TemporalCertainty
    start_year: int | None = None
    start_month: int | None = None
    start_day: int | None = None
    end_year: int | None = None
    end_month: int | None = None
    end_day: int | None = None


def extract(document: NormalizedDocument) -> list[Mention]:
    """Every mention in the document, in block then source order."""
    return [
        mention for block in document.blocks for mention in extract_from(block.id, block.text)
    ]


def extract_from(block_id: str, text: str) -> list[Mention]:
    mentions = []
    for match in _MENTION.finditer(text):
        kind = match.lastgroup
        certainty = _certainty(text[max(0, match.start() - _HEDGE_WINDOW) : match.start()])
        if kind == "relative":
            # Preserved, never resolved: local context is not enough to place it,
            # and an unplaced expression is by definition uncertain.
            values = {}
            precision, certainty = TemporalPrecision.UNKNOWN, TemporalCertainty.UNCERTAIN
        elif kind in ("span", "dashed"):
            first, second = _DATE_ONLY.findall(match.group())[:2] or ["", ""]
            precision, values = _range(first, second)
        else:
            precision, values = _single(match.group())
        mentions.append(
            Mention(
                block_id=block_id,
                start_offset=match.start(),
                end_offset=match.end(),
                text=match.group(),
                # V1 extracts from content only; a version's own metadata dates
                # would carry SOURCE_METADATA and are not read in this slice.
                origin=TemporalOrigin.CONTENT_MENTION,
                precision=precision,
                certainty=certainty,
                **values,
            )
        )
    return mentions


def _certainty(before: str) -> TemporalCertainty:
    if _UNCERTAIN.search(before):
        return TemporalCertainty.UNCERTAIN
    if _APPROXIMATE.search(before):
        return TemporalCertainty.APPROXIMATE
    return TemporalCertainty.EXACT


def _range(first: str, second: str) -> tuple[TemporalPrecision, dict]:
    """One mention with both bounds (§12), taking the widest reading of each end."""
    _, start = _single(first)
    _, end = _single(second)
    bounds = {key: value for key, value in start.items() if key.startswith("start_")}
    for key, value in end.items():
        # The far end of the range is the far end of its own last unit: "the
        # 1940s to the 1960s" ends in 1969, not 1960.
        bounds[key.replace("start_", "end_")] = value
    return TemporalPrecision.RANGE, bounds


def _single(text: str) -> tuple[TemporalPrecision, dict]:
    """Precision and normalized values for one recognized date expression."""
    text = text.strip()
    sign = -1 if re.search(r"\bBCE?\b", text, re.I) else 1
    numbers = [int(n) for n in re.findall(r"\d+", re.sub(r"\b(?:BCE?|CE|AD)\b", "", text, flags=re.I))]
    month = next((MONTHS[m.lower().rstrip(".")] for m in re.findall(_MONTH, text, re.I) if m.lower().rstrip(".") in MONTHS), None)

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        year, month, day = numbers
        return TemporalPrecision.DAY, {"start_year": year, "start_month": month, "start_day": day}
    if re.search(r"\d{3,4}s$", text):
        decade = numbers[0] * sign
        return TemporalPrecision.DECADE, {"start_year": decade, "end_year": decade + 9}
    if re.search(r"century", text, re.I):
        index = numbers[0]
        first_year, last_year = (index - 1) * 100 + 1, index * 100
        if sign < 0:
            first_year, last_year = -last_year, -first_year
        return TemporalPrecision.CENTURY, {"start_year": first_year, "end_year": last_year}
    if re.match(_SEASONS, text, re.I):
        # Season → months is hemisphere-dependent, so only the year is safe.
        return TemporalPrecision.SEASON, {"start_year": numbers[-1] * sign}
    if month is not None and len(numbers) >= 2:
        day, year = (numbers[0], numbers[-1])
        return TemporalPrecision.DAY, {"start_year": year * sign, "start_month": month, "start_day": day}
    if month is not None and numbers:
        return TemporalPrecision.MONTH, {"start_year": numbers[0] * sign, "start_month": month}
    if numbers:
        return TemporalPrecision.YEAR, {"start_year": numbers[0] * sign}
    return TemporalPrecision.UNKNOWN, {}
