"""The pipeline stages, in order.

Each stage reads what it needs from durable state and writes its result there,
so resuming mid-pipeline needs nothing but the row. Rungs 7-10 append here.
"""

import logging
from itertools import batched

from sqlalchemy import delete, select

from astrag.ingest.chunker import chunk_document, token_encoding
from astrag.ingest.embedding import EmbeddingError, get_embedder
from astrag.ingest.executor import Stage, StageContext, StageError
from astrag.ingest.normalized import NormalizedDocument
from astrag.ingest.parsers import ParseError, parse
from astrag.ingest.publish import validate
from astrag.ingest.temporal import Mention, extract
from astrag.models import (
    Chunk,
    ChunkRepresentation,
    Document,
    IngestionRun,
    TemporalMention,
    VersionStatus,
)
from astrag.settings import get_settings

log = logging.getLogger(__name__)


def parse_stage(ctx: StageContext) -> None:
    """Parse and normalize the immutable source bytes into an artifact."""
    reusable = _reusable_normalized_key(ctx)
    if reusable is not None:
        # An earlier attempt under this same generation already produced it, and
        # the source bytes are immutable, so reparsing could only agree.
        ctx.run.normalized_artifact_key = reusable
        return

    data = ctx.store.get(ctx.version.source_artifact_key)
    try:
        document = parse(data, ctx.version.media_type, ctx.version.filename)
    except ParseError as error:
        # Unsupported, corrupt or non-extractable input fails non-retryably (§7):
        # the same bytes will not parse differently next time.
        raise StageError(error.code, str(error), retryable=False) from error

    ctx.run.normalized_artifact_key = ctx.store.put(
        document.model_dump_json(indent=2).encode()
    )
    # Warnings ride along inside the artifact; error_* is for failures only.


def _reusable_normalized_key(ctx: StageContext) -> str | None:
    return ctx.db.scalars(
        select(IngestionRun.normalized_artifact_key)
        .where(
            IngestionRun.document_version_id == ctx.version.id,
            IngestionRun.processing_generation_id == ctx.run.processing_generation_id,
            IngestionRun.normalized_artifact_key.is_not(None),
        )
        .order_by(IngestionRun.attempt.desc())
    ).first()


def chunk_stage(ctx: StageContext) -> None:
    """Build this attempt's chunk set from the normalized document.

    Reconciled by ordinal rather than rebuilt from scratch: chunk identity is
    (version, generation, ordinal), so a retry that produced the same text must
    leave the same rows standing — dropping and reinserting them would cascade
    away vectors that were already bought and paid for.
    """
    document = NormalizedDocument.model_validate_json(
        ctx.store.get(ctx.run.normalized_artifact_key)
    )
    stale = {
        chunk.ordinal: chunk
        for chunk in ctx.db.scalars(
            select(Chunk).where(
                Chunk.document_version_id == ctx.version.id,
                Chunk.processing_generation_id == ctx.run.processing_generation_id,
            )
        )
    }

    rewritten = []
    for draft in chunk_document(document, get_settings().chunking):
        fields = {
            "source_text": draft.source_text,
            "contextualized_text": draft.contextualized_text,
            "section_path": draft.section_path,
            "source_spans": [vars(span) for span in draft.source_spans],
            "page_start": draft.page_start,
            "page_end": draft.page_end,
            "content_hash": draft.content_hash,
            "token_count": draft.token_count,
        }
        chunk = stale.pop(draft.ordinal, None)
        if chunk is not None and chunk.content_hash == draft.content_hash:
            continue
        if chunk is None:
            chunk = Chunk(
                corpus_id=ctx.version.corpus_id,
                document_id=ctx.version.document_id,
                document_version_id=ctx.version.id,
                processing_generation_id=ctx.run.processing_generation_id,
                ordinal=draft.ordinal,
                **fields,
            )
            ctx.db.add(chunk)
            continue
        for name, value in fields.items():
            setattr(chunk, name, value)
        rewritten.append(chunk.id)

    # A chunk whose text changed keeps its identity but loses its projections:
    # the vector embedded the old text, and the mention offsets pointed into it.
    ctx.db.execute(
        delete(ChunkRepresentation).where(ChunkRepresentation.chunk_id.in_(rewritten))
    )
    # Whatever the new chunk set no longer has an ordinal for.
    ctx.db.execute(delete(Chunk).where(Chunk.id.in_([c.id for c in stale.values()])))


def temporal_stage(ctx: StageContext) -> None:
    """Extract temporal mentions and attach each to the chunk containing it.

    Zero mentions is success (§13). An extractor *failure* is not: the version
    stays publishable with temporal marked degraded, because semantic and
    lexical evidence are unaffected and losing the document entirely would be
    the worse answer.
    """
    document = NormalizedDocument.model_validate_json(
        ctx.store.get(ctx.run.normalized_artifact_key)
    )
    chunks = list(
        ctx.db.scalars(
            select(Chunk).where(
                Chunk.document_version_id == ctx.version.id,
                Chunk.processing_generation_id == ctx.run.processing_generation_id,
            )
        )
    )
    try:
        mentions = extract(document)
    except Exception:  # noqa: BLE001 — §13: degrade the capability, keep the evidence
        log.exception("temporal extraction failed for version %s", ctx.version.id)
        ctx.version.degraded_capabilities = {
            **ctx.version.degraded_capabilities,
            "temporal": "degraded",
        }
        return

    # Same rebuild-don't-append rule as chunking; the chunk cascade covers the
    # rows of any chunk this attempt replaced.
    ctx.db.execute(
        delete(TemporalMention).where(
            TemporalMention.chunk_id.in_([chunk.id for chunk in chunks])
        )
    )
    ctx.db.add_all(
        TemporalMention(chunk_id=chunk.id, **vars(mention))
        for chunk, mention in _associate(chunks, mentions)
    )


def _associate(
    chunks: list[Chunk], mentions: list[Mention]
) -> list[tuple[Chunk, Mention]]:
    """Pair each mention with every chunk whose source span contains it (§12).

    A mention inside an overlap belongs to both chunks, which is true: the
    wording really is in both. One cut across a mention by a forced split drops
    it from that chunk rather than storing half a date.
    """
    return [
        (chunk, mention)
        for chunk in chunks
        for span in chunk.source_spans
        for mention in mentions
        if span["block_id"] == mention.block_id
        and span["start"] <= mention.start_offset
        and mention.end_offset <= span["end"]
    ]


def embed_stage(ctx: StageContext) -> None:
    """Embed the contextualized text of every chunk still missing a vector.

    Only the missing ones: a retry that re-embedded the whole document would
    pay the provider again for work that is already durable. Dense
    representation is mandatory for searchability (§14), so a provider failure
    fails the attempt — retryably, since the same text will embed fine later.
    """
    settings = get_settings()
    pending = list(
        ctx.db.scalars(
            select(Chunk)
            .where(
                Chunk.document_version_id == ctx.version.id,
                Chunk.processing_generation_id == ctx.run.processing_generation_id,
                ~Chunk.id.in_(
                    select(ChunkRepresentation.chunk_id).where(
                        ChunkRepresentation.search_representation_generation_id
                        == ctx.run.search_representation_generation_id
                    )
                ),
            )
            .order_by(Chunk.ordinal)
        )
    )

    if not pending:
        return
    embedder = get_embedder()
    encoding = token_encoding(settings.chunking.tokenizer)

    for batch in batched(pending, settings.embedding_batch_size):
        texts = [chunk.contextualized_text for chunk in batch]
        try:
            vectors = embedder.embed(texts)
        except EmbeddingError as error:
            raise StageError("embedding_failed", str(error), retryable=True) from error
        ctx.db.add_all(
            ChunkRepresentation(
                chunk_id=chunk.id,
                search_representation_generation_id=(
                    ctx.run.search_representation_generation_id
                ),
                embedding=vector,
                model=embedder.model,
                input_tokens=len(encoding.encode(text)),
            )
            for chunk, text, vector in zip(batch, texts, vectors, strict=True)
        )
        # Commit per batch, so a provider outage halfway through a large
        # document does not throw away the batches already paid for.
        ctx.db.commit()


def publish_stage(ctx: StageContext) -> None:
    """Validate the built set, then activate it in one commit (§23).

    Validation failure is not retryable: nothing about waiting thirty seconds
    makes an unanchored span anchor itself, and a silently republished broken
    set is worse than a version that says it failed.
    """
    document = NormalizedDocument.model_validate_json(
        ctx.store.get(ctx.run.normalized_artifact_key)
    )
    failures = validate(ctx.db, ctx.version, ctx.run, document)
    if failures:
        raise StageError("publication_invalid", "; ".join(failures), retryable=False)

    # The cutover: which chunk set is published, which version is active, and
    # whether it is searchable, all in one transaction. A reader either sees the
    # previous version or this one, never a half-activated mixture.
    ctx.version.published_processing_generation_id = ctx.run.processing_generation_id
    ctx.version.status = (
        VersionStatus.READY_DEGRADED
        if ctx.version.degraded_capabilities
        else VersionStatus.READY
    )
    ctx.db.get(Document, ctx.version.document_id).active_version_id = ctx.version.id
    ctx.db.commit()


# The pipeline, end to end: nothing is searchable until publish says so.
STAGES: list[Stage] = [
    ("parse", parse_stage),
    ("chunk", chunk_stage),
    ("temporal", temporal_stage),
    ("embed", embed_stage),
    ("publish", publish_stage),
]
