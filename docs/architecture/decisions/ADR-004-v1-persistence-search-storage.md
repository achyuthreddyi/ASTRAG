# ADR-004: V1 Persistence and Search Storage

## Status

Proposed — requires orchestrator approval.

## Context

Stage 2 requires durable storage for corpus/document lifecycle, immutable versions and generations, canonical chunks, temporal metadata, ingestion state, dense vectors, lexical search fields, original source files, and normalized document artifacts.

V1 assumes a single tenant, low concurrency, hundreds to thousands of documents, and a design envelope of roughly one million chunks. The global architecture intentionally deferred concrete document/vector/search stores to Stage 2.

The design should minimize operational complexity while preserving a clean separation between canonical evidence and rebuildable search projections.

## Decision

For V1, use **PostgreSQL as the authoritative relational store for lifecycle metadata, canonical chunks, temporal metadata, and search-representation metadata**, with an integrated vector capability such as pgvector for dense-vector storage/search and PostgreSQL full-text capabilities for lexical search representation.

Use a separate **ArtifactStore abstraction** for large immutable artifacts such as:

- original uploaded source files,
- canonical normalized-document artifacts.

The V1 ArtifactStore may use local filesystem/object storage depending on deployment, but ingestion code depends on the abstraction rather than direct filesystem calls.

### Canonical versus derived state

Canonical evidence records and lineage are authoritative. Dense/vector and lexical indexes are derived/rebuildable projections.

Canonical chunks are stored independently of generation-specific search representations.

Conceptually:

```text
PostgreSQL
├── corpora
├── logical_documents
├── document_versions
├── processing_generations
├── ingestion_runs
├── chunks
├── chunk_source_spans
├── temporal_mentions
├── search_representation_generations
└── chunk_search_representations

ArtifactStore
├── original source artifacts
└── normalized-document artifacts
```

### Dense representation

Dense embeddings are persisted as generation-specific representation data in PostgreSQL and indexed through the vector extension. Persisted vectors allow indexes to be rebuilt without necessarily re-calling the embedding provider.

### Lexical representation

V1 materializes lexical/full-text-searchable representation rather than requiring a learned numeric sparse vector. Stage 2 prepares/indexes lexical fields; Stage 3 owns query-time lexical ranking, dense/lexical combination, fusion, Top-K, and reranking.

### Search generations

One SearchRepresentationGeneration is active globally for V1. Search representation rows retain generation identity so a new generation can be built and validated before atomic activation.

### Transaction and publication boundary

ASTRAG does not require distributed transactions across artifact and search/index storage.

Canonical metadata is committed first, derived search data is built and validated, and publication/activation occurs through application-level state transitions. Retrieval performs eligibility checks so stale derived index entries cannot become valid evidence after deletion or generation cutover.

## Consequences

### Positive

- Low V1 operational complexity.
- Strong relational semantics for lifecycle/versioning/publication.
- Corpus/document/generation metadata and vector filtering remain close together.
- Fewer synchronization boundaries than a separate vector database/search engine.
- Canonical chunks and persisted representations permit index rebuilds.
- Architecture remains compatible with later migration to specialized search stores if required.

### Negative

- PostgreSQL must carry relational, dense-vector, and lexical workloads.
- Performance near the upper V1 scale envelope must be benchmarked.
- Native full-text ranking may not provide every feature of a dedicated BM25/search engine.
- A later move to dedicated vector/search infrastructure would require migration work.

## Alternatives Considered

### Relational metadata + dedicated vector database + object storage

Viable and potentially useful at larger scale, but rejected for initial V1 because it introduces another consistency boundary and operational system before benchmark evidence requires it.

### Dedicated search engine for lexical retrieval

Deferred. PostgreSQL full-text capabilities provide a simpler V1 starting point; Stage 3 evaluation can determine whether a dedicated lexical engine is necessary.

### Vector database as authoritative chunk store

Rejected because document lifecycle, versioning, provenance, deletion, and publication require stronger canonical relational semantics than a vector index should be expected to provide.

### Store source files as database blobs

Rejected as the primary design because large immutable artifacts are better represented through an ArtifactStore boundary.

## Revisit Triggers

Revisit if:

- retrieval benchmarks at the target chunk scale miss latency/recall requirements,
- vector index maintenance becomes operationally problematic,
- lexical evaluation requires capabilities unavailable in the integrated store,
- multi-tenant/production concurrency materially increases,
- or independent scaling of search infrastructure becomes necessary.

## Affected Stages

- Stage 2 — Data Ingestion Pipeline
- Stage 3 — Retrieval Pipeline
- Stage 8 — Observability & Debugging
- Stage 10 — Production / Serving

## Related Documents

- `NORTHSTAR.md`
- `docs/architecture/architecture.md`
- `docs/stages/01-problem-definition.md`
- `docs/stages/02-ingestion.md`
