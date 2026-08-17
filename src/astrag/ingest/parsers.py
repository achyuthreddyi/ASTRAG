"""Format parsers behind one contract (§6), plus the validation that makes a
non-throwing parser count as success (§7).

TXT and Markdown only. PDF and DOCX join the registry in later rungs without
touching anything downstream, which is the entire point of the contract.
"""

import re
from abc import ABC, abstractmethod

from astrag.ingest.normalized import Block, BlockType, NormalizedDocument, block_id

# Below this, "it parsed" is not credible evidence that it extracted anything.
MIN_USEFUL_CHARS = 16
# An unusual share of unclassifiable text is worth recording, not failing on.
UNKNOWN_RATIO_WARNING = 0.5


class ParseError(Exception):
    """Extraction produced nothing usable. Never retryable: the bytes will not
    improve on a second attempt."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class DocumentParser(ABC):
    media_types: frozenset[str] = frozenset()

    def supports(self, media_type: str) -> bool:
        return media_type in self.media_types

    @abstractmethod
    def parse(self, data: bytes, title: str) -> NormalizedDocument: ...


def decode(data: bytes) -> str:
    """UTF-8 with replacement, then normalize line endings.

    Replacement rather than strict: a handful of bad bytes in an otherwise
    readable document is a quality warning, not a reason to lose the evidence.
    The empty-extraction check below is what catches genuinely unreadable input.
    """
    return data.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")


def append_paragraphs(
    blocks: list[Block], text: str, section: list[str], page: int | None = None
) -> None:
    """Split unstructured text into blocks and append them in source order.

    `section` is mutated in place as headings are found, so a caller feeding one
    page at a time keeps its section path across the page boundary.
    """
    for paragraph in re.split(r"\n\s*\n", text):
        stripped = paragraph.strip()
        if not stripped:
            continue
        if _looks_like_heading(stripped):
            section[:] = [stripped]
            blocks.append(
                Block(id=block_id(len(blocks)), type=BlockType.HEADING, text=stripped,
                      level=1, section_path=[], page=page)
            )
            continue
        blocks.append(
            Block(
                id=block_id(len(blocks)),
                type=BlockType.PARAGRAPH,
                # A wrapped paragraph is one unit; the line breaks inside it are
                # presentation, not structure.
                text=" ".join(line.strip() for line in stripped.split("\n")),
                level=1 if section else None,
                section_path=list(section),
                page=page,
            )
        )


class TextParser(DocumentParser):
    """TXT: paragraph and order structure with minimal heading inference (§5)."""

    media_types = frozenset({"text/plain"})

    def parse(self, data: bytes, title: str) -> NormalizedDocument:
        blocks: list[Block] = []
        append_paragraphs(blocks, decode(data), [])
        return NormalizedDocument(title=title, blocks=blocks)


def _looks_like_heading(text: str) -> bool:
    """A short single line with no sentence punctuation. Deliberately timid: a
    missed heading costs a section path, a false one invents structure."""
    return (
        "\n" not in text
        and len(text) <= 80
        and not text.endswith((".", "!", "?", ",", ";", ":"))
    )


_ATX = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$")
_FENCE = re.compile(r"^\s*(?:```|~~~)")


class MarkdownParser(DocumentParser):
    """Markdown: headings create the section hierarchy (§5).

    A line scanner rather than a Markdown library: the five V1 block types need
    headings, list items, tables and paragraphs, and a full AST would still have
    to be flattened to exactly this.

    ponytail: setext headings, nested lists, block quotes and inline HTML land as
    paragraph text. Swap in markdown-it-py if a corpus makes that cost real.
    """

    media_types = frozenset({"text/markdown"})

    def parse(self, data: bytes, title: str) -> NormalizedDocument:
        blocks: list[Block] = []
        # Heading text by depth, so the section path is whatever is above us.
        hierarchy: dict[int, str] = {}
        paragraph: list[str] = []
        fenced = False

        def flush(kind: BlockType = BlockType.PARAGRAPH) -> None:
            if paragraph:
                add(" ".join(paragraph), kind)
                paragraph.clear()

        def add(text: str, kind: BlockType) -> None:
            level = max(hierarchy) if hierarchy else None
            blocks.append(
                Block(
                    id=block_id(len(blocks)),
                    type=kind,
                    text=text,
                    level=level,
                    section_path=[hierarchy[d] for d in sorted(hierarchy)],
                )
            )

        for line in decode(data).split("\n"):
            if _FENCE.match(line):
                # A fenced block is code or data: unclassifiable prose either way.
                flush(BlockType.UNKNOWN_TEXT if fenced else BlockType.PARAGRAPH)
                fenced = not fenced
                continue
            if fenced:
                paragraph.append(line)
                continue
            if not line.strip():
                flush()
                continue

            heading = _ATX.match(line)
            if heading:
                flush()
                depth = len(heading.group(1))
                # Entering a shallower heading closes every deeper section.
                for deeper in [d for d in hierarchy if d >= depth]:
                    del hierarchy[deeper]
                text = heading.group(2).strip()
                add(text, BlockType.HEADING)
                blocks[-1].level = depth
                blocks[-1].section_path = [hierarchy[d] for d in sorted(hierarchy)]
                hierarchy[depth] = text
                continue

            if _is_table_row(line):
                flush()
                if not _is_table_divider(line):
                    add(line.strip(), BlockType.TABLE_TEXT)
                continue

            bullet = _BULLET.match(line)
            if bullet:
                flush()
                add(bullet.group(1).strip(), BlockType.LIST_ITEM)
                continue

            paragraph.append(line.strip())

        flush(BlockType.UNKNOWN_TEXT if fenced else BlockType.PARAGRAPH)
        return NormalizedDocument(title=title, blocks=blocks)


def _is_table_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|") and len(stripped) > 1


def _is_table_divider(line: str) -> bool:
    return bool(re.fullmatch(r"\|[\s:|-]+\|", line.strip()))


PARSERS: tuple[DocumentParser, ...] = (TextParser(), MarkdownParser())


def parser_for(media_type: str) -> DocumentParser:
    for parser in PARSERS:
        if parser.supports(media_type):
            return parser
    raise ParseError("unsupported_media_type", f"no parser for {media_type}")


def parse(data: bytes, media_type: str, title: str) -> NormalizedDocument:
    """Parse and validate. Returning without throwing is not success (§7)."""
    document = parser_for(media_type).parse(data, title)
    return validate(document)


def validate(document: NormalizedDocument) -> NormalizedDocument:
    if not document.blocks or document.text_length() < MIN_USEFUL_CHARS:
        raise ParseError(
            "empty_extraction",
            f"extracted {document.text_length()} usable characters from "
            f"{len(document.blocks)} blocks",
        )
    if any(block.id != block_id(index) for index, block in enumerate(document.blocks)):
        raise ParseError("block_order", "block ids are not sequential in source order")

    unknown = sum(1 for block in document.blocks if block.type == BlockType.UNKNOWN_TEXT)
    if unknown / len(document.blocks) > UNKNOWN_RATIO_WARNING:
        document.warnings.append(
            f"{unknown} of {len(document.blocks)} blocks are unclassified text"
        )
    return document
