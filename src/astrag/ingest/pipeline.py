"""The pipeline stages, in order.

Each stage reads what it needs from durable state and writes its result there,
so resuming mid-pipeline needs nothing but the row. Rungs 7-10 append here.
"""

from sqlalchemy import select

from astrag.ingest.executor import Stage, StageContext, StageError
from astrag.ingest.parsers import ParseError, parse
from astrag.models import IngestionRun


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


# The pipeline. Rungs 7-10 extend this list.
STAGES: list[Stage] = [("parse", parse_stage)]
