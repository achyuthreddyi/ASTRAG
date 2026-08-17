"""The pipeline stages, in order.

Each stage reads what it needs from durable state and writes its result there,
so resuming mid-pipeline needs nothing but the row. Rungs 7-10 append here.
"""

from sqlalchemy import delete, select

from astrag.ingest.chunker import chunk_document
from astrag.ingest.executor import Stage, StageContext, StageError
from astrag.ingest.normalized import NormalizedDocument
from astrag.ingest.parsers import ParseError, parse
from astrag.models import Chunk, IngestionRun
from astrag.settings import get_settings


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


# The pipeline. Rungs 8-10 extend this list.
STAGES: list[Stage] = [("parse", parse_stage), ("chunk", chunk_stage)]
