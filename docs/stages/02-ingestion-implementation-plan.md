# Stage 2 Implementation Plan — Data Ingestion Pipeline

## Status

**Approved for implementation.** This is the step-by-step execution guide for the accepted Stage 2 architecture (`docs/stages/02-ingestion.md`, ADR-002/003/004).

`02-ingestion.md` is the *architecture*. This document is the *implementation slice*: what gets built now, what is deliberately deferred, and in what order.

## Scope of this slice

A working vertical path: upload a TXT or Markdown document → parse → normalize → chunk → extract temporal mentions → generate dense + lexical representations → validate → publish as searchable, with durable ingestion state and crash recovery.

The lifecycle *identity columns* (`document_id`, `document_version_id`, `processing_generation_id`, `search_representation_generation_id`) are present from the first migration, because retrofitting identity into already-published rows is the one thing that is genuinely expensive later.

The generation *migration machinery* is not built, because it has no caller until a chunker or embedding model actually changes.

## Settled decisions

### Stack

| Concern | Choice |
| --- | --- |
| Language / runtime | Python 3.12 |
| Dependency management | `uv` |
| API | FastAPI |
| ORM / migrations | SQLAlchemy + Alembic |
| Driver | psycopg |
| Database | PostgreSQL with pgvector (`pgvector/pgvector:pg17` via docker compose) |
| Package layout | `src/astrag/{api,ingest,storage,models}`, `alembic/` at repo root |

Rationale for Python: the PDF/DOCX parsing and temporal-extraction ecosystems are the two hardest parts of Stage 2, and they are strongest here.

### Formats

TXT and Markdown first. PDF next, DOCX after. The parser abstraction from `02-ingestion.md` §6 is built as specified in the first slice; only the registry grows when the later formats land.

PDF is deliberately not first: page provenance, header/footer stripping, and scanned-only detection would dominate the slice and delay proving the pipeline end to end.

### Embeddings

- Model: OpenAI `text-embedding-3-small`, 1536 dimensions, `cl100k_base` tokenizer.
- A deterministic hash-based fake embedder sits behind the same interface, selected by env var, so tests and the Stage 7 evaluation harness run offline, free, and reproducibly.
- Storage: one `chunk_representations` table with a `vector(1536)` column and an HNSW index.

**Known constraint:** pgvector columns are fixed-dimension, but ADR-002/004 promise SearchRepresentationGeneration migration to a potentially different embedding model. A future SRG with a different dimension requires an Alembic migration adding a column. This is accepted rather than engineered around — a dynamic per-SRG-table scheme would be maintained forever for a migration that may never happen.

### Execution model

A database-backed job table plus a separate worker process (`python -m astrag.worker`).

In-process asyncio tasks were rejected: they die with the API process, which makes the crash-recovery requirement untestable. Synchronous ingestion was rejected per the architecture — recovery needs durable job state regardless.

### Chunking

| Parameter | Value |
| --- | --- |
| Target size | 512 tokens |
| Hard maximum | 800 tokens |
| Overlap | 64 tokens, **only** on forced splits of an oversized structural unit |
| Tokenizer | `tiktoken`, `cl100k_base` |

All four live in one config object so Stage 7 can sweep them. These are tunable configuration validated by evaluation, not architectural constants.

### Ingestion state

`02-ingestion.md` §19 lists fourteen coarse states and then says they are architectural stages rather than a demand that each become an externally visible enum. Taken at its word:

- `document_versions.status` — enum of `PENDING`, `RUNNING`, `READY`, `READY_DEGRADED`, `FAILED`.
- `ingestion_runs.stage` — plain TEXT holding the current pipeline step name.
- Checkpoint granularity — one row update per completed stage. Resume re-runs the failed stage from its start, never sub-stage. Safe because deterministic chunk identity makes every stage idempotent.
- `DELETING` / `DELETED` are not implemented (see Deletion below).

### Capability status

A JSONB column on `document_versions` holding only the degraded capabilities — `{"temporal": "degraded"}`, empty object meaning fully ready.

`SEMANTIC` and `LEXICAL` can never be degraded by the architecture's own rule, so dedicated columns for them would be permanently constant. JSONB also lets the capability model extend without a migration, which §20 anticipates.

### Temporal extraction

Deterministic recognition only in this slice: regex plus `dateparser` producing real `TemporalMention` rows with precision, certainty, temporal origin, ranges, and BCE/CE. The controlled semantic-interpretation layer from §12 slots in behind the same extractor interface once there is a labelled set to score it against.

Rejected alternatives:

- Skipping temporal extraction entirely and publishing everything `READY_DEGRADED` — the slice would not exercise the one thing that distinguishes ASTRAG, and the degradation path would become the only tested path.
- Full hybrid now — that puts an LLM call inside the ingestion pipeline before any golden-file test exists to judge its output.

### Lexical representation

A Postgres `GENERATED ALWAYS AS (to_tsvector('english', contextualized_text)) STORED` column on `chunk_representations`, with a GIN index.

A generated column cannot drift from its source text; a trigger-maintained one can, and publication validation would then have to check the correspondence by hand. The bounded exact-token/phrase fallback the architecture mentions belongs to Stage 3.

### Normalized document and lineage

- The normalized document is persisted as a JSON artifact in the ArtifactStore.
- Chunk source spans (`source_block_ids` plus per-block normalized offsets) are a JSONB column on `chunks`.

Blocks are only ever read as a whole document during re-chunking and are never queried individually, so a blocks table would buy nothing and cost a join plus a million rows. Keeping the artifact makes "a temporal-extractor change reuses compatible normalized documents" free later, for the price of one `json.dumps`.

### Generation identities

`processing_generations` and `search_representation_generations` are real tables — `id`, `config` JSONB, `created_at` — plus a single-row active-SRG pointer. Rows are inserted by migrations; there is no generation-creation API.

The foreign key is what turns "no chunk ever references an unknown generation" into a database guarantee instead of a code convention, and publication validation is largely that guarantee.

### Invariants enforced in DDL

Three architecture rules are enforceable in schema rather than application code:

1. Exact-byte idempotency — `UNIQUE (corpus_id, source_hash)` on `document_versions`.
2. One replacement processing at a time — partial unique index on `document_versions (document_id) WHERE status IN ('PENDING','RUNNING')`.
3. Generation validity — foreign keys to the two generation tables.

This requires denormalizing `corpus_id` onto `document_versions`, which also serves the corpus-boundary filter Stage 3 applies on every query.

This is where complexity is deliberately spent: an idempotency race that creates a duplicate logical document is silent corrupted evidence, and a unique index costs one line.

### Deletion

Cascade delete in a single transaction (`ON DELETE CASCADE`), followed by best-effort artifact cleanup after commit. Orphaned blobs are harmless and GC is already deferred by §107.

No `DELETING` state and no tombstone table in this slice. The multi-step tombstone in §25 exists to survive partial failure across *separate* systems; in V1 the derived index lives in the same PostgreSQL as the canonical data, so one transaction removes both atomically. The state machine gets added the day the search index moves out of PostgreSQL.

Stage 3's final eligibility check stays regardless — it costs nothing and is Stage 3's contract.

### API surface

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/corpora` | create corpus |
| GET | `/corpora` | list corpora |
| POST | `/corpora/{id}/documents` | Create Document |
| PUT | `/documents/{id}` | Update Document |
| GET | `/documents/{id}` | ingestion status contract |
| DELETE | `/documents/{id}` | delete document |

No search endpoint — that is Stage 3. No auth — single tenant, and the architecture does not ask for it.

### ArtifactStore

A local-filesystem implementation (`put` / `get` / `delete`, key `sha256[:2]/sha256`, root from env) behind one abstract base so object storage slots in at Stage 10.

### Tests

The docker-compose database with a per-test transaction rollback, plus golden-file tests for parser, chunker, and temporal-extractor output.

SQLite was rejected outright: pgvector, JSONB, and FTS do not exist there, so the parts most likely to break would be uncovered. Testcontainers is the same thing plus container startup on every run — adopt it only when CI needs it.

## Implementation ladder

Each rung is one commit, committed as it goes green. A rung exceeding ~250 changed lines is split.

| # | Commit | Notes |
| --- | --- | --- |
| 1 | `chore(repo): scaffold uv project, docker-compose pgvector, settings module` | |
| 2 | `feat(db): lifecycle schema` | corpora, documents, document_versions, generation tables, the three DDL invariants |
| 3 | `feat(storage): local-filesystem ArtifactStore behind abstract base` | |
| 4 | `feat(api): corpus endpoints and document create/update upload path` | source hashing, idempotency, cheap synchronous validation |
| 5 | `feat(ingest): ingestion_runs, job table, worker loop with per-stage checkpointing` | |
| 6 | `feat(parse): parser registry, TXT and Markdown parsers, NormalizedDocument artifact` | golden-file tests in this rung |
| 7 | `feat(db,chunk): chunks table and structure-aware token-bounded chunker with source spans` | golden-file tests in this rung |
| 8 | `feat(temporal): deterministic TemporalMention extraction and chunk association` | golden-file tests in this rung |
| 9 | `feat(embed): embedding client, chunk_representations with vector(1536) and generated tsvector` | OpenAI + deterministic fake |
| 10 | `feat(publish): publication validator and atomic active-version activation` | |
| 11 | `feat(api): status contract and cascade delete` | |
| 12 | `test(ingest): end-to-end ingestion and worker crash-resume` | |

Golden-file tests live inside rungs 6, 7, and 8 rather than in a separate rung — the parser, chunker, and temporal extractor are exactly the logic that must not go green without them.

## Deferred out of this slice

| Deferred | Add when |
| --- | --- |
| PDF parser | after the pipeline is proven on TXT/MD (rung 13) |
| DOCX parser | after PDF (rung 14) |
| ProcessingGeneration cutover and reprocessing orchestration | a chunker or normalizer actually changes |
| SearchRepresentationGeneration re-embedding migration | the embedding model actually changes |
| LLM temporal interpretation | a labelled temporal set exists to score it against |
| Tombstone deletion state machine | the search index moves out of PostgreSQL |
| GC / retention policy | storage pressure is measured |
| Message broker / production queue topology | Stage 10 |
| Learned sparse embeddings | Stage 3 evaluation shows FTS is insufficient |

## Architecture compliance

Nothing in this slice weakens a Stage 1 or Stage 2 global invariant:

- corpus boundaries are enforced in DDL and denormalized onto every searchable row,
- provenance and lineage identifiers are canonical from the first migration,
- temporal mentions carry precision, certainty, and explicit origin,
- publication validation gates searchability, and no partially indexed version is ever query-visible,
- canonical evidence is authoritative and search projections are rebuildable.

The three deviations from the literal text of `02-ingestion.md` — the collapsed state enum, the absent tombstone state machine, and the fixed-width vector column — are recorded above with their reasoning and their re-add triggers.
