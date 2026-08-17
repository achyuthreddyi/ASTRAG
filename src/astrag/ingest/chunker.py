"""Structure-aware token-bounded chunking (§8, §9, §10).

Blocks in, chunks out, deterministically: the same normalized document under the
same config always produces the same ordinals, spans and text, which is what
makes every downstream stage safe to retry.

Two boundaries stop a chunk growing: a section change and the token target. Only
an oversized single block is ever split mid-unit, and only that split uses
overlap — combining whole units needs none, since nothing was cut.

ponytail: a table split across chunks does not repeat its header row (§8) —
table rows are already separate blocks, so it only bites on tables longer than
the target. Repeat the header when an evaluation shows table recall suffering.
"""

import hashlib
from dataclasses import dataclass, field
from functools import lru_cache

import tiktoken

from astrag.ingest.normalized import Block, BlockType, NormalizedDocument
from astrag.settings import ChunkingConfig


@dataclass(frozen=True)
class SourceSpan:
    """A slice of one normalized block. Whole-block unless the block was split."""

    block_id: str
    start: int
    end: int


@dataclass
class ChunkDraft:
    """A chunk before it becomes a row. Ordinal is its identity within the
    (version, processing generation) namespace."""

    ordinal: int
    source_text: str
    contextualized_text: str
    section_path: list[str]
    source_spans: list[SourceSpan]
    token_count: int
    page_start: int | None = None
    page_end: int | None = None

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.source_text.encode()).hexdigest()


@lru_cache
def token_encoding(name: str):
    return tiktoken.get_encoding(name)


def chunk_document(
    document: NormalizedDocument, config: ChunkingConfig | None = None
) -> list[ChunkDraft]:
    config = config or ChunkingConfig()
    encoding = token_encoding(config.tokenizer)
    builder = _Builder(document.title, config, encoding)

    for block in document.blocks:
        # A heading opens the section it names, so it leads its own chunk rather
        # than trailing the previous section's prose.
        if block.type == BlockType.HEADING:
            builder.flush()
            builder.section = [*block.section_path, block.text]
        elif block.section_path != builder.section:
            builder.flush()
            builder.section = list(block.section_path)
        for piece in _pieces(block, config, encoding):
            builder.add(block, piece)

    builder.flush()
    return builder.chunks


def _pieces(
    block: Block, config: ChunkingConfig, encoding
) -> list[tuple[int, int]]:
    """Character ranges of `block.text`. One range unless the block alone
    exceeds the hard maximum, in which case it is cut with overlap (§8)."""
    tokens = encoding.encode(block.text)
    if len(tokens) <= config.max_tokens:
        return [(0, len(block.text))]

    step = config.max_tokens - config.overlap_tokens
    ranges = []
    for begin in range(0, len(tokens), step):
        # Offsets are measured by decoding prefixes and then slicing the original
        # text, so a chunk's source_text is always literal source, never a
        # round-tripped approximation of it.
        start = len(encoding.decode(tokens[:begin]))
        end = len(encoding.decode(tokens[: begin + config.max_tokens]))
        ranges.append((start, end))
        if end >= len(block.text):
            break
    return ranges


@dataclass
class _Builder:
    title: str
    config: ChunkingConfig
    encoding: object
    section: list[str] = field(default_factory=list)
    chunks: list[ChunkDraft] = field(default_factory=list)
    _texts: list[str] = field(default_factory=list)
    _spans: list[SourceSpan] = field(default_factory=list)
    _pages: list[int] = field(default_factory=list)
    _tokens: int = 0
    # Pending content is nothing but a heading, which may not stand alone.
    _heading_only: bool = True

    def add(self, block: Block, piece: tuple[int, int]) -> None:
        start, end = piece
        text = block.text[start:end]
        tokens = len(self.encoding.encode(text))
        # A heading alone is not evidence, so it overshoots the target rather
        # than being published as a chunk of its own — up to the hard maximum.
        limit = (
            self.config.max_tokens if self._heading_only else self.config.target_tokens
        )
        # Overshooting is otherwise allowed only when nothing is pending: a
        # single oversized unit is already capped at max_tokens by _pieces.
        if self._texts and self._tokens + tokens > limit:
            self.flush()
        self._heading_only = self._heading_only and block.type == BlockType.HEADING
        self._texts.append(text)
        self._spans.append(SourceSpan(block.id, start, end))
        if block.page is not None:
            self._pages.append(block.page)
        self._tokens += tokens

    def flush(self) -> None:
        if not self._texts:
            return
        source_text = "\n\n".join(self._texts)
        self.chunks.append(
            ChunkDraft(
                ordinal=len(self.chunks),
                source_text=source_text,
                contextualized_text=contextualize(self.title, self.section, source_text),
                section_path=list(self.section),
                source_spans=list(self._spans),
                token_count=self._tokens,
                page_start=min(self._pages, default=None),
                page_end=max(self._pages, default=None),
            )
        )
        self._texts, self._spans, self._pages = [], [], []
        self._tokens, self._heading_only = 0, True


def contextualize(title: str, section_path: list[str], source_text: str) -> str:
    """Title and section hierarchy ahead of the source text, for embedding and
    lexical representation only (§9). No derived temporal metadata in V1."""
    return "\n\n".join([" > ".join([title, *section_path]), source_text])
