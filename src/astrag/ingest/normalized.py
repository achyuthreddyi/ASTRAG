"""The canonical normalized document (§5).

One format-independent ordered representation that every parser produces, so
chunking, temporal extraction and provenance never learn about file formats.
Persisted as an immutable JSON artifact, which is what lets a later re-chunk or
a new temporal extractor skip reparsing when the processing generation is
compatible.

Pydantic rather than plain dataclasses: it is already a dependency, and reading
an artifact back is a trust boundary worth validating.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class BlockType(StrEnum):
    HEADING = "HEADING"
    PARAGRAPH = "PARAGRAPH"
    LIST_ITEM = "LIST_ITEM"
    TABLE_TEXT = "TABLE_TEXT"
    UNKNOWN_TEXT = "UNKNOWN_TEXT"


class Block(BaseModel):
    """One structural unit, in source order."""

    # Stable within the document and referenced by chunk source spans, so it is
    # positional and never renumbered: b0001, b0002, ...
    id: str
    type: BlockType
    text: str
    # Heading depth for HEADING; the depth it sits under for everything else.
    level: int | None = None
    # Durable provenance: the heading trail above this block.
    section_path: list[str] = Field(default_factory=list)
    # Nullable because only paginated formats have meaningful pages (§11).
    page: int | None = None


class NormalizedDocument(BaseModel):
    title: str
    blocks: list[Block]
    # Quality observations that do not fail ingestion (§7).
    warnings: list[str] = Field(default_factory=list)

    def text_length(self) -> int:
        return sum(len(block.text) for block in self.blocks)


def block_id(index: int) -> str:
    return f"b{index:04d}"
