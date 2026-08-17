"""What the chunks table guarantees on its own: trustworthy lineage, unique
ordinals within a generation, and removal with the evidence it belongs to.
"""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from astrag.models import ActiveGenerationPointer, Chunk
from test_lifecycle_schema import make_corpus, make_document, make_version


def make_chunk(db, version, ordinal=0, generation_id=None, **kwargs):
    pointer = db.scalars(select(ActiveGenerationPointer)).one()
    chunk = Chunk(
        corpus_id=kwargs.pop("corpus_id", version.corpus_id),
        document_id=version.document_id,
        document_version_id=version.id,
        processing_generation_id=generation_id or pointer.processing_generation_id,
        ordinal=ordinal,
        source_text="The Republic was founded in 509 BCE.",
        contextualized_text="Rome > Republic\n\nThe Republic was founded in 509 BCE.",
        section_path=["Rome", "Republic"],
        source_spans=[{"block_id": "b0001", "start": 0, "end": 36}],
        content_hash="f" * 64,
        token_count=9,
        **kwargs,
    )
    db.add(chunk)
    db.flush()
    return chunk


def test_a_chunk_carries_its_whole_lineage(db):
    version = make_version(db, make_document(db, make_corpus(db)))

    chunk = make_chunk(db, version)

    assert (chunk.corpus_id, chunk.document_id) == (version.corpus_id, version.document_id)
    assert chunk.source_spans[0]["block_id"] == "b0001"


def test_two_chunks_may_hold_identical_text(db):
    """Identity is positional: a repeated sentence stays two occurrences (§10)."""
    version = make_version(db, make_document(db, make_corpus(db)))

    first, second = make_chunk(db, version, 0), make_chunk(db, version, 1)

    assert first.content_hash == second.content_hash
    assert first.id != second.id


def test_a_repeated_ordinal_in_one_generation_is_rejected(db):
    version = make_version(db, make_document(db, make_corpus(db)))
    make_chunk(db, version, ordinal=0)

    with pytest.raises(IntegrityError, match="uq_chunks_version_generation_ordinal"):
        make_chunk(db, version, ordinal=0)


def test_a_chunk_cannot_claim_a_corpus_its_version_is_not_in(db):
    """Stage 3 filters the corpus boundary on this copy, so it cannot drift."""
    version = make_version(db, make_document(db, make_corpus(db, "owning")))
    unrelated = make_corpus(db, "unrelated")

    with pytest.raises(IntegrityError, match="fk_chunks_version_document_corpus"):
        make_chunk(db, version, corpus_id=unrelated.id)


def test_an_unknown_processing_generation_is_rejected(db):
    version = make_version(db, make_document(db, make_corpus(db)))

    with pytest.raises(IntegrityError, match="processing_generation_id"):
        make_chunk(db, version, generation_id=uuid.uuid4())


def test_deleting_the_corpus_removes_its_chunks(db):
    corpus = make_corpus(db)
    chunk = make_chunk(db, make_version(db, make_document(db, corpus)))

    db.delete(corpus)
    db.flush()

    assert db.scalars(select(Chunk).where(Chunk.id == chunk.id)).all() == []
