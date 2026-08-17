"""Golden-file tests for the parsers, plus the validation rules.

The goldens are the contract: a parser change that moves a block boundary or a
section path changes chunk identity downstream, so it has to be a visible diff
in review. Regenerate deliberately with UPDATE_GOLDEN=1.
"""

import json
import os
from pathlib import Path

import pytest

from astrag.ingest.normalized import BlockType, NormalizedDocument
from astrag.ingest.parsers import (
    MIN_USEFUL_CHARS,
    ParseError,
    parse,
    parser_for,
)

GOLDEN = Path(__file__).parent / "golden"
MEDIA_TYPES = {".txt": "text/plain", ".md": "text/markdown"}


@pytest.mark.parametrize("source", sorted(p for p in GOLDEN.iterdir() if p.suffix in MEDIA_TYPES), ids=lambda p: p.name)
def test_parsing_matches_the_golden_normalization(source: Path):
    document = parse(source.read_bytes(), MEDIA_TYPES[source.suffix], source.name)

    expected = source.with_suffix(source.suffix + ".json")
    actual = document.model_dump_json(indent=2) + "\n"
    if os.environ.get("UPDATE_GOLDEN"):
        expected.write_text(actual)
    assert json.loads(actual) == json.loads(expected.read_text())


def code_of(call) -> str:
    with pytest.raises(ParseError) as raised:
        call()
    return raised.value.code


def test_unsupported_media_type_has_no_parser():
    assert code_of(lambda: parser_for("application/pdf")) == "unsupported_media_type"


@pytest.mark.parametrize("data", [b"", b"   \n\n  \n", b"tiny"])
def test_unusable_extraction_is_rejected(data):
    """A parser returning without throwing is not success (§7)."""
    assert code_of(lambda: parse(data, "text/plain", "doc.txt")) == "empty_extraction"


def test_a_wrapped_plain_text_paragraph_is_one_block():
    document = parse(b"first line\nsecond line of the same thought.", "text/plain", "d.txt")

    assert [b.type for b in document.blocks] == [BlockType.PARAGRAPH]
    assert document.blocks[0].text == "first line second line of the same thought."


def test_a_short_unpunctuated_line_is_inferred_as_a_heading():
    document = parse(b"Chapter One\n\nThe first paragraph ends here.", "text/plain", "d.txt")

    assert [b.type for b in document.blocks] == [BlockType.HEADING, BlockType.PARAGRAPH]
    assert document.blocks[1].section_path == ["Chapter One"]


def test_markdown_section_paths_follow_heading_depth():
    document = parse(
        b"# Top\n\ntext one\n\n## Middle\n\ntext two\n\n# Other\n\ntext three",
        "text/markdown",
        "d.md",
    )

    paths = {b.text: b.section_path for b in document.blocks if b.type == BlockType.PARAGRAPH}
    assert paths == {
        "text one": ["Top"],
        "text two": ["Top", "Middle"],
        # A shallower heading closes the deeper section rather than nesting under it.
        "text three": ["Other"],
    }


def test_markdown_tables_keep_rows_and_drop_the_divider():
    document = parse(
        b"| a | b |\n| --- | --- |\n| 1 | 2 |\n", "text/markdown", "d.md"
    )

    assert [b.type for b in document.blocks] == [BlockType.TABLE_TEXT] * 2
    assert [b.text for b in document.blocks] == ["| a | b |", "| 1 | 2 |"]


def test_fenced_blocks_are_unclassified_text():
    document = parse(b"prose here\n\n```\nnot prose at all\n```\n", "text/markdown", "d.md")

    assert document.blocks[-1].type == BlockType.UNKNOWN_TEXT
    assert document.blocks[-1].text == "not prose at all"


def test_mostly_unclassified_text_warns_without_failing():
    document = parse(b"```\nfirst opaque fragment\n```\n", "text/markdown", "d.md")

    assert document.warnings == ["1 of 1 blocks are unclassified text"]


def test_an_artifact_round_trips():
    """The normalized document is read back from storage on resume, so the JSON
    form has to reconstruct it exactly."""
    document = parse((GOLDEN / "timeline.md").read_bytes(), "text/markdown", "timeline.md")

    assert NormalizedDocument.model_validate_json(document.model_dump_json()) == document


def test_min_useful_chars_is_the_documented_floor():
    assert MIN_USEFUL_CHARS == 16
