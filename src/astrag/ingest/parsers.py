"""Format parsers behind one contract (§6), plus the validation that makes a
non-throwing parser count as success (§7).

TXT and Markdown only. PDF and DOCX join the registry in later rungs without
touching anything downstream, which is the entire point of the contract.
"""

import re
from abc import ABC, abstractmethod
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

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


class PdfParser(DocumentParser):
    """Text-extractable PDF, with page provenance (§11) and best-effort removal
    of repeated headers and footers (§16).

    pypdf rather than a layout engine: V1 needs ordered prose plus the page it
    came from, and nothing downstream can use column geometry or font metrics.

    ponytail: multi-column pages interleave, and tables arrive as paragraph text.
    Swap in a layout-aware extractor when a corpus makes that cost real.
    """

    media_types = frozenset({"application/pdf"})

    def parse(self, data: bytes, title: str) -> NormalizedDocument:
        pages = _page_texts(data)
        stripped, removed = _strip_running_lines(pages)

        blocks: list[Block] = []
        section: list[str] = []
        for number, text in enumerate(stripped, start=1):
            append_paragraphs(blocks, text, section, page=number)

        empty = sum(1 for text in stripped if not text.strip())
        if pages and empty == len(pages):
            # Every page turned the page and gave us nothing: this is a scan or
            # an image-only export, which is a different problem for the uploader
            # than a corrupt file, so it gets its own non-retryable code (§7).
            raise ParseError(
                "scanned_or_image_only",
                f"no text layer on any of {len(pages)} pages; OCR is out of V1 scope",
            )

        document = NormalizedDocument(title=title, blocks=blocks)
        if empty:
            document.warnings.append(
                f"{empty} of {len(pages)} pages had no extractable text"
            )
        # Named, not silently dropped: cleanup has to stay inspectable (§16).
        document.warnings += [f"removed repeated line {line!r}" for line in removed]
        return document


def _page_texts(data: bytes) -> list[str]:
    """Extracted text per page, or a ParseError for bytes that cannot yield any."""
    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            # An empty password covers the common "restricted permissions" case;
            # a real password is not something a retry will discover.
            if reader.decrypt("") == 0:
                raise ParseError(
                    "encrypted_document", "the PDF is password-protected"
                )
        return [_page_text(page) for page in reader.pages]
    except PdfReadError as error:
        raise ParseError("corrupt_document", f"unreadable PDF: {error}") from error


def _page_text(page) -> str:
    """One page's text.

    Layout mode, because it turns vertical gaps into blank lines — which is the
    paragraph structure the blocker splits on. Plain mode drops them and every
    page collapses into a single block. Runs of layout padding become one space;
    horizontal geometry is not evidence.

    A page that cannot be extracted at all is an empty page, not a failed
    document: the aggregate checks in the caller decide whether the document as a
    whole is usable (§7).
    """
    try:
        text = page.extract_text(extraction_mode="layout") or ""
    except Exception:  # noqa: BLE001 — any per-page failure means "no text here"
        return ""
    return _SPACES.sub(" ", text).replace("\r\n", "\n").replace("\r", "\n")


_SPACES = re.compile(r"[ \t]{2,}")
# Page furniture repeats; the numeral inside it does not.
_DIGITS = re.compile(r"\d+")
# Below this a "repeated" line is a coincidence, not a running header.
MIN_PAGES_FOR_RUNNING_LINES = 3


def _strip_running_lines(pages: list[str]) -> tuple[list[str], list[str]]:
    """Drop first/last lines that recur across pages, comparing with digits
    masked so `Page 3` and `Page 7` count as the same running footer.

    Blank lines are left alone: they are the paragraph boundaries the blocker
    splits on, so removing furniture must not also remove structure.
    """
    if len(pages) < MIN_PAGES_FOR_RUNNING_LINES:
        return pages, []

    lines = [text.split("\n") for text in pages]
    edges = [_edges(page) for page in lines]
    threshold = len(pages) / 2

    running: set[str] = set()
    removed: list[str] = []
    for position in (0, -1):
        counts: dict[str, list[str]] = {}
        for page, edge in zip(lines, edges):
            if edge:
                text = page[edge[position]].strip()
                counts.setdefault(_DIGITS.sub("#", text), []).append(text)
        for key, seen in counts.items():
            if len(seen) > threshold and key not in running:
                running.add(key)
                removed.append(seen[0])

    def cleaned(page: list[str], edge: tuple[int, int] | None) -> str:
        dropped = {
            i for i in (edge or ()) if _DIGITS.sub("#", page[i].strip()) in running
        }
        return "\n".join(line for i, line in enumerate(page) if i not in dropped)

    return [cleaned(page, edge) for page, edge in zip(lines, edges)], removed


def _edges(page: list[str]) -> tuple[int, int] | None:
    """Indices of the first and last non-blank line, where furniture lives."""
    filled = [i for i, line in enumerate(page) if line.strip()]
    return (filled[0], filled[-1]) if filled else None


PARSERS: tuple[DocumentParser, ...] = (TextParser(), MarkdownParser(), PdfParser())


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
