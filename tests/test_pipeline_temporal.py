"""The temporal stage inside the real executor: mentions land on the chunk that
contains them, an empty document is still a success, and an extractor failure
degrades the capability instead of losing the evidence.
"""

from sqlalchemy import select

from astrag.ingest.executor import run_once
from astrag.ingest.pipeline import STAGES
from astrag.models import Chunk, TemporalMention, VersionStatus
from test_pipeline_chunk import chunks_of
from test_pipeline_parse import enqueued  # noqa: F401 — fixture


def mentions_of(db, version) -> list[TemporalMention]:
    return list(
        db.scalars(
            select(TemporalMention)
            .join(Chunk, Chunk.id == TemporalMention.chunk_id)
            .where(Chunk.document_version_id == version.id)
            .order_by(TemporalMention.start_offset)
        )
    )


def test_mentions_attach_to_the_chunk_that_contains_them(db, store, enqueued):
    version = enqueued()

    run_once(db, store, STAGES)

    mention = mentions_of(db, version)[0]
    chunk = db.get(Chunk, mention.chunk_id)
    assert (mention.text, mention.start_year) == ("509 BCE", -509)
    assert mention.text in chunk.source_text
    assert mention.block_id in {span["block_id"] for span in chunk.source_spans}
    assert version.status == VersionStatus.READY


def test_a_document_without_dates_is_a_plain_success(db, store, enqueued):
    """§13: zero mentions is extraction working, not extraction failing."""
    version = enqueued(
        data=b"A note with no dates in it at all, only prose about nothing.",
        media_type="text/plain",
        filename="undated.txt",
    )

    run_once(db, store, STAGES)

    assert mentions_of(db, version) == []
    assert version.status == VersionStatus.READY
    assert version.degraded_capabilities == {}


def test_an_extractor_failure_degrades_instead_of_failing(db, store, enqueued, monkeypatch):
    """§13: semantic and lexical evidence are unaffected, so the version stays
    publishable with temporal marked degraded."""
    version = enqueued()
    monkeypatch.setattr(
        "astrag.ingest.pipeline.extract",
        lambda _: (_ for _ in ()).throw(RuntimeError("extractor exploded")),
    )

    run_once(db, store, STAGES)

    assert version.degraded_capabilities == {"temporal": "degraded"}
    assert version.status == VersionStatus.READY_DEGRADED
    assert chunks_of(db, version) != []
    assert mentions_of(db, version) == []


def test_the_stage_is_last_in_the_pipeline():
    assert [name for name, _ in STAGES] == ["parse", "chunk", "temporal"]
