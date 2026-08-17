"""The pipeline stages, in order.

Each stage reads what it needs from durable state and writes its result there,
so resuming mid-pipeline needs nothing but the row. Rungs 7-10 append here.
"""

import logging

from sqlalchemy import delete, select

from astrag.ingest.chunker import chunk_document
from astrag.ingest.executor import Stage, StageContext, StageError
from astrag.ingest.normalized import NormalizedDocument
from astrag.ingest.parsers import ParseError, parse
from astrag.ingest.temporal import Mention, extract
from astrag.models import Chunk, IngestionRun, TemporalMention
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
    """Build this attempt's chunk set from the normalized document."""
    document = NormalizedDocument.model_validate_json(
        ctx.store.get(ctx.run.normalized_artifact_key)
    )
    # A retry re-runs the whole stage, so the previous attempt's partial chunk
    # set is replaced rather than added to. Chunk identity is deterministic, so
    # the rebuilt set is the same set.
    ctx.db.execute(
        delete(Chunk).where(
            Chunk.document_version_id == ctx.version.id,
            Chunk.processing_generation_id == ctx.run.processing_generation_id,
        )
    )
    ctx.db.add_all(
        Chunk(
            corpus_id=ctx.version.corpus_id,
            document_id=ctx.version.document_id,
            document_version_id=ctx.version.id,
            processing_generation_id=ctx.run.processing_generation_id,
            ordinal=draft.ordinal,
            source_text=draft.source_text,
            contextualized_text=draft.contextualized_text,
            section_path=draft.section_path,
            source_spans=[vars(span) for span in draft.source_spans],
            page_start=draft.page_start,
            page_end=draft.page_end,
            content_hash=draft.content_hash,
            token_count=draft.token_count,
        )
        for draft in chunk_document(document, get_settings().chunking)
    )


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


# The pipeline. Rungs 9-10 extend this list.
STAGES: list[Stage] = [
    ("parse", parse_stage),
    ("chunk", chunk_stage),
    ("temporal", temporal_stage),
]
