# ASTRAG — System Architecture

## Purpose

This document describes the current accepted end-to-end architecture of ASTRAG at a project-wide level.

It contains only architecture that has been accepted across stages. Stage-specific implementation details belong in `docs/stages/`, and significant architecture choices belong in `docs/architecture/decisions/`.

Stage 1 defines the global behavioral constraints. Stage 2 now defines the accepted ingestion lifecycle, temporal-evidence representation, publication boundary, and V1 persistence/search-storage foundation. Retrieval ranking, orchestration, context assembly, generation, and production serving details remain owned by later stages.

---

## System Goal

ASTRAG is an evidence-grounded agentic RAG system that supports general-purpose retrieval-augmented QA while being specifically optimized and evaluated for historical and temporal question answering.

The system combines:

- user-selected document corpora,
- semantic retrieval,
- temporal/date-aware retrieval,
- optional web access controlled per query,
- agentic orchestration,
- short-term conversational context,
- evidence-grounded generation,
- citations and traceability.

---

## High-Level Architecture

```text
Document Upload / Update
        ↓
Ingestion + Canonical Evidence
        ↓
Validated Search Publication
        ↓
PostgreSQL Search Projections
        │
        │ searchable local evidence
        ▼
Client / Query Interface
        │
        │ question
        │ selected_corpora[]
        │ web_enabled
        │ conversation context
        ▼
Query + Temporal Understanding
        │
        ▼
Agent / Orchestration
        │
        │ enforce query evidence boundary
        │
        ├───────────────┐
        ▼               ▼
Local Corpus         Web Retrieval
Retrieval            (when Web ON)
        │               │
        └───────┬───────┘
                ▼
         Evidence Pipeline
                │
                │ provenance
                │ temporal metadata
                │ retrieval signals
                ▼
         Context Assembly
                │
                ▼
       Grounded Generation
                │
                ▼
Answer + Citations + Conflict / Uncertainty Disclosure
```

The diagram expresses responsibilities and accepted storage boundaries, not deployment topology.

---

## Query Evidence Boundary

Every query defines its allowed evidence sources through:

```text
question
selected_corpora[]
web_enabled
conversation_context
```

The accepted V1 execution matrix is defined by ADR-001:

| Selected corpora | Web | Evidence sources |
| --- | --- | --- |
| One or more | OFF | Selected corpora only |
| One or more | ON | Selected corpora + web |
| None | ON | Web only |
| None | OFF | Invalid query |

The evidence boundary is authoritative.

- Unselected corpora cannot contribute factual evidence.
- Web OFF prohibits web evidence.
- Web ON requires web retrieval in V1.
- Conversation history cannot expand the current query's evidence permissions.
- Model memory cannot replace missing retrieved factual evidence.

The agent retains discretion over execution strategy within this boundary.

---

## Global Architectural Invariants

### 1. Evidence Grounding

Material factual claims must be grounded in retrieved evidence from sources allowed for the current query.

Insufficient evidence is a valid answer state.

### 2. Corpus Isolation

Corpora are first-class query boundaries.

A query may search one or more selected corpora using union semantics, but evidence from unselected corpora must remain inaccessible to that query's factual answer.

In V1, each logical document has exactly one owning corpus at a time. Corpus identity is preserved into searchable records so Stage 3 can enforce the query's selected-corpus boundary.

### 3. Provenance Preservation

Evidence provenance must survive the complete pipeline.

Local evidence remains attributable to corpus, logical document, immutable document version, processed chunk set, and chunk. Page/section/source-span metadata is preserved where available. Web evidence retains external source identity.

Later stages must not discard provenance merely because doing so makes an intermediate interface tidier.

### 4. Temporal Information Is First-Class

ASTRAG preserves and reasons over temporal information including:

- exact dates,
- date ranges,
- before/after relationships,
- ordering,
- approximate dates,
- BCE/CE,
- temporal uncertainty,
- multiple temporal mentions,
- unresolved relative expressions.

Stage 2 persists structured temporal mentions while retaining original wording and uncertainty. Source/document metadata time is explicitly distinguishable from temporal expressions mentioned in content; source time must not silently become event time.

Temporal metadata remains available across ingestion, retrieval, context assembly, generation, and evaluation where applicable.

### 5. Conflict Preservation

Conflicting evidence must not be silently collapsed into a single claim.

The system must preserve enough provenance for generation to expose conflicting claims and cite each side.

### 6. Duplicate Evidence Must Not Inflate Corroboration

Duplicate or substantially copied evidence from multiple retrieval paths must not be represented as independent confirmation.

Stage 2 preserves exact source hashes, chunk content hashes, and lineage signals. Final semantic deduplication and corroboration semantics belong to Stage 5.

### 7. Short-Term Conversation Is Interpretive Context

Short-term conversation may resolve references such as "that event" or "what happened next".

It is not an additional factual evidence source and cannot bypass the current query's corpus/web configuration.

### 8. Graceful Evidence-Source Failure

Configured retrieval sources should fail independently where practical.

If one source fails while another returns usable evidence, ASTRAG may produce a grounded partial answer using the successful source and explicitly disclose the retrieval failure.

Successful retrieval with no relevant evidence must remain distinguishable from retrieval-system failure.

### 9. Traceability and Evaluation

The architecture must make it possible to observe at least:

- the user query,
- selected corpora,
- web setting,
- interpreted temporal constraints,
- retrieval paths executed,
- retrieved evidence and provenance,
- retrieval failures,
- context presented to generation,
- final citations,
- ingestion/publication lineage for local evidence,
- latency,
- token usage,
- and cost where applicable.

Evaluation and observability are cross-cutting requirements rather than end-of-project additions.

### 10. Immutable Source Versions and Explicit Generations

ASTRAG separates:

- `LogicalDocument` — stable logical source identity,
- `DocumentVersion` — immutable uploaded source-content version,
- `ProcessingGeneration` — immutable parser/normalizer/chunker-compatible processing configuration,
- `SearchRepresentationGeneration` — immutable dense/lexical representation configuration,
- `IngestionRun` — one durable processing attempt.

Source changes create DocumentVersions. Processing changes do not. Search-representation changes do not create new source or chunk versions.

Active documents may use different ProcessingGenerations. V1 uses one globally active SearchRepresentationGeneration for query-time local search.

### 11. Atomic Publication and No Partial Search Visibility

New source versions, processed chunk sets, and search representations are built privately and validated before publication.

A logical document's active publication identifies both its active `document_version_id` and active `processing_generation_id`. Reprocessing the same immutable source version therefore has an explicit cutover target rather than overloading DocumentVersion.

Partially parsed, partially represented, or partially indexed evidence is never query-visible.

If replacement or reprocessing fails, the prior active publication remains searchable.

`READY_DEGRADED` is permitted only for explicitly modeled optional capabilities. Dense representation, lexical representation, and core corpus/document/version/chunk lineage are mandatory for searchability.

### 12. Canonical Evidence Is Authoritative; Search Indexes Are Derived

Canonical chunks, lineage, temporal metadata, lifecycle state, and representation metadata are authoritative persisted state.

Dense-vector and lexical indexes are rebuildable projections. Retrieval must not treat index membership alone as evidence eligibility.

Deletion disables authoritative retrieval eligibility before asynchronous/physical cleanup. Stale derived records must therefore fail the final eligibility check.

---

## Accepted Stage 2 Ingestion Architecture

### Document lifecycle and publication

Each V1 logical document belongs to one corpus and may have multiple immutable source versions.

Explicit Create Document and Update Document operations determine logical identity. Filename similarity does not infer updates.

Each source version stores a SHA-256 hash of the exact uploaded bytes for idempotency and exact-content equivalence. The hash is not logical document identity.

Only one replacement version processes at a time for a logical document in V1. Existing active evidence remains searchable until the replacement passes publication validation and is atomically activated.

Reprocessing an existing source version under a new ProcessingGeneration follows the same private-build/validate/cutover rule.

### Stage 2 → Stage 3 persisted contract

Local searchable evidence exposes enough information for Stage 3 to obtain or enforce:

- corpus identity,
- logical document identity,
- immutable document version,
- chunk identity and source text,
- active ProcessingGeneration identity,
- active SearchRepresentationGeneration identity,
- dense and lexical search representations,
- structured temporal mentions,
- stable page/section/source-span provenance where available,
- capability/degraded state,
- publication/readiness eligibility,
- deletion/tombstone eligibility.

Stage 3 owns query-time retrieval, filtering, ranking, fusion, Top-K, reranking, and handling of degraded capabilities.

A returned local record is valid evidence only when it belongs to a selected corpus and matches the authoritative active document version, active processed chunk set, globally active SearchRepresentationGeneration, and non-deleted searchable state.

### Failure and degraded capability model

Unsupported, encrypted/password-protected, scanned/image-only, empty, corrupt, or otherwise non-extractable inputs fail non-retryably as appropriate.

Transient processing failures are retryable through durable IngestionRuns and checkpoints. A retry is an execution attempt, not a new source version.

Temporal extraction or optional provenance-location enrichment may be degraded while otherwise complete semantic/lexical evidence remains searchable. Zero temporal mentions is a successful extraction outcome and is distinct from temporal subsystem failure.

Dense or lexical representation failure blocks publication.

### Deletion and corpus deletion

Deletion first removes authoritative retrieval eligibility and then performs derived-index and artifact cleanup. A durable deleting/tombstone state survives partial cleanup failure.

Deleting a corpus semantically deletes its owned documents and their versions/artifacts through the same lifecycle rules.

---

## V1 Persistence and Search Storage

ADR-004 establishes the initial persistence boundary:

- **PostgreSQL** is the authoritative relational store for corpus/document lifecycle, immutable versions and generations, canonical chunks, provenance, temporal metadata, ingestion state, and search-representation metadata.
- An integrated vector capability such as **pgvector** stores/indexes dense embeddings.
- **PostgreSQL full-text search** provides the V1 lexical-search representation/index.
- An **ArtifactStore abstraction** stores large immutable original-source and normalized-document artifacts; its concrete V1 backend may be local filesystem or object storage.

This integrated design is chosen for the accepted V1 envelope of one primary user, low concurrency, hundreds to thousands of documents, and roughly up to one million chunks. Vector/full-text performance near the upper envelope must be benchmarked before introducing a dedicated vector database or search engine.

PostgreSQL search indexes remain derived projections rather than the canonical evidence authority. This preserves a migration path to specialized search infrastructure if later stages demonstrate a need.

---

## Major Logical Components

The accepted architecture recognizes these logical responsibilities:

1. **Ingestion / Document Lifecycle**
   - owns corpus/document lifecycle and immutable source versions,
   - parses, normalizes, chunks, and enriches supported documents,
   - produces dense/lexical representations,
   - validates and atomically publishes searchable evidence,
   - manages reprocessing, retries, deletion, and generation cutovers.

2. **Canonical Evidence + Persistence**
   - stores authoritative lifecycle, chunks, provenance, temporal metadata, and representation metadata in PostgreSQL,
   - stores immutable source/normalized artifacts behind ArtifactStore,
   - treats search indexes as derived/rebuildable state.

3. **Client / Query Interface**
   - receives the question,
   - selected corpora,
   - web configuration,
   - relevant conversational context.

4. **Query + Temporal Understanding**
   - interprets semantic intent,
   - resolves query-time temporal language,
   - preserves temporal uncertainty.

5. **Agent / Orchestration**
   - enforces configured source boundaries,
   - coordinates retrieval/tool execution,
   - manages retries and stopping behavior,
   - does not override the source configuration.

6. **Local Corpus Retrieval**
   - searches only selected corpora,
   - enforces active publication/search-generation/deletion eligibility,
   - preserves document/corpus provenance,
   - consumes Stage 2 semantic, lexical, temporal, and provenance representations.

7. **Web Retrieval**
   - executes whenever Web is ON in V1,
   - preserves external-source provenance,
   - fails independently from local retrieval where practical.

8. **Evidence Pipeline / Context Assembly**
   - combines permitted evidence,
   - preserves conflicts,
   - avoids false duplicate corroboration,
   - orders and budgets context for generation.

9. **Grounded Generation**
   - answers from retrieved evidence,
   - exposes conflicts and uncertainty,
   - returns citations,
   - acknowledges insufficient evidence.

10. **Evaluation + Observability**
   - measures component and end-to-end quality,
   - traces source configuration, ingestion publication, and agent execution,
   - tracks latency and cost.

These are logical boundaries. Except for the accepted V1 persistence/search-storage choice, service boundaries, process boundaries, frameworks, providers, and production deployment topology remain undecided.

---

## Current Data Flow

### Ingestion

```text
Create / Update Supported Document
        ↓
Persist source + lifecycle identity
        ↓
Parse / Normalize / Chunk
        ↓
Temporal + provenance enrichment
        ↓
Dense + lexical representation
        ↓
Build derived search projection
        ↓
Publication validation
        ↓
Atomic active publication
        ↓
READY / permitted READY_DEGRADED
```

### Local-Only Query

```text
Query + Selected Corpora + Web OFF
        ↓
Query / Temporal Understanding
        ↓
Selected-Corpus Retrieval
        ↓
Authoritative eligibility check
        ↓
Evidence Assessment + Context Assembly
        ↓
Grounded Generation
        ↓
Answer + Local Citations
```

### Hybrid Query

```text
Query + Selected Corpora + Web ON
        ↓
Query / Temporal Understanding
        ↓
Local Retrieval + Web Retrieval
        ↓
Evidence Combination / Conflict Handling
        ↓
Context Assembly
        ↓
Grounded Generation
        ↓
Answer + Local/Web Citations
```

### Web-Only Query

```text
Query + Web ON + No Corpus
        ↓
Query / Temporal Understanding
        ↓
Web Retrieval
        ↓
Evidence Assessment + Context Assembly
        ↓
Grounded Generation
        ↓
Answer + Web Citations
```

---

## Scale and V1 Assumptions

Current accepted assumptions:

- single tenant,
- one primary user / low concurrency,
- hundreds to thousands of documents,
- design envelope up to approximately 1 million chunks,
- one embedding model initially,
- one globally active SearchRepresentationGeneration,
- text-extractable PDF, TXT, Markdown, and DOCX inputs,
- OCR and multimodal ingestion excluded from V1,
- PostgreSQL with integrated dense-vector and lexical-search capabilities is the initial V1 search/storage foundation,
- no mandatory external message broker for Stage 2 ingestion.

These assumptions constrain later designs without requiring production-scale distributed infrastructure prematurely.

---

## Decisions Intentionally Deferred

The following remain owned by later implementation/stages:

- concrete PDF/DOCX parser libraries,
- exact chunk-size/overlap tuning,
- exact temporal-extraction libraries/models,
- embedding model/provider,
- PostgreSQL vector/full-text index tuning,
- dense/lexical query fusion and ranking,
- reranking,
- temporal query representation and query-time temporal policy,
- agent framework,
- concrete web-search provider integration,
- context token budgeting,
- prompt architecture,
- generation model/provider selection,
- exact API schema,
- caching,
- artifact retention/garbage-collection policy,
- production queue/topology,
- source-quality ranking.

When one of these choices materially changes global architecture, the owning stage must escalate it to the orchestrator and create an ADR when appropriate.

---

## Accepted ADRs

- `ADR-001-query-source-execution-policy.md` — V1 query source configuration is authoritative; Web ON mandates web retrieval.
- `ADR-002-ingestion-identity-versioning-publication.md` — source identity, immutable versions, processing/search generations, active publication, and authoritative retrieval eligibility are distinct.
- `ADR-003-temporal-evidence-representation.md` — temporal evidence preserves multiple mentions, source/document versus content origin, normalization, precision, and uncertainty without inventing exactness.
- `ADR-004-v1-persistence-search-storage.md` — PostgreSQL plus integrated vector/full-text capabilities and ArtifactStore form the V1 persistence/search-storage foundation.

---

## Stage Alignment

- **Stage 1** defines the behavioral contract and global evidence invariants.
- **Stage 2** owns ingestion, corpora, document lifecycle, immutable versions/generations, provenance capture, temporal metadata extraction, search representation generation, publication, reprocessing, and deletion.
- **Stage 3** owns query-time local retrieval, selected-corpus enforcement, authoritative search eligibility checks, temporal/semantic/lexical retrieval behavior, ranking, and reranking.
- **Stage 4** owns orchestration within the source policy established by ADR-001.
- **Stage 5** owns evidence combination, semantic deduplication/corroboration, ordering, and context budgeting.
- **Stage 6** owns grounded response generation and citation rendering.
- **Stage 7** formalizes evaluation of the quality targets.
- **Stage 8** formalizes tracing and operational observability.
- **Stage 9** adds reliability and guardrails without weakening evidence boundaries.
- **Stage 10** defines production serving and scaling and may evolve worker/search deployment topology without changing canonical evidence semantics.
