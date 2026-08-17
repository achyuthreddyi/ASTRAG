"""The whole slice at once: upload through the API, let the real worker run the
real stages, and check that what comes out the far end is consistent — and that
a worker killed mid-pipeline picks up where it stopped without redoing or
duplicating what is already durable (§22).

The per-stage tests each check one stage. This one checks that they compose.
"""

import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select

from astrag.ingest.executor import run_once
from astrag.ingest.pipeline import STAGES
from astrag.models import (
    Chunk,
    Document,
    DocumentVersion,
    IngestionJob,
    IngestionRun,
    JobState,
    VersionStatus,
)
from astrag.models.representation import DIMENSIONS
from test_api_documents import corpus_id, replace, upload  # noqa: F401 — fixtures
from test_pipeline_chunk import chunks_of
from test_pipeline_embed import representations_of
from test_pipeline_parse import latest_run
from test_pipeline_temporal import mentions_of

SOURCE = b"""# Republic

The Republic was founded in 509 BCE.

## Fall

Caesar was killed on 15 March 44 BCE, and Augustus took power in 27 BCE.
"""


@pytest.fixture
def uploaded(client, corpus_id):
    def upload_document(content=SOURCE, name="timeline.md"):
        return upload(client, corpus_id, content, name).json()

    return upload_document


def version_of(db, body) -> DocumentVersion:
    return db.get(DocumentVersion, uuid.UUID(body["document_version_id"]))


def test_an_uploaded_document_becomes_searchable_evidence(client, db, store, uploaded):
    body = uploaded()

    assert run_once(db, store, STAGES) is not None

    version = version_of(db, body)
    chunks, mentions = chunks_of(db, version), mentions_of(db, version)
    representations = representations_of(db, version)

    # Published, active, and not degraded.
    assert version.status == VersionStatus.READY
    assert db.get(Document, version.document_id).active_version_id == version.id
    assert version.degraded_capabilities == {}

    # Every chunk carries its corpus boundary and both representations.
    assert chunks and [c.ordinal for c in chunks] == list(range(len(chunks)))
    assert {c.corpus_id for c in chunks} == {version.corpus_id}
    assert len(representations) == len(chunks)
    assert {len(r.embedding) for r in representations} == {DIMENSIONS}
    assert all(c.lexical for c in chunks)  # the generated lexical projection

    # Temporal evidence survived the whole pipeline anchored to its chunk.
    assert {m.text for m in mentions} >= {"509 BCE", "15 March 44 BCE", "27 BCE"}
    assert all(m.text in db.get(Chunk, m.chunk_id).source_text for m in mentions)

    status = client.get(f"/documents/{body['document_id']}").json()
    assert (status["status"], status["current_stage"]) == (VersionStatus.READY, "publish")
    assert status["active_version_id"] == body["document_version_id"]


def test_a_pdf_carries_its_page_provenance_all_the_way_to_the_chunks(
    client, db, store, corpus_id
):
    """§11: the page a claim came from is evidence, and only the parser knows it."""
    source = (Path(__file__).parent / "golden" / "rome.pdf").read_bytes()
    body = upload(client, corpus_id, source, "rome.pdf").json()

    run_once(db, store, STAGES)

    version = version_of(db, body)
    chunks = chunks_of(db, version)
    assert version.status == VersionStatus.READY
    # One section per page here, so each chunk names exactly the page it quotes.
    assert [(c.page_start, c.page_end) for c in chunks] == [(1, 1), (2, 2), (3, 3)]
    assert {m.text for m in mentions_of(db, version)} >= {"509 BCE", "15 March 44 BCE"}


def kill_worker_after(db, store, version, stages: int) -> None:
    """Run a prefix of the pipeline, then leave the wreckage a crash leaves:
    the job still claimed, the attempt still unfinished, no settled version."""
    run_once(db, store, STAGES[:stages])
    job = db.scalars(
        select(IngestionJob).where(IngestionJob.document_version_id == version.id)
    ).one()
    job.state = JobState.CLAIMED
    job.heartbeat_at = db.scalar(select(func.now())) - timedelta(hours=1)
    run = latest_run(db, version)
    run.finished_at, run.stage = None, STAGES[stages][0]
    version.status = VersionStatus.RUNNING
    db.commit()


def test_a_worker_killed_mid_pipeline_resumes_without_redoing_its_work(
    db, store, uploaded
):
    body = uploaded()
    version = version_of(db, body)
    kill_worker_after(db, store, version, stages=3)  # died after temporal, before embed
    before = {c.id: c.content_hash for c in chunks_of(db, version)}
    artifact_key = latest_run(db, version).normalized_artifact_key
    assert representations_of(db, version) == []

    assert run_once(db, store, STAGES) is not None

    # The crashed attempt was continued, not restarted.
    assert db.scalar(
        select(func.count())
        .select_from(IngestionRun)
        .where(IngestionRun.document_version_id == version.id)
    ) == 1
    run = latest_run(db, version)
    assert run.normalized_artifact_key == artifact_key
    # Chunk identity survived, so the vectors now hang off the same rows.
    assert {c.id: c.content_hash for c in chunks_of(db, version)} == before
    assert len(representations_of(db, version)) == len(before)
    assert version.status == VersionStatus.READY
    assert db.get(Document, version.document_id).active_version_id == version.id


def test_a_replacement_is_only_activated_once_its_own_run_publishes(
    client, db, store, uploaded
):
    """§4: the searchable version never flickers while its replacement builds."""
    first = uploaded()
    run_once(db, store, STAGES)
    second = replace(client, first["document_id"], b"Augustus died in 14 CE.\n").json()
    original_id = uuid.UUID(first["document_version_id"])

    document = db.get(Document, uuid.UUID(first["document_id"]))
    assert document.active_version_id == original_id

    run_once(db, store, STAGES)

    db.refresh(document)
    assert document.active_version_id == uuid.UUID(second["document_version_id"])
    assert db.get(DocumentVersion, original_id).status == VersionStatus.READY
