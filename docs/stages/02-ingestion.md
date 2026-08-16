# Stage 2: Data Ingestion Pipeline

## Status

**Implementation Ready.**

Orchestrator review is complete. ADR-002, ADR-003, and ADR-004 are accepted, and the corresponding project-wide invariants are recorded in `docs/architecture/architecture.md`.

## Objective

Define how supported user documents become reliable, searchable, provenance-preserving, temporally useful evidence for later ASTRAG stages.

Stage 2 owns the ingestion architecture from upload through validated publication of searchable representations. It also owns corpus/document lifecycle, document versions, processing generations, search-representation generations, ingestion state, retry/recovery behavior, deletion propagation, and the persisted Stage 3 retrieval contract.

The design preserves Stage 1 invariants:

- corpora are first-class evidence boundaries,
- provenance survives ingestion and later evidence use,
- temporal information and uncertainty are first-class,
- duplicate content must not appear as independent corroboration merely because it was ingested through multiple paths,
- V1 supports text-extractable PDF, TXT, Markdown, and DOCX,
- OCR and multimodal ingestion remain outside V1,
- V1 assumes one tenant, low concurrency, hundreds to thousands of documents, and a design envelope of roughly one million chunks.

## Scope

Stage 2 defines:

- corpus ownership of documents,
- explicit document create/update semantics,
- logical document identity and immutable source versions,
- upload validation and exact-byte hashing,
- parser abstraction and canonical normalization,
- structure-aware chunking,
- durable chunk/provenance lineage,
- temporal metadata extraction and uncertainty representation,
- dense and lexical search representation generation,
- search-representation versioning,
- canonical storage and derived search projections,
- asynchronous ingestion execution,
- ingestion state and capability degradation,
- retries, idempotency, crash recovery, and stale-run handling,
- atomic publication and active-version cutover,
- deletion and corpus deletion semantics,
- incremental reprocessing and re-indexing,
- exact-content duplicate signals,
- ingestion observability/evaluation hooks,
- the persisted contract Stage 3 consumes.

## Non-Goals

Stage 2 does not define:

- query rewriting,
- query-time dense/lexical fusion,
- query-time temporal interpretation,
- Top-K selection,
- reranking,
- query-time source balancing,
- final evidence deduplication/corroboration semantics,
- context token budgeting,
- agent orchestration,
- final citation rendering,
- OCR,
- scanned/image-only PDF understanding,
- multimodal document understanding,
- sophisticated historical-calendar conversion,
- production queue/broker topology,
- production-scale multi-tenant concurrency.

These belong primarily to later stages.

## Requirements

### Supported formats

V1 supports text-extractable:

- PDF,
- DOCX,
- Markdown,
- TXT.

Unsupported, encrypted/password-protected, scanned/image-only, empty, corrupt, or otherwise non-extractable inputs fail non-retryably as appropriate.

### Corpus ownership

Each V1 logical document belongs to exactly one corpus.

`documents.corpus_id` is required. A document may be moved between corpora without creating a new document version or recomputing document content/search representations; affected search metadata is updated incrementally.

Deleting a corpus semantically deletes all owned logical documents, versions, chunks, representations, and artifacts through the normal durable deletion workflow.

### Search visibility

Only the active `READY` or explicitly permitted `READY_DEGRADED` version of a logical document, under its active ProcessingGeneration and the globally active SearchRepresentationGeneration, is query-visible.

Partially processed or partially indexed versions/generations are never searchable.

## Assumptions

- One embedding model is active in V1, but the architecture supports future replacement through SearchRepresentationGeneration.
- One preferred ProcessingGeneration exists for new processing, but active documents may have been processed by different ProcessingGenerations.
- One SearchRepresentationGeneration is active globally for query-time search in V1.
- Dense and lexical search representations are mandatory for searchable readiness.
- Temporal/provenance-location enrichment may be explicitly degraded while semantic/lexical search remains available.
- Garbage collection/retention optimization is deferred; historical versions and generation artifacts are logically retained for now.

## Key Design Decisions

### 1. Logical document identity and immutable versions

ASTRAG distinguishes:

```text
LogicalDocument
    ↓ 1:N
DocumentVersion
```

`document_id` is a stable logical source identity.

A source-content replacement creates a new immutable `DocumentVersion`; processing/model changes do not.

Document creation and document update are explicit operations. The system does not infer update identity from filename or similarity.

### 2. Exact-byte source hashing

Each DocumentVersion stores:

```text
source_hash = SHA-256(exact uploaded bytes)
```

The source hash is an idempotency/duplicate-content signal, not logical document identity.

The same bytes uploaded again to the same corpus through Create Document return the existing logical document/version idempotently. An explicit update using bytes identical to the current version returns the existing version and does not create a fake version.

The same source bytes may exist as distinct logical documents in different corpora; the shared hash preserves exact-content equivalence for downstream duplicate analysis.

### 3. Version versus processing/search generations

```text
source content changes
    → new DocumentVersion

parser/normalizer/chunker processing changes
    → new ProcessingGeneration

embedding/lexical search configuration changes
    → new SearchRepresentationGeneration
```

ProcessingGeneration and SearchRepresentationGeneration are global immutable configuration identities referenced by generated artifacts.

A global preferred ProcessingGeneration controls new processing. Changing it does not automatically reprocess all existing documents.

Active documents may use chunks produced by different ProcessingGenerations. For a given active DocumentVersion, publication selects exactly one active ProcessingGeneration chunk set.

Active retrieval uses one globally active SearchRepresentationGeneration in V1; incompatible embedding/search generations are not mixed.

An `IngestionRun` identifies one processing attempt and is not a document, processing, or search-representation version.

### 4. Safe replacement cutover

Only one replacement version may be processing at a time for a logical document in V1.

If:

```text
v1 = READY / active
v2 = PROCESSING
```

Stage 3 continues to retrieve v1.

If v2 fails, v1 remains active.

If v2 reaches publishable `READY` or permitted `READY_DEGRADED`, publication validates the full new searchable set and atomically changes the active version and active ProcessingGeneration for that version.

Reprocessing the same DocumentVersion under a new ProcessingGeneration follows the same private-build, validate, and atomic-cutover rule without creating a fake source version.

### 5. Canonical normalized document representation

Each format-specific parser produces one format-independent ordered normalized representation.

Minimal V1 block types:

- `HEADING`
- `PARAGRAPH`
- `LIST_ITEM`
- `TABLE_TEXT`
- `UNKNOWN_TEXT`

The representation preserves source order and meaningful structure without preserving presentation styling.

PDF preserves page provenance when available.

DOCX preserves semantic headings, paragraphs, lists, and table text while ignoring fonts/colors/layout styling.

Markdown headings create section hierarchy.

TXT preserves paragraph/order structure with minimal heading inference.

Repeated PDF headers/footers may be removed by deterministic best-effort cleanup while keeping processing lineage inspectable.

The normalized document is persisted as an immutable artifact so later re-chunking can avoid reparsing when compatible.

### 6. Parser abstraction

Stage 2 defines a format parser contract conceptually equivalent to:

```text
DocumentParser
    supports(format)
    parse(source) -> NormalizedDocument
```

Format-specific libraries may differ behind this contract. Parser library selection normally does not require an ADR unless it changes architecture, deployment/licensing constraints, or the canonical representation contract.

### 7. Parsing success requires validation

A parser returning without throwing is not sufficient.

Parsing/normalization validates, at minimum, that extracted evidence is usable and structurally consistent. Examples include:

- non-empty useful text,
- valid block order,
- valid page/block metadata when present,
- no unsupported encrypted/scanned-only input masquerading as successful extraction.

Parser quality warnings may record empty pages, low extracted-character counts, unusual unknown-block ratios, pages without text, or table extraction concerns without necessarily failing ingestion.

### 8. Structure-aware token-bounded chunking

V1 uses a structure-aware, token-bounded hybrid strategy.

The chunker:

- starts from normalized structural blocks,
- prefers not to cross meaningful section boundaries,
- combines structural units within configurable size targets,
- splits paragraphs only when oversized,
- uses limited overlap only when forced to split a structural unit,
- treats tables as structural units and splits oversized tables by rows while preserving useful header context,
- treats exact chunk-size/overlap values as tunable configuration validated by evaluation rather than permanent architectural constants.

### 9. Authoritative source text versus contextualized retrieval text

Every chunk preserves authoritative `source_text` separately from retrieval-oriented contextualized text.

Contextualized text may conservatively include document title and section hierarchy before the source text for embedding/lexical representation generation.

Derived temporal metadata is not injected into dense embedding text in V1.

Later generation/citation logic must use source evidence/provenance rather than pretending retrieval-added headings are original source prose.

### 10. Chunk identity and lineage

Chunk identity is deterministic within a processing generation and conceptually derives from:

```text
document_version_id
+ processing_generation_id
+ chunk_ordinal
```

Chunk text hash is stored separately as `chunk_content_hash`; identical text in different locations remains distinct chunk occurrences.

A new DocumentVersion receives a new chunk identity namespace. V1 does not attempt cross-version chunk-ID matching.

Chunks retain:

- `chunk_id`
- `corpus_id`
- `document_id`
- `document_version_id`
- `processing_generation_id`
- `section_path`
- `source_block_ids` / source spans
- `chunk_ordinal`
- page range when available
- normalized source offsets/spans
- `chunk_content_hash`

Explicit previous/next chunk IDs are unnecessary because ordinal/source structure preserves order.

### 11. Provenance model

Every searchable chunk directly exposes the core evidence-boundary and lineage identifiers:

- chunk,
- corpus,
- logical document,
- document version,
- processing generation.

Authoritative source display metadata lives on the document/version and may be denormalized into search records for retrieval efficiency.

Source metadata distinguishes original filename from logical display title.

Page provenance uses nullable `page_start`/`page_end` because a chunk may span pages and non-PDF formats may not have meaningful pages.

Section path is durable provenance.

Chunk source lineage uses block IDs plus per-block normalized offsets. Exact raw PDF/DOCX byte offsets are not required in V1.

Core source/document/corpus/chunk lineage is mandatory. Missing optional location metadata such as page information may produce provenance-location degradation without discarding otherwise usable evidence.

### 12. Temporal metadata model

Stage 2 extracts zero or more `TemporalMention` records against normalized source structure, then associates those mentions with chunks by source spans.

A chunk may contain multiple temporal mentions.

Temporal origin is explicit so source/document metadata dates cannot be confused with dates mentioned in document content. V1 distinguishes at least:

- `SOURCE_METADATA`
- `CONTENT_MENTION`

This origin dimension is separate from semantic role. A conservative semantic role may be assigned when reliably determinable; `UNKNOWN` is valid.

Each mention preserves original wording and normalized values only where safe.

V1 precision categories:

- `DAY`
- `MONTH`
- `YEAR`
- `SEASON`
- `DECADE`
- `CENTURY`
- `RANGE`
- `UNKNOWN`

V1 certainty categories:

- `EXACT`
- `APPROXIMATE`
- `UNCERTAIN`

Ranges are represented as one mention with start/end bounds.

BCE/CE remains machine-comparable while preserving source era/writing.

Relative expressions are preserved and resolved only when deterministic from local source context. Unresolved relative expressions remain evidence rather than being discarded or assigned invented dates.

V1 does not perform sophisticated Julian/Gregorian or other historical calendar conversion.

Temporal extraction uses a hybrid architecture: deterministic recognition where reliable plus controlled semantic interpretation for harder expressions/roles.

### 13. Temporal degradation

Successful temporal extraction with zero mentions is not a failure.

A temporal-extraction subsystem failure may yield `READY_DEGRADED` if all mandatory semantic/lexical/provenance requirements are otherwise satisfied.

Stage 2 exposes capability state; Stage 3 owns query-time handling of degradation.

### 14. Search representations

Every searchable chunk has access to:

- authoritative source text,
- contextualized retrieval text,
- dense embedding,
- lexical/full-text representation,
- structured metadata,
- temporal metadata,
- provenance.

Dense embedding input uses the contextualized text.

Dense and lexical representations are required for `READY`/`READY_DEGRADED` searchability.

A chunk missing a required representation is not partially published.

The exact embedding batch size is implementation tuning; the architecture requires batch-capable generation, per-chunk failure tracking, idempotent retry, and generation identity.

### 15. Lexical representation rather than learned sparse vector in V1

Stage 2 materializes lexical/full-text-searchable representation suitable for Stage 3 lexical retrieval.

V1 does not require a learned sparse-embedding model.

Stage 3 owns query-time lexical ranking, dense/lexical combination, weighting/fusion, metadata/temporal filtering, Top-K, and reranking.

### 16. Canonical evidence versus search projections

Canonical chunks and evidence metadata are authoritative and persisted independently of search indexes.

Search indexes are derived/rebuildable state.

Dense embedding vectors and lexical representation artifacts are persisted by SearchRepresentationGeneration so search indexes can be rebuilt without necessarily rerunning parsing/chunking or re-calling embedding providers.

### 17. V1 persistence architecture

Accepted by ADR-004, Stage 2 uses:

- PostgreSQL as authoritative relational storage for corpus/document lifecycle, chunks, provenance, temporal metadata, ingestion state, and search-representation metadata,
- integrated dense-vector capability such as pgvector,
- PostgreSQL full-text capabilities for V1 lexical representation/search indexing,
- a small ArtifactStore abstraction for original sources and normalized-document artifacts.

The ArtifactStore may be backed by local filesystem/object storage depending on deployment; ingestion logic depends on the abstraction.

This storage boundary is part of the accepted global V1 architecture and remains benchmark/revisit-driven rather than permanent infrastructure dogma.

### 18. Async sequential ingestion

Upload processing is asynchronous at the architectural level.

The synchronous request performs cheap validation such as:

- corpus existence,
- supported input type,
- non-empty input,
- configured size constraints,
- source-hash/idempotency lookup,
- creation/persistence of source/version/run state.

It then returns document/version/ingestion-run identifiers.

A small `IngestionExecutor` runs a sequential checkpointed pipeline. V1 does not require a message broker. Production queue topology belongs to later stages.

### 19. Ingestion runs and lifecycle state

Each processing attempt creates an `IngestionRun`. DocumentVersion exposes current lifecycle/searchability state while runs preserve attempt history.

Coarse conceptual states include:

```text
UPLOADED
VALIDATING
PARSING
NORMALIZING
CHUNKING
ENRICHING
REPRESENTING
INDEXING
PUBLISHING
READY
READY_DEGRADED
FAILED
DELETING
DELETED
```

These are architectural stages, not a demand that every internal function become an externally visible enum.

### 20. Capability state

`READY_DEGRADED` is accompanied by capability-level state rather than a single temporal-failure boolean.

Conceptually:

```text
SEMANTIC = READY
LEXICAL = READY
TEMPORAL = READY | DEGRADED
PROVENANCE_LOCATION = READY | DEGRADED
```

The capability model may extend later.

Mandatory source/document/corpus/chunk lineage, dense representation, and lexical representation cannot be degraded into searchability.

### 21. Idempotency and retries

Pipeline stages must be safe to retry using stable version/generation/chunk identities.

A retry creates a new IngestionRun but reuses compatible successful intermediate artifacts.

Failures are structured with, at minimum:

- stage/component,
- error code,
- message/summary,
- retryable flag,
- timestamp,
- relevant component/generation identity.

Explicitly retryable transient failures receive bounded automatic retry/backoff. Exact retry counts and delays are implementation configuration.

### 22. Crash recovery and stale runs

Ingestion correctness does not depend on in-memory state.

Persisted checkpoints allow restart/resume after worker/process failure.

Runs track enough timing/heartbeat information to detect stale processing and recover or fail the attempt.

Only one active processing attempt for a particular document-version/generation combination may execute at once.

### 23. Publication validation

Before activation, publication validates that:

- every chunk has valid document/version/generation lineage,
- every chunk references valid normalized source spans,
- corpus association is consistent,
- all required dense representations exist,
- all required lexical representations exist,
- all active search records belong to the expected SearchRepresentationGeneration,
- temporal annotations are structurally valid when extraction succeeded,
- degradations are explicitly recorded when permitted,
- expected searchable chunk identity/count matches derived index visibility.

Only after validation is the specific DocumentVersion + ProcessingGeneration searchable set exposed to Stage 3 under the globally active SearchRepresentationGeneration.

### 24. Incremental processing and re-indexing

New documents and new document versions process incrementally; unrelated documents are not rebuilt.

Parser changes reprocess only affected formats/documents.

Normalizer changes require new processing from normalization downstream.

Chunking changes create a new ProcessingGeneration/chunk set and use safe cutover rather than mutating existing chunks.

Temporal-extractor changes may reuse compatible normalized documents/chunks.

Embedding or lexical search configuration changes create a new SearchRepresentationGeneration and reuse canonical chunks.

A corrupted/changed search index may be rebuilt from persisted representations without re-parsing/re-chunking.

Full search-index rebuild is reserved for search-generation/schema/index-wide changes or corruption, not ordinary single-document lifecycle operations.

Artifact reuse is permitted only when generation compatibility proves upstream inputs remain unchanged/valid.

### 25. Deletion

Deletion first removes retrieval eligibility, then propagates physical cleanup.

A durable `DELETING` state/tombstone survives partial cleanup failure.

Conceptually:

```text
DELETE requested
    ↓
retrieval eligibility disabled
    ↓
remove dense/lexical index records
    ↓
remove canonical/representation data as required
    ↓
clean source/normalized artifacts according to retention policy
    ↓
DELETED
```

Stage 3 must apply a final eligibility check so stale index entries cannot become evidence if derived-index deletion fails or lags.

Historical versions are retained as lineage until deleted by explicit document/corpus deletion or later GC policy, but only the active version and active ProcessingGeneration are searchable.

### 26. Duplicate-content responsibility

Exact duplicate handling is separated from semantic evidence deduplication.

Stage 2:

- uses exact source hash for byte-identical source equivalence/idempotency,
- stores chunk content hashes,
- preserves repeated chunks and source locations,
- permits same exact source bytes as separate logical documents in different corpora,
- does not perform semantic near-duplicate detection in V1.

Stage 5 owns final evidence deduplication/corroboration semantics.

## Proposed Architecture

```text
User Create / Update
        ↓
Cheap Upload Validation
        ↓
Persist Original Source Artifact
        ↓
LogicalDocument / DocumentVersion
        ↓
IngestionRun
        ↓
┌─────────────────────────────────┐
│ Sequential Checkpointed Worker │
│                                 │
│ Validate                        │
│ Parse                           │
│ Normalize                       │
│ Chunk                           │
│ Metadata/Temporal Enrichment    │
│ Dense Representation            │
│ Lexical Representation          │
│ Index                           │
│ Publication Validation          │
└─────────────────────────────────┘
        ↓
Atomic Activate
        ↓
READY / READY_DEGRADED
        ↓
Stage 3 Searchable Chunk Contract
```

Canonical lifecycle:

```text
Corpus
  ↓ 1:N
LogicalDocument
  ↓ 1:N
DocumentVersion
  ↓ processed using
ProcessingGeneration
  ↓
Canonical Chunks
  ↓ represented using
SearchRepresentationGeneration
  ↓
Derived Search Indexes
```

## Components

### Corpus Repository

Maintains corpus lifecycle and one-corpus-per-document ownership.

### Document Lifecycle Service

Handles explicit Create Document, Update Document, active-version/processing-generation publication state, source hashing/idempotency, and deletion transitions.

### ArtifactStore

Stores/retrieves/deletes immutable original-source and normalized-document artifacts.

### Parser Registry / Format Parsers

Selects format-specific parsers and emits canonical normalized documents.

### Normalizer

Produces deterministic ordered structural blocks and source-location metadata.

### Chunker

Produces structure-aware token-bounded chunks with deterministic identity and source spans.

### Metadata / Temporal Extractor

Produces structured temporal mentions, temporal origin, and enrichment status while preserving source wording/uncertainty.

### Representation Generator

Generates mandatory dense and lexical search representations using the active SearchRepresentationGeneration.

### Search Index Publisher

Builds/updates derived search projections and performs generation-aware activation.

### IngestionExecutor

Executes the sequential pipeline asynchronously with durable checkpoints and idempotent recovery.

### Publication Validator

Verifies lineage, representation completeness, temporal/provenance consistency, generation consistency, and expected index visibility before activation.

## Data Flow

### Create Document

```text
Create(corpus, file)
    ↓
source hash lookup
    ↓
existing exact duplicate in same corpus? ─ yes → return existing document/version
    │ no
    ↓
new LogicalDocument + DocumentVersion
    ↓
async ingestion
```

### Update Document

```text
Update(document_id, replacement_file)
    ↓
replacement already processing? ─ yes → reject/defer V1 update
    ↓
exact same bytes as current version? ─ yes → return current version
    ↓
new DocumentVersion
    ↓
process privately
    ↓
READY / READY_DEGRADED
    ↓
atomic active-version/processing-generation cutover
```

### Re-embedding / search-generation migration

```text
existing canonical chunks
    ↓
new SearchRepresentationGeneration
    ↓
generate dense + lexical representation
    ↓
build/validate derived indexes
    ↓
atomic global active-SRG cutover
```

### Chunker/process migration

```text
existing DocumentVersion / reusable normalized artifact
    ↓
new ProcessingGeneration
    ↓
new canonical chunk generation
    ↓
represent under active SRG
    ↓
validate
    ↓
activate new chunk set for that document version
```

## Interfaces / Contracts

### Stage 2 → Stage 3 searchable chunk contract

Stage 2 exposes only eligible searchable records. Conceptually:

```text
SearchableChunk {
    chunk_id
    corpus_id
    document_id
    document_version_id
    processing_generation_id
    search_representation_generation_id

    source_text
    contextualized_text

    dense_embedding
    lexical_fields

    temporal_mentions[]

    section_path
    page_start
    page_end
    source_spans[]
    chunk_ordinal
    chunk_content_hash

    source_display_metadata

    capability_status
    active/searchable eligibility
}
```

Stage 3 must enforce:

- selected-corpus filtering,
- active logical-document/version eligibility,
- active ProcessingGeneration eligibility for the active DocumentVersion,
- active SearchRepresentationGeneration eligibility,
- non-deleted state.

Stage 3 owns query-time retrieval/ranking behavior.

### Ingestion status contract

Callers must be able to observe conceptually:

```text
document_id
document_version_id
ingestion_run_id
status
current_stage
capability_status / degraded capabilities
error summary
created_at
updated_at
```

Exact API schemas are implementation details.

## Failure Cases

### Unsupported input

Unsupported/encrypted/scanned-only/empty/corrupt input fails non-retryably as appropriate.

### Parser/normalization failure

Version remains non-searchable. Structured failure is recorded. Compatible prior active version remains active.

### Temporal extractor failure

If mandatory semantic/lexical/provenance requirements succeed, version may become `READY_DEGRADED` with temporal capability degraded.

### Missing provenance location

Usable evidence may become `READY_DEGRADED` with provenance-location degradation when page/section location cannot be recovered, while core corpus/document/chunk identity remains mandatory.

### Dense or lexical representation failure

Document version is not publishable. Failed chunks may be retried idempotently; partial versions are never exposed.

### Indexing failure

Canonical evidence/representations remain persisted. Retry resumes indexing rather than recreating valid upstream artifacts.

### Worker crash

Persisted state/checkpoints allow recovery. Stale runs may be detected and resumed/failed according to retry policy.

### Replacement failure

Previous active version remains searchable.

### Deletion cleanup failure

Document remains retrieval-ineligible in `DELETING`; cleanup resumes later. Stage 3 eligibility checks protect against stale index entries.

## Evaluation Criteria

Stage 2 evaluation must measure or validate at least:

### Parsing / normalization

- success rate by supported format,
- valid extraction versus empty/garbage extraction,
- structural preservation,
- PDF page provenance where available,
- parser warning rates.

### Chunking

- chunk count/distribution,
- chunk-size distribution,
- section-boundary preservation,
- oversized-unit split correctness,
- table split correctness,
- chunk-to-source lineage validity.

### Provenance

- corpus/document/version correctness,
- page/section correctness where available,
- source-span validity,
- source display identity correctness,
- degraded-provenance classification correctness.

### Temporal extraction

- mention precision/recall on curated temporal data,
- normalized-date/range correctness,
- uncertainty preservation,
- BCE/CE correctness,
- relative/unresolved-expression handling,
- temporal-origin classification correctness,
- role classification quality,
- successful-zero-mention versus subsystem-failure distinction.

### Search representation

- dense/lexical generation completion,
- per-chunk representation completeness,
- generation identity correctness,
- failed-representation retry correctness.

### Lifecycle / recovery

- duplicate-upload idempotency,
- update/version cutover correctness,
- processing-generation cutover correctness,
- previous-version preservation on failed replacement,
- crash recovery,
- stale-run recovery,
- corpus move correctness,
- document/corpus deletion correctness,
- reprocessing/re-indexing correctness,
- no partial query visibility.

### Observability

Each IngestionRun should expose stage timings and useful counts, including where applicable:

- source size,
- normalized block count,
- chunk count,
- temporal mention count,
- representation success/failure counts,
- indexed chunk count,
- stage durations,
- structured warnings/errors.

Logs should default to identifiers, counts, hashes, timings, status, and error metadata rather than full chunk/source content. Content inspection should be an explicit debugging path.

## Scalability

V1 targets:

- hundreds to thousands of documents,
- roughly up to one million chunks,
- one primary user / low concurrency.

The Stage 2 design favors operational simplicity at this scale while retaining explicit generation boundaries and rebuildable projections so search/storage systems can be specialized later if benchmarks require it.

PostgreSQL vector/full-text behavior at the upper V1 envelope must be benchmarked before treating the storage architecture as permanently sufficient.

## Latency / Throughput Requirements

Stage 1 does not establish a strict ingestion-latency SLO.

Stage 2 therefore requires:

- asynchronous upload processing so long ingestion does not hold request lifetimes open,
- batch-capable embedding generation,
- incremental single-document updates rather than corpus rebuilds,
- persisted stage timings so implementation/evaluation can establish realistic targets.

Exact throughput, worker concurrency, batch sizes, timeouts, and retry backoff are implementation/evaluation parameters.

## Alternatives Considered

### Every upload is a new logical document

Rejected because stable source identity and corrections/replacements would be lost.

### Content hash as document ID

Rejected because exact content equality is not the same as logical source identity and identical content may validly exist in different corpora.

### Mutable source/chunks/embeddings in place

Rejected because it destroys reproducibility and makes failed migrations unsafe.

### Fixed token chunking

Rejected as the primary V1 strategy because it ignores meaningful source structure important to retrieval and citations.

### Pure structural chunking

Rejected as the sole strategy because structural units can be arbitrarily large.

### Universal fixed overlap

Rejected because it creates unnecessary duplicate evidence; limited overlap is used only for forced splits.

### One date field per chunk

Rejected because it cannot represent multiple dates, ranges, uncertainty, BCE/CE, and relative historical expressions.

### Exact raw-file byte offsets

Rejected for PDF/DOCX V1 because they are brittle and format-specific; normalized block/source-span lineage is sufficient.

### Learned sparse embedding in V1

Deferred. Dense embeddings plus lexical/full-text representation provide complementary retrieval signals with lower complexity.

### Dedicated vector database/search engine in V1

Viable, but the accepted initial design uses integrated PostgreSQL capabilities until benchmark evidence requires additional operational systems.

### Synchronous ingestion

Rejected because parsing/embedding/indexing may outlive reasonable request lifetimes and recovery requires durable job state anyway.

### Mandatory external message broker

Deferred. V1 can use a database-backed/background executor while preserving a small executor abstraction.

### Partial document publication

Rejected because silent missing chunks create unpredictable evidence gaps.

## Dependencies

### Stage 1

Provides evidence-boundary, provenance, temporal, failure, and scale invariants.

### Stage 3

Consumes searchable chunk records and owns query-time corpus enforcement, retrieval, lexical/dense/temporal combination, ranking, Top-K, and reranking.

Stage 3 must apply final eligibility checks against active document/version/processing generation/search generation and deletion state even when an index returns stale records.

### Stage 5

Consumes source hashes, chunk hashes, document lineage, and provenance signals to implement final evidence deduplication/corroboration semantics.

### Stage 6

Consumes authoritative source text and source-location metadata for citation rendering/grounded generation.

### Stage 7

Formalizes ingestion/retrieval temporal and provenance evaluation datasets/thresholds.

### Stage 8

Formalizes traces/metrics around IngestionRun state, stage timings, failure reasons, representation counts, and publication validation.

### Stage 10

May replace the V1 background-executor/storage deployment topology with production queue/object/search infrastructure without changing canonical lifecycle semantics.

## Implementation Plan

Implementation may begin from this accepted Stage 2 architecture.

Suggested implementation order:

1. relational lifecycle schema and migrations,
2. ArtifactStore abstraction,
3. document Create/Update upload path and hashing/idempotency,
4. IngestionRun and executor/checkpoints,
5. parser interface and supported format parsers,
6. normalized-document model and persistence,
7. chunker and provenance spans,
8. temporal metadata extraction and validation,
9. dense embedding contract/generation,
10. lexical representation generation,
11. search projection/index publishing,
12. publication validator and active-version/processing-generation cutover,
13. deletion/tombstone workflow,
14. reprocessing/re-indexing paths,
15. ingestion observability/evaluation tests.

Concrete parser library, embedding model/provider, chunk-size default, retry counts, and batch sizes should be selected during implementation/evaluation as local choices unless they materially change architecture.

## Open Questions

No unresolved Stage 2 question currently blocks implementation.

The following remain implementation/evaluation choices rather than architecture blockers:

- exact PDF/DOCX parser libraries,
- exact V1 embedding model/provider,
- exact chunk target/max/overlap values,
- exact temporal extraction libraries/model,
- exact PostgreSQL vector/full-text index configuration,
- exact asynchronous worker implementation,
- retention/garbage-collection policy,
- ingestion throughput targets after measurement.

## Orchestrator Decisions

### ADR-002 — Ingestion Identity, Versioning, and Publication Model

**Accepted.** Establishes the Stage 2 lifecycle/generation/publication model as an architecture-wide contract, including explicit publication of the active DocumentVersion + ProcessingGeneration searchable set.

### ADR-003 — Temporal Evidence Representation

**Accepted.** Establishes the normalized temporal evidence/uncertainty contract consumed by later stages, including explicit distinction between source/document metadata time and content temporal mentions.

### ADR-004 — V1 Persistence and Search Storage

**Accepted.** Establishes PostgreSQL + integrated vector/full-text capabilities plus ArtifactStore as the V1 storage architecture.

The corresponding global invariants are recorded in `docs/architecture/architecture.md`.

## Acceptance Criteria

Stage 2 is Implementation Ready because:

- this document has been reviewed by the orchestrator,
- ADR-002/003/004 are accepted,
- `docs/architecture/architecture.md` records the accepted Stage 2 global invariants and storage boundaries,
- Stage 3 contract and corpus-boundary implications are accepted,
- no unresolved architecture contradiction remains.

## Impact on Existing Architecture

Stage 2 does not weaken any Stage 1 global evidence invariant.

The following Stage 2 decisions are now accepted global architecture:

1. immutable LogicalDocument/DocumentVersion/ProcessingGeneration/SearchRepresentationGeneration identities,
2. explicit publication of active DocumentVersion + ProcessingGeneration searchable state,
3. canonical-evidence-versus-derived-search publication semantics,
4. structured temporal evidence representation with explicit temporal origin,
5. one-corpus-per-logical-document V1 ownership,
6. capability-aware degraded readiness,
7. PostgreSQL + vector/full-text + ArtifactStore V1 persistence architecture,
8. asynchronous checkpointed ingestion with no partial search visibility.

These decisions are reflected in `docs/architecture/architecture.md` and ADR-002 through ADR-004.

---

## Consolidated Stage 2 Architecture Review

### Alignment with North Star and Stage 1

The Stage 2 design remains aligned with the governing product contract:

- selected corpora remain enforceable evidence boundaries,
- corpus/document/chunk identifiers survive into search records,
- provenance is canonical rather than reconstructed after retrieval,
- temporal information preserves uncertainty rather than inventing precision,
- duplicate exact content retains lineage signals for later deduplication,
- partial/failed ingestion cannot silently expose incomplete evidence,
- OCR/multimodal work remains out of scope,
- the design remains appropriate for V1 single-tenant/low-concurrency scale.

### Cross-stage consistency

Stage 2 stops before query-time retrieval policy. It prepares dense, lexical, metadata, temporal, and provenance representations but does not choose how Stage 3 combines or ranks them.

Stage 2 provides duplicate/equivalence lineage but does not decide final evidence independence; Stage 5 owns that behavior.

Stage 2 preserves authoritative source text/location while Stage 6 owns citation rendering.

Stage 2 exposes degraded capabilities while Stage 3/5/6 decide query-time/user-facing consequences within their own contracts.

### Architecture risks

1. PostgreSQL vector/full-text performance at the upper V1 envelope requires benchmark validation.
2. Temporal extraction quality is a primary product risk because historical expressions are nuanced and false precision is unacceptable.
3. Reprocessing reuse requires strict generation-compatibility checks to avoid stale derived artifacts.
4. One globally active SearchRepresentationGeneration simplifies correctness but makes full search-model migration a coordinated cutover.
5. One corpus per logical document simplifies V1 evidence-boundary enforcement but is a product/architecture constraint that should remain documented globally.

### Review conclusion

No contradiction requires reopening Stage 1. The orchestrator review is complete, ADR-002/003/004 are accepted, and the accepted global architecture has been updated.

Stage 2 is **Implementation Ready**.

---

## Orchestrator Handoff

### Stage

Stage 2 — Data Ingestion Pipeline

### Status

**Implementation Ready.**

### Major Decisions

- Stable LogicalDocument identity with immutable DocumentVersions.
- Explicit Create Document versus Update Document operations.
- Exact uploaded-byte SHA-256 source hash for idempotency/equivalence.
- One corpus owner per logical document in V1; corpus ID propagated to searchable chunks.
- Canonical normalized structural document representation.
- Structure-aware, token-bounded chunking with overlap only for forced splits.
- Deterministic generation-scoped chunk identity and durable source-span provenance.
- Structured multi-mention temporal evidence with ranges, precision, uncertainty, BCE/CE, unresolved relative expressions, and explicit temporal origin.
- Dense + lexical representation required for search readiness.
- ProcessingGeneration separated from SearchRepresentationGeneration.
- One active ProcessingGeneration chunk set per active DocumentVersion.
- One globally active SearchRepresentationGeneration in V1.
- Canonical chunks/evidence are authoritative; search indexes are derived/rebuildable.
- Asynchronous checkpointed ingestion with durable IngestionRun attempts.
- No partially searchable document versions or processing generations.
- Atomic publication/active-version-and-processing-generation cutover.
- READY_DEGRADED with per-capability state for explicitly permitted temporal/provenance-location degradation.
- Incremental reprocessing/re-indexing and durable deletion/tombstone behavior.

### Global Architecture Changes Accepted

- Document/version/processing/search-generation lifecycle.
- Explicit active DocumentVersion + ProcessingGeneration publication contract.
- Structured temporal evidence representation and temporal-origin distinction.
- Canonical evidence versus derived search-index publication semantics.
- One-corpus-per-document V1 ownership.
- Capability-aware degraded readiness.
- PostgreSQL + integrated vector/full-text + ArtifactStore V1 persistence architecture.
- Asynchronous ingestion/publication boundary.

### Dependencies

- Stage 3 must enforce selected corpus plus active document/version/processing-generation/search-generation/deletion eligibility.
- Stage 3 owns query-time dense/lexical/temporal retrieval and ranking.
- Stage 5 owns final evidence deduplication/corroboration using Stage 2 lineage/hash signals.
- Stage 6 owns citation rendering from Stage 2 authoritative provenance.
- Stage 7 must evaluate temporal extraction, provenance, chunking, and lifecycle correctness.
- Stage 8 must trace ingestion runs, stages, failures, counts, and publication validation.
- Stage 10 may evolve worker/object/search deployment topology.

### ADRs Accepted

- `ADR-002-ingestion-identity-versioning-publication.md` — Accepted.
- `ADR-003-temporal-evidence-representation.md` — Accepted.
- `ADR-004-v1-persistence-search-storage.md` — Accepted.

### New Specs Required

None currently required. Component specifications should be created only if implementation exposes a genuinely independent contract that no longer fits this stage document.

### Open Questions

No architecture-blocking Stage 2 question remains. Concrete libraries/models/index parameters/retention policy are implementation or evaluation choices.

### Risks

- PostgreSQL vector/full-text performance at target scale,
- temporal extraction false precision or low recall,
- stale artifact reuse if generation compatibility is implemented loosely,
- coordinated cutover complexity for SearchRepresentationGeneration migration,
- future pressure to permit one logical document in multiple corpora.

### Files Created or Updated

- `docs/stages/02-ingestion.md`
- `docs/architecture/architecture.md`
- `docs/architecture/decisions/ADR-002-ingestion-identity-versioning-publication.md`
- `docs/architecture/decisions/ADR-003-temporal-evidence-representation.md`
- `docs/architecture/decisions/ADR-004-v1-persistence-search-storage.md`

Stage 2 acceptance is complete and its global decisions are integrated into the accepted architecture.