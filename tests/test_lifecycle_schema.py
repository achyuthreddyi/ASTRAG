"""The three architecture invariants the plan pushed into DDL, asserted against
the real database. If any of these stops raising, corrupted evidence becomes
silently possible.
"""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from astrag.models import (
    ActiveGenerationPointer,
    Corpus,
    Document,
    DocumentVersion,
    ProcessingGeneration,
    SearchRepresentationGeneration,
    VersionStatus,
)


def make_corpus(db, name="corpus") -> Corpus:
    corpus = Corpus(name=f"{name}-{uuid.uuid4()}")
    db.add(corpus)
    db.flush()
    return corpus


def make_document(db, corpus: Corpus) -> Document:
    document = Document(corpus_id=corpus.id, title="a document")
    db.add(document)
    db.flush()
    return document


def make_version(db, document: Document, source_hash="a" * 64, corpus_id=None, **kwargs):
    version = DocumentVersion(
        document_id=document.id,
        corpus_id=corpus_id or document.corpus_id,
        source_hash=source_hash,
        source_artifact_key=f"ab/{source_hash}",
        filename="doc.txt",
        media_type="text/plain",
        byte_size=12,
        **kwargs,
    )
    db.add(version)
    db.flush()
    return version


def test_same_bytes_twice_in_one_corpus_is_rejected(db):
    """Invariant 1: exact-byte idempotency is a constraint, not a convention."""
    corpus = make_corpus(db)
    make_version(db, make_document(db, corpus))

    with pytest.raises(IntegrityError, match="uq_document_versions_corpus_source_hash"):
        make_version(db, make_document(db, corpus))


def test_same_bytes_in_another_corpus_is_allowed(db):
    """The same source may be a distinct logical document in another corpus."""
    first = make_version(db, make_document(db, make_corpus(db, "one")))
    second = make_version(db, make_document(db, make_corpus(db, "two")))

    assert first.source_hash == second.source_hash


def test_two_in_flight_versions_for_one_document_are_rejected(db):
    """Invariant 2: only one replacement version may process at a time."""
    document = make_document(db, make_corpus(db))
    make_version(db, document, source_hash="b" * 64, status=VersionStatus.RUNNING)

    with pytest.raises(IntegrityError, match="uq_document_versions_one_in_flight"):
        make_version(db, document, source_hash="c" * 64, status=VersionStatus.PENDING)


def test_a_new_version_may_process_beside_a_ready_one(db):
    """The published version stays searchable while its replacement processes."""
    document = make_document(db, make_corpus(db))
    active = make_version(db, document, source_hash="d" * 64, status=VersionStatus.READY)
    replacement = make_version(db, document, source_hash="e" * 64, status=VersionStatus.RUNNING)

    assert {active.status, replacement.status} == {"READY", "RUNNING"}


def test_a_version_cannot_claim_a_corpus_its_document_is_not_in(db):
    """The denormalized corpus_id is trustworthy, not merely convenient.

    Stage 3 filters the corpus boundary on this copy, so a copy that could drift
    from the parent document would be a silent evidence-boundary leak.
    """
    document = make_document(db, make_corpus(db, "owning"))
    unrelated = make_corpus(db, "unrelated")

    with pytest.raises(IntegrityError, match="fk_document_versions_document_corpus"):
        make_version(db, document, corpus_id=unrelated.id)


def test_an_unknown_processing_generation_is_rejected(db):
    """Invariant 3: no row may reference a generation that does not exist."""
    document = make_document(db, make_corpus(db))

    with pytest.raises(IntegrityError, match="published_processing_generation_id"):
        make_version(db, document, published_processing_generation_id=uuid.uuid4())


def test_the_seeded_active_pointers_resolve(db):
    """The migration leaves exactly one row pointing at real generations."""
    pointer = db.scalars(select(ActiveGenerationPointer)).one()

    assert db.get(ProcessingGeneration, pointer.processing_generation_id)
    srg = db.get(
        SearchRepresentationGeneration, pointer.search_representation_generation_id
    )
    assert srg.config["dimensions"] == 1536


def test_a_second_pointer_row_is_rejected(db):
    """The global pointer is global: the table holds one row by construction."""
    pointer = db.scalars(select(ActiveGenerationPointer)).one()

    db.add(
        ActiveGenerationPointer(
            id=2,
            processing_generation_id=pointer.processing_generation_id,
            search_representation_generation_id=(
                pointer.search_representation_generation_id
            ),
        )
    )
    with pytest.raises(IntegrityError, match="ck_active_generation_pointer_single_row"):
        db.flush()


def test_deleting_a_corpus_removes_its_documents_and_versions(db):
    """V1 deletion is one cascading transaction, not a tombstone state machine."""
    corpus = make_corpus(db)
    version = make_version(db, make_document(db, corpus))

    db.delete(corpus)
    db.flush()

    # Queried rather than Session.get: the cascade happens in the database, and
    # the identity map would still hand back the cached instance.
    remaining_versions = select(DocumentVersion).where(DocumentVersion.id == version.id)
    remaining_documents = select(Document).where(Document.corpus_id == corpus.id)
    assert db.scalars(remaining_versions).all() == []
    assert db.scalars(remaining_documents).all() == []
