"""Publication validation and activation (§23).

The gate between a private build and searchable evidence. Everything here is a
check that a partially built version cannot pass, because Stage 3 trusts what
publication activates: a chunk with no vector, a span pointing at a block that
does not exist, or a chunk set built under a different generation would all be
silently wrong answers rather than errors.

Several of §23's checks are already database constraints — lineage validity,
corpus consistency, one vector per chunk per generation. Those are re-asserted
here anyway: publication is cheap, runs once per version, and a constraint that
was dropped in a migration should surface as a refusal to publish rather than
as evidence nobody validated.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from astrag.ingest.normalized import NormalizedDocument
from astrag.models import (
    ActiveGenerationPointer,
    Chunk,
    ChunkRepresentation,
    DocumentVersion,
    IngestionRun,
    TemporalMention,
)


def validate(
    db: Session, version: DocumentVersion, run: IngestionRun, document: NormalizedDocument
) -> list[str]:
    """Every reason this version may not become searchable. Empty means go."""
    chunks = list(
        db.scalars(
            select(Chunk).where(
                Chunk.document_version_id == version.id,
                Chunk.processing_generation_id == run.processing_generation_id,
            )
        )
    )
    blocks = {block.id: len(block.text) for block in document.blocks}
    failures = []

    if not chunks:
        failures.append("no chunks were produced for this version and generation")
    if [c.ordinal for c in sorted(chunks, key=lambda c: c.ordinal)] != list(
        range(len(chunks))
    ):
        # A gap means a chunk was lost between building and publishing, and the
        # count Stage 3 sees would silently disagree with the count built.
        failures.append("chunk ordinals are not a complete sequence")

    wrong_lineage = [
        c.ordinal
        for c in chunks
        if (c.corpus_id, c.document_id) != (version.corpus_id, version.document_id)
    ]
    if wrong_lineage:
        failures.append(f"chunks {wrong_lineage} do not carry this version's lineage")

    unanchored = [
        c.ordinal
        for c in chunks
        if any(
            span["block_id"] not in blocks
            or not 0 <= span["start"] < span["end"] <= blocks[span["block_id"]]
            for span in c.source_spans
        )
    ]
    if unanchored:
        failures.append(f"chunks {unanchored} have spans outside the normalized source")

    represented = set(
        db.scalars(
            select(ChunkRepresentation.chunk_id).where(
                ChunkRepresentation.chunk_id.in_([c.id for c in chunks]),
                ChunkRepresentation.search_representation_generation_id
                == run.search_representation_generation_id,
            )
        )
    )
    missing = [c.ordinal for c in chunks if c.id not in represented]
    if missing:
        failures.append(f"chunks {missing} have no dense representation")

    # The lexical column is generated, so an empty one means empty text rather
    # than a skipped step — still not searchable evidence.
    lexical_gaps = db.scalar(
        select(func.count())
        .select_from(Chunk)
        .where(Chunk.id.in_([c.id for c in chunks]), Chunk.lexical == func.to_tsvector(""))
    )
    if lexical_gaps:
        failures.append(f"{lexical_gaps} chunks have an empty lexical representation")

    active = db.scalars(select(ActiveGenerationPointer)).one()
    if run.search_representation_generation_id != (
        active.search_representation_generation_id
    ):
        # Publishing under a superseded SRG would expose vectors Stage 3 filters
        # out, which reads as a document that ingested fine and finds nothing.
        failures.append("this run's search representation generation is not the active one")

    if "temporal" not in version.degraded_capabilities:
        broken = db.scalar(
            select(func.count())
            .select_from(TemporalMention)
            .where(
                TemporalMention.chunk_id.in_([c.id for c in chunks]),
                TemporalMention.start_offset >= TemporalMention.end_offset,
            )
        )
        if broken:
            failures.append(f"{broken} temporal mentions have invalid offsets")

    return failures
