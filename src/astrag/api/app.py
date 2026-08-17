"""HTTP surface for the corpus and document lifecycle.

Upload is asynchronous (§18): the request validates cheaply, hashes the exact
uploaded bytes, persists source and version state as PENDING, and returns
identifiers. The worker (rung 5) runs the pipeline.

No search endpoint — that is stage 3 — and no auth, since V1 is single tenant.
"""

import hashlib
import uuid
from datetime import datetime
from pathlib import PurePosixPath

from fastapi import Depends, FastAPI, File, HTTPException, Response, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from astrag.models import (
    Corpus,
    Document,
    DocumentVersion,
    IngestionJob,
    IngestionRun,
    VersionStatus,
)
from astrag.settings import get_settings
from astrag.storage.artifacts import ArtifactStore, get_artifact_store
from astrag.storage.database import get_db

app = FastAPI(title="ASTRAG", version="0.1.0")

# Extension, not the client-declared content type, which browsers get wrong.
# PDF and DOCX join this registry in rungs 13 and 14.
MEDIA_TYPES = {".txt": "text/plain", ".md": "text/markdown", ".markdown": "text/markdown"}

IN_FLIGHT = (VersionStatus.PENDING, VersionStatus.RUNNING)


class CorpusIn(BaseModel):
    name: str
    description: str | None = None


class CorpusOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


@app.post("/corpora", response_model=CorpusOut, status_code=status.HTTP_201_CREATED)
def create_corpus(body: CorpusIn, db: Session = Depends(get_db)) -> Corpus:
    corpus = Corpus(name=body.name, description=body.description)
    db.add(corpus)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"a corpus named {body.name!r} already exists"
        ) from None
    db.refresh(corpus)
    return corpus


@app.get("/corpora", response_model=list[CorpusOut])
def list_corpora(db: Session = Depends(get_db)) -> list[Corpus]:
    return list(db.scalars(select(Corpus).order_by(Corpus.created_at)))


class VersionOut(BaseModel):
    document_id: uuid.UUID
    document_version_id: uuid.UUID
    status: VersionStatus


def _out(version: DocumentVersion) -> VersionOut:
    return VersionOut(
        document_id=version.document_id,
        document_version_id=version.id,
        status=version.status,
    )


def _read_upload(file: UploadFile) -> tuple[bytes, str]:
    """Cheap synchronous validation, before anything durable is written."""
    suffix = PurePosixPath(file.filename or "").suffix.lower()
    if suffix not in MEDIA_TYPES:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"unsupported file type {suffix or '(none)'}; expected {sorted(MEDIA_TYPES)}",
        )
    limit = get_settings().max_upload_bytes
    # One byte past the limit is enough to know it is over it.
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, f"upload exceeds {limit} bytes"
        )
    if not data.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "upload is empty")
    return data, MEDIA_TYPES[suffix]


def _existing_version(db: Session, corpus_id: uuid.UUID, source_hash: str):
    """The corpus-scoped exact-byte duplicate, if there is one (§2)."""
    return db.scalars(
        select(DocumentVersion).where(
            DocumentVersion.corpus_id == corpus_id,
            DocumentVersion.source_hash == source_hash,
        )
    ).one_or_none()


def _add_version(db: Session, document: Document, data: bytes, media_type: str,
                 filename: str, store: ArtifactStore) -> DocumentVersion:
    version = DocumentVersion(
        document_id=document.id,
        corpus_id=document.corpus_id,
        source_hash=hashlib.sha256(data).hexdigest(),
        # Content-addressed, so re-storing the same bytes is a no-op. A blob
        # orphaned by a failed commit is harmless; GC is deferred.
        source_artifact_key=store.put(data),
        filename=filename,
        media_type=media_type,
        byte_size=len(data),
        status=VersionStatus.PENDING,
    )
    db.add(version)
    db.flush()
    # Enqueued in the same transaction as the version: a version the worker will
    # never see is worse than no version at all.
    db.add(IngestionJob(document_version_id=version.id))
    return version


@app.post(
    "/corpora/{corpus_id}/documents",
    response_model=VersionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_document(
    corpus_id: uuid.UUID,
    response: Response,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    store: ArtifactStore = Depends(get_artifact_store),
) -> VersionOut:
    corpus = db.get(Corpus, corpus_id)
    if corpus is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no corpus {corpus_id}")
    data, media_type = _read_upload(file)
    source_hash = hashlib.sha256(data).hexdigest()

    duplicate = _existing_version(db, corpus_id, source_hash)
    if duplicate is not None:
        response.status_code = status.HTTP_200_OK
        return _out(duplicate)

    filename = file.filename or "untitled"
    document = Document(corpus_id=corpus_id, title=filename)
    db.add(document)
    db.flush()
    version = _add_version(db, document, data, media_type, filename, store)
    try:
        db.commit()
    except IntegrityError:
        # A concurrent identical upload won the idempotency race. Returning its
        # row is the whole point of the constraint: never two logical documents
        # for one set of bytes in one corpus.
        db.rollback()
        response.status_code = status.HTTP_200_OK
        return _out(_existing_version(db, corpus_id, source_hash))
    return _out(version)


class StatusOut(BaseModel):
    """The ingestion status contract. Reports the newest version — the one being
    processed — alongside the version that is actually searchable, because
    during a replacement those are deliberately not the same one (§4)."""

    document_id: uuid.UUID
    document_version_id: uuid.UUID
    active_version_id: uuid.UUID | None
    ingestion_run_id: uuid.UUID | None
    status: VersionStatus
    current_stage: str | None
    degraded_capabilities: dict
    error_summary: str | None
    created_at: datetime
    updated_at: datetime


@app.get("/documents/{document_id}", response_model=StatusOut)
def get_document(document_id: uuid.UUID, db: Session = Depends(get_db)) -> StatusOut:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no document {document_id}")
    # The version worth reporting on is the one being processed; failing that,
    # the active one; failing that, the newest. created_at cannot break the tie
    # on its own — two versions created in one transaction share a timestamp.
    versions = list(
        db.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.created_at.desc())
        )
    )
    version = next(
        (v for v in versions if v.status in IN_FLIGHT),
        next((v for v in versions if v.id == document.active_version_id), versions[0]),
    )
    run = db.scalars(
        select(IngestionRun)
        .where(IngestionRun.document_version_id == version.id)
        .order_by(IngestionRun.attempt.desc())
    ).first()
    return StatusOut(
        document_id=document.id,
        document_version_id=version.id,
        active_version_id=document.active_version_id,
        ingestion_run_id=run.id if run else None,
        status=version.status,
        # The stage reached, which for a finished version is the last one it ran.
        current_stage=run.stage if run else None,
        degraded_capabilities=version.degraded_capabilities,
        error_summary=version.error_summary,
        created_at=version.created_at,
        updated_at=version.updated_at,
    )


@app.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    store: ArtifactStore = Depends(get_artifact_store),
) -> Response:
    """Delete the document and everything derived from it (§25).

    One cascading transaction rather than a tombstone state machine: in V1 the
    derived index lives in the same PostgreSQL as the canonical data, so the
    commit removes both atomically and there is no window for a stale index
    entry to survive. Artifacts are swept afterwards, best effort — an orphaned
    blob is harmless, a missing one that a live version still points at is not.
    """
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no document {document_id}")

    versions = list(
        db.scalars(
            select(DocumentVersion).where(DocumentVersion.document_id == document_id)
        )
    )
    keys = {version.source_artifact_key for version in versions} | set(
        db.scalars(
            select(IngestionRun.normalized_artifact_key).where(
                IngestionRun.document_version_id.in_([v.id for v in versions]),
                IngestionRun.normalized_artifact_key.is_not(None),
            )
        )
    )

    db.delete(document)
    db.commit()

    for key in keys - _still_referenced(db, keys):
        store.delete(key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _still_referenced(db: Session, keys: set[str]) -> set[str]:
    """Keys another document still needs. Artifacts are content-addressed, so
    the same bytes uploaded to two corpora share one blob."""
    return set(
        db.scalars(
            select(DocumentVersion.source_artifact_key).where(
                DocumentVersion.source_artifact_key.in_(keys)
            )
        )
    ) | set(
        db.scalars(
            select(IngestionRun.normalized_artifact_key).where(
                IngestionRun.normalized_artifact_key.in_(keys)
            )
        )
    )


@app.put(
    "/documents/{document_id}",
    response_model=VersionOut,
    status_code=status.HTTP_201_CREATED,
)
def update_document(
    document_id: uuid.UUID,
    response: Response,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    store: ArtifactStore = Depends(get_artifact_store),
) -> VersionOut:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no document {document_id}")
    data, media_type = _read_upload(file)
    source_hash = hashlib.sha256(data).hexdigest()

    duplicate = _existing_version(db, document.corpus_id, source_hash)
    if duplicate is not None:
        if duplicate.document_id != document_id:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "those bytes are already a different document in this corpus",
            )
        # Identical bytes are not a new version; no fake version is created.
        response.status_code = status.HTTP_200_OK
        return _out(duplicate)

    in_flight = db.scalars(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.status.in_(IN_FLIGHT),
        )
    ).first()
    if in_flight is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"version {in_flight.id} is still processing; retry when it settles",
        )

    version = _add_version(db, document, data, media_type, file.filename or "untitled", store)
    try:
        db.commit()
    except IntegrityError:
        # Lost a race against another update or upload; the caller retries.
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "a concurrent change won; retry"
        ) from None
    return _out(version)
