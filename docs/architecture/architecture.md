# ASTRAG — System Architecture

## Purpose

This document describes the current accepted end-to-end architecture of ASTRAG at a project-wide level.

It contains only architecture accepted across stages. Stage-specific implementation details belong in `docs/stages/`, and significant architecture choices belong in `docs/architecture/decisions/`.

Stage 1 defines the global behavioral contract. Stage 2 defines the accepted ingestion lifecycle, temporal-evidence representation, publication boundary, and V1 persistence/search-storage foundation. Stage 3 defines the accepted deterministic local retrieval architecture, temporal retrieval semantics, query-understanding boundary, and concurrent eligibility/cutover policy. Broader orchestration, context assembly, generation, and production serving details remain owned by later stages.

---

## System Goal

ASTRAG is an evidence-grounded agentic RAG system that supports general-purpose retrieval-augmented QA while being specifically optimized and evaluated for historical and temporal question answering.

The system combines:

- user-selected document corpora,
- semantic retrieval,
- lexical retrieval,
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
        │ relevant conversation context
        ▼
Query + Temporal Understanding
(coordinated by Stage 4)
        │
        │ structured retrieval intent
        ▼
Agent / Orchestration
        │
        │ enforce configured source boundary
        │
        ├───────────────┐
        ▼               ▼
Local Corpus         Web Retrieval
Retrieval            (when Web ON)
(Stage 3)               │
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

The diagram expresses logical responsibilities and accepted storage/evidence boundaries, not deployment topology.

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
- The agent may choose strategy within the configured boundary but may not override the boundary.

---

## Global Architectural Invariants

### 1. Evidence Grounding

Material factual claims must be grounded in retrieved evidence from sources allowed for the current query.

Insufficient evidence is a valid answer state.

### 2. Corpus Isolation

Corpora are first-class query boundaries.

A query may search one or more selected corpora using union semantics, but evidence from unselected corpora must remain inaccessible to that query's factual answer.

In V1, each logical document has exactly one owning corpus at a time. Corpus identity survives ingestion and retrieval so selected-corpus enforcement is structural.

Target corpus-boundary violation rate: **0**.

### 3. Provenance Preservation

Evidence provenance must survive the complete pipeline.

Local evidence remains attributable to:

- corpus,
- logical document,
- immutable document version,
- active processed chunk set / ProcessingGeneration,
- SearchRepresentationGeneration,
- canonical chunk,
- page/section/source spans where available.

Web evidence retains external-source identity.

Later stages must not discard provenance merely because doing so makes an intermediate interface tidier.

### 4. Temporal Information Is First-Class

ASTRAG preserves and reasons over temporal information including:

- exact dates,
- ranges,
- before/after relationships,
- ordering,
- approximate periods,
- BCE/CE,
- temporal uncertainty,
- multiple temporal mentions,
- recurring month/day semantics,
- unresolved relative expressions.

Stage 2 persists structured TemporalMentions while retaining original wording and uncertainty. Source/document metadata time is explicitly distinguishable from temporal expressions mentioned in content; source time must not silently become event time.

Stage 3 consumes structured query-time TemporalIntent values and uses temporal information for candidate generation/ranking without converting optional temporal enrichment into a universal evidence-eligibility requirement.

### 5. Conflict Preservation

Conflicting evidence must not be silently collapsed into a single claim.

The system preserves enough independent source identity for later stages to expose conflicting claims and cite each side.

### 6. Duplicate Evidence Must Not Inflate Corroboration

Duplicate or substantially copied evidence must not be represented as independent confirmation merely because it arrived through multiple retrieval paths.

Stage 2 preserves exact source hashes, chunk content hashes, and lineage signals.

Stage 3 consolidates repeated retrieval hits for the same canonical `chunk_id` while keeping all route signals. Distinct canonical chunks remain distinct even when duplicate-lineage signals match.

Final semantic/source-level deduplication and corroboration semantics belong to Stage 5.

### 7. Short-Term Conversation Is Interpretive Context

Short-term conversation may resolve references such as `that event` or `what happened next`.

It is not an additional factual evidence source and cannot bypass the current query's corpus/web configuration.

### 8. Graceful Evidence-Source Failure

Configured retrieval sources/routes should fail independently where practical.

If one configured source fails while another returns usable evidence, ASTRAG may produce a grounded partial answer using the successful source and explicitly disclose the retrieval failure.

Successful retrieval with no candidates/evidence must remain distinguishable from retrieval-system failure.

### 9. Traceability and Evaluation

The architecture must make it possible to observe at least:

- user query,
- selected corpora,
- web setting,
- interpreted temporal intent/constraints,
- retrieval profile,
- retrieval state/configuration identities,
- routes executed,
- retrieved evidence/provenance,
- eligibility rejects/state changes,
- retrieval failures/degradation,
- context presented to generation,
- final citations,
- ingestion/publication lineage,
- latency,
- token usage,
- cost where applicable.

Evaluation and observability are cross-cutting requirements rather than end-of-project additions.

### 10. Immutable Source Versions and Explicit Generations

ASTRAG separates:

- `LogicalDocument` — stable logical source identity,
- `DocumentVersion` — immutable uploaded source-content version,
- `ProcessingGeneration` — immutable parser/normalizer/chunker-compatible processing configuration,
- `SearchRepresentationGeneration` — immutable dense/lexical representation configuration,
- `IngestionRun` — one durable processing attempt.

Source changes create DocumentVersions. Processing changes do not. Search-representation changes do not create new source/chunk versions.

Active documents may use different ProcessingGenerations. V1 uses one globally active SearchRepresentationGeneration for query-time local search.

### 11. Atomic Publication and No Partial Search Visibility

New source versions, processed chunk sets, and search representations are built privately and validated before publication.

A logical document's active publication identifies both its active `document_version_id` and active `processing_generation_id`.

Partially parsed, represented, or indexed evidence is never query-visible.

If replacement or reprocessing fails, the prior active publication remains searchable.

`READY_DEGRADED` is permitted only for explicitly modeled optional capabilities. Dense representation, lexical representation, and core lineage are mandatory for searchability.

### 12. Canonical Evidence Is Authoritative; Search Indexes Are Derived

Canonical chunks, lineage, temporal metadata, lifecycle state, and representation metadata are authoritative persisted state.

Dense-vector and lexical indexes are rebuildable projections. Retrieval must not treat index membership alone as evidence eligibility.

Deletion disables authoritative retrieval eligibility before asynchronous/physical cleanup. Stale derived records must fail final eligibility validation.

### 13. Deterministic Local Retrieval Boundary

Core Stage 3 local retrieval consumes a structured request rather than raw conversation history.

Query + Temporal Understanding is an upstream logical responsibility coordinated by Stage 4. It resolves conversational/temporal interpretation where safe and preserves unresolved/uncertain state when not safe.

Stage 3 owns deterministic local retrieval mechanics. Stage 4 owns multi-step strategy, web/local coordination, evidence-seeking retries/replanning, and stopping behavior.

### 14. V1 Hybrid Local Retrieval

Under ADR-005:

- dense and lexical local retrieval execute by default,
- strongly temporal requests may additionally execute a structured temporal candidate route,
- route hits for the same canonical chunk are consolidated,
- Reciprocal Rank Fusion is the V1 fusion baseline,
- strong temporal profiles may apply a bounded deterministic temporal adjustment,
- no learned reranker is required initially,
- exact vector search is the initial benchmark baseline,
- candidate/output budgets are internally controlled versioned configuration.

PostgreSQL FTS remains the primary lexical mechanism. A bounded deterministic exact-token/phrase fallback within PostgreSQL protects materially important literal queries that FTS normalization handles poorly.

### 15. Temporal Retrieval Preserves Recall and Uncertainty

Under ADR-006, structured temporal intent may drive temporal candidate generation and ranking but is not a hard cross-route evidence filter by default.

The temporal route may use strict route-local predicates. Dense/lexical candidates without matching temporal metadata remain eligible when useful, including when temporal extraction found zero mentions or degraded.

Cross-route hard temporal exclusion is limited to explicit typed constraints whose semantics genuinely require exclusion.

Approximate/uncertain periods remain approximate/uncertain; normalized search bounds never upgrade evidence to false exactness.

### 16. Retrieval Eligibility and Concurrent Cutovers Fail Closed

Under ADR-008, each Stage 3 execution captures a coherent request-scoped search state including the active SearchRepresentationGeneration and retrieval configuration identity.

One result must never mix incompatible SearchRepresentationGenerations.

Immediately before output, Stage 3 performs authoritative current-state validation. Candidates that became deleted, moved out of scope, superseded by publication/reprocessing, or otherwise ineligible are rejected and may be backfilled.

If a global SearchRepresentationGeneration cutover invalidates the request search space, Stage 3 may perform a bounded transparent restart under the new generation. If a coherent restart cannot complete, it fails closed rather than returning mixed/stale evidence.

Correctness does not depend on synchronous derived-index cleanup.

---

## Accepted Stage 2 Ingestion Architecture

### Document lifecycle and publication

Each V1 logical document belongs to one corpus and may have multiple immutable source versions.

Explicit Create Document and Update Document operations determine logical identity. Filename similarity does not infer updates.

Each source version stores SHA-256 over exact uploaded bytes for idempotency/exact-content equivalence. The hash is not logical document identity.

Only one replacement version processes at a time for a logical document in V1. Existing active evidence remains searchable until the replacement passes publication validation and is atomically activated.

Reprocessing an existing source version under a new ProcessingGeneration follows the same private-build/validate/cutover rule.

### Stage 2 → Stage 3 persisted contract

Local searchable evidence exposes enough information for Stage 3 to obtain/enforce:

- corpus identity,
- logical document identity,
- immutable document version,
- chunk identity and canonical source text,
- active ProcessingGeneration identity,
- active SearchRepresentationGeneration identity,
- dense/lexical search representations,
- structured temporal mentions,
- stable page/section/source-span provenance where available,
- capability/degraded state,
- publication/readiness eligibility,
- deletion/tombstone eligibility,
- duplicate-lineage/hash signals where relevant.

A returned local record is valid evidence only when it belongs to selected corpus scope and satisfies the authoritative active lifecycle/generation state.

### Failure and degraded capability model

Unsupported, encrypted/password-protected, scanned/image-only, empty, corrupt, or otherwise non-extractable inputs fail non-retryably as appropriate.

Transient processing failures are retryable through durable IngestionRuns/checkpoints.

Temporal extraction or optional provenance-location enrichment may be degraded while complete semantic/lexical evidence remains searchable. Zero temporal mentions is a successful extraction outcome and is distinct from temporal subsystem failure.

Dense or lexical representation failure blocks publication.

### Deletion and corpus deletion

Deletion first removes authoritative retrieval eligibility and then performs derived-index/artifact cleanup. A durable deleting/tombstone state survives partial cleanup failure.

Deleting a corpus semantically deletes its owned documents and artifacts through the same lifecycle rules.

---

## Accepted Stage 3 Local Retrieval Architecture

### Structured request contract

Stage 3 conceptually receives:

```text
LocalRetrievalRequest
- query_id
- original_question
- retrieval_query
- selected_corpus_ids[]
- temporal_intents[]
- metadata_constraints[]
- retrieval_profile
- interpretation_metadata
```

Unknown profile values are invalid requests. When a profile is omitted, Stage 3 derives a deterministic default from structured intent so temporal requests are not silently downgraded to generic fact lookup.

### Retrieval routes

Normal V1 local retrieval executes:

```text
Dense Retrieval
+ Lexical Retrieval
+ Temporal Retrieval when structured temporal intent/profile requires it
```

Dense retrieval uses the captured active SearchRepresentationGeneration.

Lexical retrieval uses PostgreSQL FTS plus the bounded literal fallback when necessary.

Temporal retrieval searches structured TemporalMentions while preserving multiple mentions, source/content origin, semantic role, precision, certainty, BCE/CE, ranges, and unresolved state.

### Fusion and ranking

Candidate lists are consolidated by canonical `chunk_id` before fusion.

V1 uses RRF because route score domains are heterogeneous. The RRF constant and candidate budgets are configuration, not architectural constants.

Strong temporal profiles may apply a bounded deterministic post-RRF temporal adjustment.

A mild document-level diversity penalty may be used as a retrieval-quality safeguard, but final context diversity remains Stage 5.

No learned reranker is present in the initial V1 baseline. Reranking is reconsidered when evaluation shows relevant evidence exists in the fused pool but is consistently ordered below Stage 5's practical cutoff.

### Retrieval result contract

Stage 3 returns provenance-complete canonical evidence candidates containing enough identity and retrieval metadata for later stages, including:

- corpus/document/version/ProcessingGeneration/SearchRepresentationGeneration/chunk identity,
- authoritative `source_text`,
- provenance/location metadata where available,
- TemporalMentions,
- duplicate-lineage signals,
- route signals/ranks,
- temporal match information,
- fusion/final Stage 3 rank,
- capability/degradation state.

Derived embedding/contextualized text never replaces canonical source evidence.

### Retrieval outcome contract

Stage 3 distinguishes at least:

```text
SUCCESS_WITH_CANDIDATES
SUCCESS_NO_CANDIDATES
SUCCESS_DEGRADED
FAILURE
```

A route failure may degrade to other successful routes. Database-wide unavailability, inability to verify authoritative eligibility, incoherent search-generation state, or invalid request state never masquerades as successful no-results retrieval.

Stage 3 does not decide final evidence sufficiency/answerability.

---

## V1 Persistence and Search Storage

ADR-004 establishes the persistence boundary:

- PostgreSQL is the authoritative relational store for corpus/document lifecycle, immutable versions/generations, canonical chunks, provenance, temporal metadata, ingestion state, and search-representation metadata.
- Integrated vector capability such as pgvector stores/searches dense embeddings.
- PostgreSQL full-text search provides the primary V1 lexical representation/search mechanism.
- ArtifactStore stores large immutable original-source and normalized-document artifacts.

This integrated design targets one primary user, low concurrency, hundreds to thousands of documents, and approximately up to one million chunks.

Vector, lexical fallback, temporal, and eligibility-validation performance near the upper V1 envelope must be benchmarked before introducing specialized search infrastructure.

PostgreSQL search indexes remain derived projections rather than canonical evidence authority.

---

## Major Logical Components

1. **Ingestion / Document Lifecycle**
   - owns corpus/document lifecycle and immutable source versions,
   - parses, normalizes, chunks, and enriches documents,
   - produces dense/lexical representations,
   - validates and atomically publishes searchable evidence,
   - manages reprocessing, retries, deletion, and generation cutovers.

2. **Canonical Evidence + Persistence**
   - stores authoritative lifecycle/chunks/provenance/temporal/representation metadata,
   - stores immutable source/normalized artifacts behind ArtifactStore,
   - treats search indexes as derived/rebuildable.

3. **Client / Query Interface**
   - receives question, selected corpora, web setting, relevant short-term conversation.

4. **Query + Temporal Understanding**
   - upstream logical component coordinated by Stage 4,
   - resolves conversational references where safe,
   - resolves query-time temporal language/current-date-relative expressions,
   - preserves ambiguity/uncertainty,
   - produces structured retrieval intent/profile recommendation.

5. **Agent / Orchestration**
   - enforces configured source policy,
   - coordinates Query + Temporal Understanding,
   - coordinates local/web/tool execution,
   - owns multi-step retrieval strategies, replanning, retries that alter strategy, and stopping behavior.

6. **Local Corpus Retrieval (Stage 3)**
   - searches only selected executable corpora,
   - executes deterministic dense + lexical (+ temporal when appropriate) retrieval,
   - enforces authoritative lifecycle/generation/deletion eligibility,
   - preserves provenance and temporal/duplicate-lineage metadata,
   - performs same-chunk consolidation/RRF and bounded retrieval-level adjustments,
   - fails closed on unverifiable or incoherent eligibility state.

7. **Web Retrieval**
   - executes whenever Web is ON in V1,
   - preserves external-source provenance,
   - fails independently from local retrieval where practical.

8. **Evidence Pipeline / Context Assembly (Stage 5)**
   - combines permitted local/web evidence,
   - performs final semantic/source deduplication and corroboration handling,
   - preserves conflicts,
   - assesses evidence sufficiency,
   - applies context diversity/source grouping/ordering/token budgets,
   - selects final context for generation.

9. **Grounded Generation (Stage 6)**
   - answers from retrieved/assembled evidence,
   - exposes conflicts/uncertainty,
   - renders citations,
   - acknowledges insufficient evidence.

10. **Evaluation + Observability**
   - measures component/end-to-end quality,
   - traces source configuration, ingestion publication, retrieval state/ranking, and agent execution,
   - tracks latency/cost.

These are logical boundaries. Service/process boundaries, frameworks, providers, and production deployment topology remain undecided except where an accepted ADR states otherwise.

---

## Current Data Flow

### Ingestion

```text
Create / Update Supported Document
→ Persist source + lifecycle identity
→ Parse / Normalize / Chunk
→ Temporal + provenance enrichment
→ Dense + lexical representation
→ Build derived search projection
→ Publication validation
→ Atomic active publication
→ READY / permitted READY_DEGRADED
```

### Local-only query

```text
Query + Selected Corpora + Web OFF
→ Query + Temporal Understanding
→ Structured LocalRetrievalRequest
→ Dense + Lexical (+ Temporal when appropriate)
→ candidate eligibility
→ same-chunk consolidation + RRF
→ bounded retrieval adjustments
→ final authoritative current-state validation/backfill
→ Stage 5 context/sufficiency processing
→ Grounded Generation
→ Answer + Local Citations
```

### Hybrid query

```text
Query + Selected Corpora + Web ON
→ Query + Temporal Understanding
→ Stage 4 coordinates Local Retrieval + mandatory Web Retrieval
→ Stage 5 evidence combination/conflict/deduplication/sufficiency/context selection
→ Grounded Generation
→ Answer + Local/Web Citations
```

### Web-only query

```text
Query + Web ON + No Corpus
→ Query + Temporal Understanding
→ Web Retrieval
→ Stage 5 evidence assessment/context assembly
→ Grounded Generation
→ Answer + Web Citations
```

---

## Scale and V1 Assumptions

Current accepted assumptions:

- single tenant,
- one primary user / low concurrency,
- hundreds to thousands of documents,
- design envelope up to approximately one million chunks,
- one embedding model initially,
- one globally active SearchRepresentationGeneration,
- text-extractable PDF/TXT/Markdown/DOCX,
- OCR and multimodal ingestion excluded,
- PostgreSQL with integrated dense-vector and lexical-search capabilities is the V1 search/storage foundation,
- no mandatory external message broker for Stage 2 ingestion,
- no ANN requirement initially,
- no learned reranker initially.

These assumptions constrain later designs without requiring premature distributed infrastructure.

---

## Implementation-Time Retrieval Validation Requirements

Stage 3 implementation must validate at least:

- Recall@K, MRR, nDCG@K, Hit Rate@K and Precision@K where useful,
- temporal retrieval correctness/Recall@K,
- dense-only vs lexical-only vs hybrid vs hybrid+temporal ablations,
- zero corpus-boundary violations,
- zero stale/ineligible evidence leakage,
- correct provenance/lineage,
- exact-date/range/before/after/approximate/BCE-CE/recurring-day cases,
- rare names, numbers, quoted phrases, acronyms/codes, and lexical fallback cases,
- `TEMPORAL_READY + 0 mentions` versus `TEMPORAL_DEGRADED`,
- deletion/publication/ProcessingGeneration/corpus-move/SRG cutover races,
- no mixed SearchRepresentationGeneration output,
- deterministic stable ordering for fixed request/state/config,
- exact-vector/FTS/fallback/temporal/final-eligibility latency at representative V1 sizes.

Exact numeric candidate budgets, RRF constants, temporal-adjustment weights, diversity penalties, and latency SLOs remain implementation/evaluation configuration.

---

## Decisions Intentionally Deferred

The following remain owned by later implementation/stages or benchmark-triggered revisits:

- concrete PDF/DOCX parser libraries,
- exact chunk-size/overlap tuning,
- exact temporal-extraction libraries/models,
- embedding model/provider,
- PostgreSQL vector/full-text/fallback index tuning,
- exact retrieval candidate-budget defaults,
- exact RRF constant,
- exact temporal-adjustment weights,
- exact document-diversity penalty,
- ANN adoption/index type pending benchmark need,
- learned reranker choice pending ranking evaluation,
- agent framework,
- concrete web-search provider integration,
- context token budgeting,
- prompt architecture,
- generation model/provider,
- exact external API schema,
- caching,
- artifact retention/garbage collection,
- production queue/topology,
- source-quality ranking,
- production/multi-user debug-text retention policy.

When one of these materially changes global architecture, the owning stage must escalate it and create/revise an ADR where appropriate.

---

## Accepted ADRs

- `ADR-001-query-source-execution-policy.md` — V1 query source configuration is authoritative; Web ON mandates web retrieval.
- `ADR-002-ingestion-identity-versioning-publication.md` — source identity, immutable versions, processing/search generations, active publication, and authoritative retrieval eligibility are distinct.
- `ADR-003-temporal-evidence-representation.md` — temporal evidence preserves multiple mentions, source/document versus content origin, normalization, precision, and uncertainty without inventing exactness.
- `ADR-004-v1-persistence-search-storage.md` — PostgreSQL plus integrated vector/full-text capabilities and ArtifactStore form the V1 persistence/search-storage foundation.
- `ADR-005-v1-local-hybrid-retrieval-fusion-policy.md` — dense + lexical retrieval are the V1 baseline, temporal routing is additive, same-chunk signals are consolidated, and RRF is the initial fusion policy.
- `ADR-006-temporal-query-retrieval-policy.md` — structured uncertainty-preserving temporal intent drives candidate generation/ranking without universal hard temporal exclusion.
- `ADR-007-query-understanding-retrieval-boundary.md` — Query + Temporal Understanding is upstream/coordinated by Stage 4; Stage 3 receives a structured request and owns deterministic retrieval mechanics.
- `ADR-008-retrieval-eligibility-consistency-cutover-policy.md` — local retrieval captures coherent search state, performs output-time authoritative validation, and fails closed/restarts boundedly across incompatible cutovers.

---

## Stage Alignment

- **Stage 1** defines the behavioral contract and global evidence invariants.
- **Stage 2** owns ingestion, corpus/document lifecycle, immutable versions/generations, provenance capture, temporal metadata extraction, search representation generation, publication, reprocessing, and deletion.
- **Stage 3** owns deterministic query-time local retrieval, selected-corpus enforcement, authoritative eligibility/cutover handling, dense/lexical/temporal candidate retrieval, same-chunk consolidation, RRF/bounded retrieval ranking, and retrieval-specific failures/degradation.
- **Stage 4** owns Query + Temporal Understanding coordination, broader agent/tool orchestration, web + local coordination, multi-step query strategy, replanning, and stopping behavior within ADR-001.
- **Stage 5** owns final evidence combination, sufficiency assessment, semantic deduplication/corroboration, context diversity/source grouping, chronological/context ordering, token budgeting, and final context selection.
- **Stage 6** owns grounded response generation and citation rendering.
- **Stage 7** formalizes evaluation including the accepted Stage 3 retrieval/race/temporal benchmarks.
- **Stage 8** formalizes end-to-end tracing and operational observability including Stage 3 state/ranking traces.
- **Stage 9** adds reliability/guardrails, including stale evidence, timeout, and retrieved-content/prompt-injection protections, without weakening evidence boundaries.
- **Stage 10** defines production serving/scaling and may evolve worker/search deployment topology while preserving accepted canonical evidence/retrieval semantics.
