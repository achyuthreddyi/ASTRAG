"""Golden-file tests for the chunker, plus the boundary rules behind them.

The goldens are the contract: chunk boundaries are chunk identity, so a change
to them has to be a visible diff in review. Regenerate with UPDATE_GOLDEN=1.
"""

import json
import os
from pathlib import Path

import pytest

from astrag.ingest.chunker import chunk_document, contextualize
from astrag.ingest.normalized import Block, BlockType, NormalizedDocument, block_id
from astrag.ingest.parsers import parse
from astrag.settings import ChunkingConfig

GOLDEN = Path(__file__).parent / "golden"
MEDIA_TYPES = {".txt": "text/plain", ".md": "text/markdown"}
# Small enough that a handful of sentences exercises combining and splitting.
TINY = ChunkingConfig(target_tokens=20, max_tokens=30, overlap_tokens=6)


def document(*blocks: Block, title="doc") -> NormalizedDocument:
    return NormalizedDocument(title=title, blocks=list(blocks))


def block(text, type=BlockType.PARAGRAPH, index=0, section=()) -> Block:
    return Block(
        id=block_id(index), type=type, text=text, section_path=list(section)
    )


@pytest.mark.parametrize(
    "source",
    sorted(p for p in GOLDEN.iterdir() if p.suffix in MEDIA_TYPES),
    ids=lambda p: p.name,
)
def test_chunking_matches_the_golden_chunk_set(source: Path):
    parsed = parse(source.read_bytes(), MEDIA_TYPES[source.suffix], source.name)

    chunks = chunk_document(parsed, TINY)

    expected = GOLDEN / f"{source.name}.chunks.json"
    actual = json.dumps([vars(c) | {"content_hash": c.content_hash, "source_spans": [vars(s) for s in c.source_spans]} for c in chunks], indent=2) + "\n"
    if os.environ.get("UPDATE_GOLDEN"):
        expected.write_text(actual)
    assert json.loads(actual) == json.loads(expected.read_text())


def test_units_combine_up_to_the_target():
    """Whole blocks are combined, not cut, while they fit."""
    chunks = chunk_document(
        document(block("one two three.", index=0), block("four five six.", index=1)),
        TINY,
    )

    assert len(chunks) == 1
    assert chunks[0].source_text == "one two three.\n\nfour five six."
    assert [s.block_id for s in chunks[0].source_spans] == ["b0000", "b0001"]


def test_a_section_change_ends_a_chunk():
    """A chunk never straddles two sections, however small they are (§8)."""
    chunks = chunk_document(
        document(
            block("intro.", index=0, section=["A"]),
            block("body.", index=1, section=["B"]),
        ),
        TINY,
    )

    assert [c.section_path for c in chunks] == [["A"], ["B"]]


def test_a_heading_leads_its_own_section():
    chunks = chunk_document(
        document(
            block("earlier prose.", index=0),
            block("Republic", BlockType.HEADING, index=1),
            block("founded in 509 BCE.", index=2, section=["Republic"]),
        ),
        TINY,
    )

    assert [c.section_path for c in chunks] == [[], ["Republic"]]
    assert chunks[1].source_text.startswith("Republic\n\n")


def test_an_oversized_block_is_split_with_overlap():
    """The only place overlap applies: a structural unit that had to be cut."""
    text = " ".join(f"word{n}" for n in range(120))

    chunks = chunk_document(document(block(text)), TINY)

    assert len(chunks) > 1
    assert all(c.token_count <= TINY.max_tokens for c in chunks)
    # Spans stay inside the one block and step back by the overlap each time.
    spans = [c.source_spans[0] for c in chunks]
    assert all(s.block_id == "b0000" for s in spans)
    assert all(later.start < earlier.end for earlier, later in zip(spans, spans[1:]))


def test_split_pieces_are_literal_source_text():
    """Source text is sliced from the block, never re-decoded from tokens."""
    text = " ".join(f"día{n}" for n in range(120))

    chunks = chunk_document(document(block(text)), TINY)

    for chunk in chunks:
        span = chunk.source_spans[0]
        assert chunk.source_text == text[span.start : span.end]
    assert chunks[-1].source_spans[0].end == len(text)


def test_ordinals_and_hashes_are_deterministic():
    parsed = parse((GOLDEN / "timeline.md").read_bytes(), "text/markdown", "timeline.md")

    first, second = chunk_document(parsed, TINY), chunk_document(parsed, TINY)

    assert [c.ordinal for c in first] == list(range(len(first)))
    assert [c.content_hash for c in first] == [c.content_hash for c in second]


def test_contextualized_text_leads_with_title_and_section():
    """Retrieval text only: citation must still quote source_text (§9)."""
    assert contextualize("Rome", ["Republic"], "founded in 509 BCE.") == (
        "Rome > Republic\n\nfounded in 509 BCE."
    )
