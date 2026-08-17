"""Golden-file tests for the parsers, plus the validation rules.

The goldens are the contract: a parser change that moves a block boundary or a
section path changes chunk identity downstream, so it has to be a visible diff
in review. Regenerate deliberately with UPDATE_GOLDEN=1.
"""

import json
import os
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfWriter

from astrag.ingest.normalized import BlockType, NormalizedDocument
from astrag.ingest.parsers import (
    MIN_USEFUL_CHARS,
    ParseError,
    parse,
    parser_for,
)

GOLDEN = Path(__file__).parent / "golden"
MEDIA_TYPES = {".txt": "text/plain", ".md": "text/markdown", ".pdf": "application/pdf"}


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
    assert code_of(lambda: parser_for("image/png")) == "unsupported_media_type"


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


def pdf(**pages) -> bytes:
    """A PDF built from the golden one, since authoring text content by hand is
    not what these tests are about."""
    writer = PdfWriter(clone_from=GOLDEN / "rome.pdf")
    for key, value in pages.items():
        getattr(writer, key)(value)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


ROME_PDF = (GOLDEN / "rome.pdf").read_bytes()


def test_pdf_blocks_carry_the_page_they_came_from():
    """§11: page provenance is the one thing only a paginated format can give."""
    document = parse(ROME_PDF, "application/pdf", "rome.pdf")

    assert [b.page for b in document.blocks] == [1, 1, 2, 2, 3, 3]


def test_pdf_running_headers_and_footers_are_removed_and_named():
    document = parse(ROME_PDF, "application/pdf", "rome.pdf")

    texts = [b.text for b in document.blocks]
    assert "A History of Rome" not in texts  # the header on every page
    assert not any(t.startswith("Page ") for t in texts)  # the numbered footer
    # Removed, but not silently: the cleanup stays inspectable (§16).
    assert document.warnings == [
        "removed repeated line 'A History of Rome'",
        "removed repeated line 'Page 1'",
    ]


def test_a_line_repeated_on_too_few_pages_is_kept():
    """Two pages sharing a first line is a coincidence, not page furniture."""
    writer = PdfWriter(clone_from=GOLDEN / "rome.pdf")
    del writer.pages[2]
    buffer = BytesIO()
    writer.write(buffer)

    document = parse(buffer.getvalue(), "application/pdf", "two.pdf")

    assert "A History of Rome" in [b.text for b in document.blocks]


def test_an_encrypted_pdf_fails_non_retryably():
    assert code_of(
        lambda: parse(pdf(encrypt="hunter2"), "application/pdf", "locked.pdf")
    ) == "encrypted_document"


def test_a_pdf_with_no_text_layer_is_reported_as_scanned():
    """An image-only export is a different problem for the uploader than an
    empty file, so it does not hide behind empty_extraction (§7)."""
    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(width=200, height=200)
    buffer = BytesIO()
    writer.write(buffer)

    assert code_of(
        lambda: parse(buffer.getvalue(), "application/pdf", "scan.pdf")
    ) == "scanned_or_image_only"


def test_corrupt_pdf_bytes_fail_non_retryably():
    assert code_of(
        lambda: parse(b"%PDF-1.4\nnot really a pdf at all\n", "application/pdf", "x.pdf")
    ) == "corrupt_document"
