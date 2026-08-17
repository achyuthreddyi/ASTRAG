# ASTRAG — System Architecture

## Purpose

This document describes the current accepted end-to-end architecture of ASTRAG at a project-wide level.

It contains only architecture accepted across stages. Stage-specific implementation details belong in `docs/stages/`, and significant architecture choices belong in `docs/architecture/decisions/`.

Stage 1 defines the global behavioral contract. Stage 2 defines the accepted ingestion lifecycle, temporal-evidence representation, publication boundary, and V1 persistence/search-storage foundation. Stage 3 defines the accepted deterministic local retrieval architecture, temporal retrieval semantics, query-understanding boundary, and concurrent eligibility/cutover policy. Stage 4 defines the accepted bounded orchestration execution model, immutable evidence policy, provider-neutral web retrieval boundary, and Stage 4 → Stage 5 evidence-gathering contract. Stage 5 defines accepted evidence relationship/corroboration semantics, conflict/coverage/sufficiency semantics, provenance-safe context selection, and the Stage 5 → Stage 6 `GenerationContext` contract. Stage 6 owns prompt construction and grounded response generation.

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
        ▼
Agent / Orchestration
        │
        │ immutable EvidencePolicy
        │ bounded adaptive execution
        ├───────────────┐
        ▼               ▼
Local Corpus         Web Retrieval
Retrieval            (when Web ON)
(Stage 3)               │
        │               │
        └───────┬───────┘
                ▼
     EvidenceGatheringResult
                │
                │ provenance + causal run lineage
                │ temporal metadata
                │ failures/degradation
                ▼
         Context Assembly
                │
                │ relationship/corroboration semantics
                │ conflict + coverage + sufficiency
                │ provenance-safe context selection
                ▼
        GenerationContext
                │
                ▼
       Grounded Generation
       (prompt owned by Stage 6)
                │
                ▼
Answer + Citations + Conflict / Uncertainty Disclosure
```

The diagram expresses logical responsibilities and accepted storage/evidence boundaries, not deployment topology or mandatory source-execution scheduling.

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

Stage 4 materializes this contract as an immutable request-scoped `EvidencePolicy`. Required source classes are independent bounded execution obligations. When both local and web are required and ready, concurrent initial execution is the preferred V1 scheduling strategy, but semantic correctness depends on executing both obligations rather than on a particular parallelism mechanism.

Stage 5 revalidates the immutable evidence boundary as defense in depth. Revalidation can reject invalid evidence but cannot expand or reduce the permitted source set.

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

Web evidence retains external-source identity and acquisition/completeness semantics where applicable.

Context selection or trimming may reduce text but must not erase or fabricate evidence identity, source spans, citation targets, or causal retrieval lineage.

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

Stage 4 preserves query-time temporal uncertainty through interpretation, reformulation, decomposition, and web constraints. Event/content time must not be silently translated into web publication-time filtering.

Stage 5 preserves temporal origin, precision, certainty, multiple mentions, BCE/CE semantics, and unresolved state during selection and ordering. Approximate evidence must not become falsely exact merely to simplify chronological presentation.

### 5. Conflict Preservation

Conflicting evidence must not be silently collapsed into a single claim.

Stage 4 may use a structured possible-conflict signal to justify bounded additional retrieval, but it does not perform final conflict grouping, choose a winner, suppress a side, or assign source authority.

Under ADR-012, Stage 5 owns final material conflict grouping and distinguishes factual, quantitative, temporal, and interpretation divergence from compatible detail. Stage 5 does not nominate a winning claim in V1.

Conflict is orthogonal to sufficiency. Evidence may be sufficient to answer by accurately presenting a disagreement.

### 6. Duplicate Evidence Must Not Inflate Corroboration

Duplicate or substantially copied evidence must not be represented as independent confirmation merely because it arrived through multiple retrieval paths.

Stage 2 preserves exact source hashes, chunk content hashes, and lineage signals.

Stage 3 consolidates repeated retrieval hits for the same canonical `chunk_id` while keeping all route signals. Distinct canonical chunks remain distinct even when duplicate-lineage signals match.

Stage 4 may consolidate only exact/identity-level operational repetition while preserving all retrieval-run associations.

Under ADR-011, Stage 5 owns final semantic/source relationship and corroboration semantics. It distinguishes:

```text
SAME_IDENTITY
EXACT_DUPLICATE
DERIVATIVE
INDEPENDENT
UNKNOWN_DEPENDENCE
```

Different documents, URLs, domains, corpora, or retrieval runs do not by themselves establish independent support. `UNKNOWN_DEPENDENCE` is not proof of derivation but is not counted as established independent corroboration.

### 7. Short-Term Conversation Is Interpretive Context

Short-term conversation may resolve references such as `that event` or `what happened next`.

It is not an additional factual evidence source and cannot bypass the current query's corpus/web configuration.

### 8. Graceful Evidence-Source Failure

Configured retrieval sources/routes should fail independently where practical.

If one configured source fails while another returns usable evidence, ASTRAG may produce a grounded partial answer using the successful source and explicitly disclose the retrieval failure.

Successful retrieval with no candidates/evidence must remain distinguishable from retrieval-system failure.

Stage 4 preserves successful candidates, source-specific failure/degradation metadata, and first-class required-source execution status. Stage 5 preserves these statuses in `GenerationContext` independently from whether that source contributes selected context.

### 9. Traceability and Evaluation

The architecture must make it possible to observe at least:

- user query,
- selected corpora,
- web setting,
- immutable EvidencePolicy,
- interpreted references and temporal intent/constraints,
- retrieval profile,
- retrieval state/configuration identities,
- routes/source classes executed,
- retrieval-run kind and causal lineage,
- query transformations/decomposition lineage,
- retrieved evidence/provenance,
- web acquisition/completeness state,
- eligibility rejects/state changes,
- retrieval failures/degradation,
- required-source execution status,
- orchestration budget consumption and stop reason,
- Stage 5 candidate rejection reasons,
- evidence relationship/dependency groups,
- corroboration decisions,
- conflict groups,
- coverage mapping,
- selection/drop decisions,
- token allocation and final context order,
- sufficiency assessment,
- context presented to generation,
- final citations,
- ingestion/publication lineage,
- latency,
- token usage,
- cost where applicable.

Evaluation and observability are cross-cutting requirements rather than end-of-project additions. Structured decisions/results are traced; arbitrary hidden model chain-of-thought prose is not required.

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

Stage 4 may select a supported Stage 3 retrieval profile but does not control Stage 3 route weights, RRF constants, raw candidate limits, eligibility mechanics, or SearchRepresentationGeneration behavior.

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

### 17. Request-Scoped EvidencePolicy Is Immutable

Under ADR-009, Stage 4 derives one request-scoped `EvidencePolicy` from selected corpora and the web setting.

`local_required` and `web_required` are derived from ADR-001 and are not independent reasoning outputs. Conversation context, query transformations, retrieved evidence, tool failures, or model reasoning cannot expand or reduce the policy.

### 18. Orchestration Is Bounded and Deterministic at the Control Plane

Stage 4 uses a bounded adaptive application state machine rather than an open-ended agent loop.

Deterministic application control owns schema validation, source obligations, legal state transitions, budget accounting, retry ceilings, deadlines, tool-contract validation, outcome/failure normalization, stop-reason mapping, and result construction.

Bounded LLM/semantic reasoning may assist difficult reference/temporal interpretation, material-ambiguity judgment, intent-preserving reformulation, decomposition, and whether a permitted evidence-seeking action is useful. The reasoning model cannot increase budgets, alter source permissions, or own the orchestration loop.

### 19. Operational Retry and Evidence-Seeking Adaptation Are Distinct

Operational retries repeat the same logical request after retryable execution failure.

Evidence-seeking attempts change retrieval strategy while preserving factual intent and require an explicit traceable trigger. Reformulation/decomposition must preserve the original factual subject/objective, typed temporal uncertainty, and EvidencePolicy and cannot introduce unsupported factual premises.

All adaptive execution is bounded by global/per-source/tool/transformation budgets and a deadline.

### 20. Stage 4 → Stage 5 Evidence Contract Preserves Causal Lineage

Stage 4 emits an `EvidenceGatheringResult` containing at least:

```text
query identity
original + resolved query
EvidencePolicy
orchestration completion status
required-source statuses
retrieval runs with causal lineage
typed evidence/provenance
interpretation assumptions
failures/degradation
stop reason
```

Retrieval runs distinguish mandatory initial execution, operational retries, reformulation/decomposition runs, anchor recovery, possible-conflict follow-up, and other bounded evidence-seeking actions through explicit run kind and parent/trigger/transformation lineage.

Stage 5 must not infer orchestration trajectory from query text or execution order.

Orchestration completion is distinct from source retrieval outcome, Stage 5 assembly status, and final evidence sufficiency.

### 21. Web Retrieval Is Provider-Neutral and Grounding-Capable

Stage 4 depends on a provider-neutral logical Web Retrieval capability. Search, content acquisition, and normalization may be internally composed but remain one logical V1 capability.

Web candidates retain URL/source identity and usable grounding text. A snippet is not promoted to authoritative evidence when it cannot support grounding.

Full-page acquisition is not universally required. Extracted/selected/normalized content may satisfy the contract when usable grounding text is available, but the candidate must preserve whether the acquired content is full, partial, or of unknown completeness.

Provider-specific schemas/details remain below the logical contract. Event/content-time constraints remain distinct from web publication/source-time filters.

### 22. Retrieved Content Is Data, Not Control

Local and web evidence are data-plane inputs.

Retrieved content cannot modify EvidencePolicy, source permissions, orchestration budgets, legal transitions, tool permissions, system/control instructions, or generation-control metadata.

Stage 5 preserves this separation while assembling `GenerationContext`; Stage 9 adds defense in depth later.

### 23. V1 Runtime State Is Ephemeral; Structured Trace State Survives

Stage 4 runtime control state exists for the bounded request lifetime and does not require durable resume-from-checkpoint semantics in V1.

Append-oriented structured trace information must survive sufficiently for Stage 7 evaluation and Stage 8 observability/debugging. Exact trace backend and retention are later implementation/production decisions.

### 24. Stage 5 Owns Final Evidence Relationship and Corroboration Semantics

Under ADR-011, Stage 5 is the final boundary for semantic/source-level duplicate and dependence analysis.

Exact/derivative evidence may use a representative text plus alternate provenance to reduce token duplication without erasing source history. Raw source/evidence count is never a substitute for independent support.

V1 does not introduce numeric corroboration confidence, source-authority scores, trusted-domain truth ranking, or majority-vote truth selection.

### 25. Stage 5 Owns Material Conflict, Coverage, and Sufficiency

Under ADR-012, Stage 5 owns:

- final material conflict grouping,
- semantic question/subquestion coverage,
- supported/partially supported/unsupported aspect classification,
- final evidence sufficiency.

Overall sufficiency states are:

```text
SUFFICIENT
PARTIALLY_SUFFICIENT
INSUFFICIENT
```

Sufficiency is semantic rather than evidence-count based. Source failure/degradation remains separate from answerability.

### 26. Assembly Status Is Distinct From Evidence Sufficiency

Stage 5 conceptually returns:

```text
ContextAssemblyResult
- assembly_status
- generation_context?
- failure?
```

with:

```text
ASSEMBLED
NOT_APPLICABLE
FAILED
```

A valid empty evidence set may be `ASSEMBLED + INSUFFICIENT`; malformed provenance or inability to construct safe context may be `FAILED`; rejected/clarification-required upstream states are `NOT_APPLICABLE` for normal evidence generation.

### 27. GenerationContext Is the Stage 5 → Stage 6 Contract

Under ADR-013, Stage 5 emits a structured `GenerationContext` containing the material semantics required by generation, including:

```text
query identity + original/resolved query
EvidencePolicy
sufficiency assessment
selected ContextItems with real provenance
relationship/dependency metadata
conflict groups
coverage units
timeline structure when useful
required-source statuses
source failures/degradation
interpretation assumptions
assembly metadata
```

Stage 6 should not require the complete raw Stage 4 retrieval-run graph for normal generation. Selected context items preserve stable lineage references; full traces remain available to evaluation/observability.

### 28. Stage 5 Does Not Initiate New Retrieval in V1

Context assembly does not fetch adjacent chunks or acquire new datastore/web evidence after Stage 4 completion.

Already-gathered parent/neighbor content may be used only if it is already part of the accepted Stage 4 evidence contract.

Changing this boundary requires explicit cross-stage architecture review.

### 29. V1 Context Compression Is Extractive and Provenance-Preserving

Stage 5 may use exact passage selection/extractive trimming with explicit full-versus-extracted extent semantics and source-span lineage.

V1 does not use generative/LLM evidence summarization as source evidence. Any future generated compression must be explicitly marked as derived text and preserve compression/provenance lineage through a reviewed architecture change.

### 30. Stage 6 Owns Generation Prompt Construction

The accepted boundary is:

```text
Stage 5: EvidenceGatheringResult → structured GenerationContext
Stage 6: system/generation instructions + GenerationContext → grounded answer
```

Stage 6 owns system/generation prompt construction, grounding instructions, response-format instructions, final citation-rendering instructions, natural-language answer generation, and user-facing conflict/uncertainty/partial-answer wording.

Stage 5 does not own final prompt construction or user-facing prose.

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

Normal V1 local retrieval executes dense + lexical retrieval, with a structured temporal route when intent/profile requires it.

Dense retrieval uses the captured active SearchRepresentationGeneration. Lexical retrieval uses PostgreSQL FTS plus the bounded literal fallback when necessary. Temporal retrieval searches structured TemporalMentions while preserving multiple mentions, source/content origin, semantic role, precision, certainty, BCE/CE, ranges, and unresolved state.

### Fusion and ranking

Candidate lists are consolidated by canonical `chunk_id` before fusion.

V1 uses RRF because route score domains are heterogeneous. The RRF constant and candidate budgets are configuration, not architectural constants.

Strong temporal profiles may apply a bounded deterministic post-RRF temporal adjustment. A mild document-level diversity penalty may be used as a retrieval-quality safeguard, but final context diversity remains Stage 5.

No learned reranker is present in the initial V1 baseline. Reranking is benchmark-triggered.

### Retrieval result/outcome contract

Stage 3 returns provenance-complete canonical evidence candidates with authoritative source text, identity, provenance/location where available, TemporalMentions, duplicate-lineage signals, route/rank metadata, and capability/degradation state.

Stage 3 distinguishes:

```text
SUCCESS_WITH_CANDIDATES
SUCCESS_NO_CANDIDATES
SUCCESS_DEGRADED
FAILURE
```

A route failure may degrade to other successful routes. Database-wide unavailability, inability to verify authoritative eligibility, incoherent search-generation state, or invalid request state never masquerades as successful no-results retrieval.

Stage 3 does not decide final evidence sufficiency/answerability.

---

## Accepted Stage 4 Orchestration Architecture

### Evidence policy and execution obligations

Stage 4 validates the request and derives immutable local/web source obligations from ADR-001.

For hybrid requests, local and web are independent mandatory bounded execution obligations. Success from one cannot cancel the other's initial execution. Concurrent initial execution is preferred when practical but is not a semantic requirement.

### Query + temporal understanding

Stage 4 coordinates the upstream responsibility accepted in ADR-007. `ResolvedQuery` preserves the original question, resolved references, structured temporal intents, assumptions, unresolved ambiguity, interpretation status, and supported retrieval-profile hints.

Clarification is reserved for material ambiguity that cannot safely be resolved from relevant conversation context. Uncertain history remains uncertain rather than being converted into false exactness.

### Bounded adaptive state machine

The execution plan is explicit but incremental. Initial mandatory source actions are planned deterministically; later actions are appended only from structured outcomes/triggers and within remaining budgets.

Operational retries repeat the same logical request after retryable failures. Evidence-seeking attempts change retrieval strategy and require explicit causal reasons such as no results, recoverable unresolved anchors, over-constrained queries, uncovered subqueries, relevant degradation, or possible-conflict follow-up.

### Stage 4 → Stage 5 handoff

`EvidenceGatheringResult` preserves:

- query/resolution state,
- immutable evidence policy,
- orchestration completion status,
- first-class required-source status,
- per-run causal lineage,
- canonical evidence text,
- typed local/web provenance,
- temporal metadata,
- interpretation assumptions,
- failures/degradation,
- stop reason.

### Web evidence

The Web Retrieval capability is provider-neutral. It returns grounding-capable evidence with external identity, temporal metadata where known, and acquisition/completeness state. Provider-returned extracted or partial text may be valid grounding evidence; inadequate snippets are not silently promoted.

### State and framework boundary

Runtime state is ephemeral for bounded V1 interactive requests. Structured traces survive sufficiently for evaluation/debugging. Durable workflow checkpointing and a mandatory orchestration framework are not V1 requirements.

---

## Accepted Stage 5 Context Assembly Architecture

### Relationship and corroboration

Stage 5 uses the ADR-011 relationship/dependence model. Repeated retrieval, exact duplicates, and derivative families do not inflate independent support. Unknown dependence remains explicit rather than being promoted to independence.

### Conflict, coverage, and sufficiency

Stage 5 uses ADR-012 to group material conflicts, map material question coverage, preserve supported/unsupported aspects, and classify overall evidence sufficiency as sufficient, partially sufficient, or insufficient.

No source-authority or winner-selection policy is introduced.

### Context selection and temporal organization

Stage 5 performs a final utility reassessment across heterogeneous Stage 4 candidates, applies soft diversity without quotas, preserves material conflict sides and coverage under token budget, and orders context according to query semantics rather than universally by date.

Temporal uncertainty and unresolved placement remain explicit.

### Compression and retrieval boundary

V1 allows provenance-preserving extractive trimming only. Stage 5 does not initiate new retrieval or adjacent-chunk fetching after Stage 4 completion.

### Stage 5 → Stage 6 handoff

Stage 5 emits `GenerationContext` under ADR-013. Required-source statuses, failures/degradation, conflicts, coverage, sufficiency, relationship/dependence semantics, selected provenance-complete evidence, and interpretation assumptions remain available to Stage 6 without requiring the full Stage 4 run graph.

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

5. **Agent / Orchestration (Stage 4)**
   - constructs immutable EvidencePolicy,
   - enforces independent mandatory source obligations,
   - coordinates Query + Temporal Understanding,
   - coordinates typed local/web execution,
   - owns bounded incremental planning, operational retries, evidence-seeking adaptations, budgets, and stopping,
   - preserves causal run/source/failure lineage in EvidenceGatheringResult,
   - never owns final evidence sufficiency, semantic corroboration/deduplication, or final conflict grouping.

6. **Local Corpus Retrieval (Stage 3)**
   - searches only selected executable corpora,
   - executes deterministic dense + lexical (+ temporal when appropriate) retrieval,
   - enforces authoritative lifecycle/generation/deletion eligibility,
   - preserves provenance and temporal/duplicate-lineage metadata,
   - performs same-chunk consolidation/RRF and bounded retrieval-level adjustments,
   - fails closed on unverifiable or incoherent eligibility state.

7. **Web Retrieval**
   - executes whenever Web is ON in V1,
   - is provider-neutral at the Stage 4 contract boundary,
   - returns grounding-capable evidence with external provenance and content-completeness semantics,
   - distinguishes event/content temporal constraints from source/publication time,
   - fails independently from local retrieval where practical.

8. **Context Assembly (Stage 5)**
   - consumes `EvidenceGatheringResult`,
   - revalidates legal evidence/provenance,
   - owns final relationship/deduplication/corroboration semantics,
   - groups material conflicts,
   - maps question coverage and final evidence sufficiency,
   - applies final utility/diversity/temporal ordering/token budgeting,
   - performs provenance-preserving extractive selection,
   - emits structured `GenerationContext`,
   - performs no new retrieval in V1.

9. **Grounded Generation (Stage 6)**
   - consumes `GenerationContext`,
   - constructs system/generation prompts and grounding instructions,
   - generates supported full/partial/insufficient responses,
   - exposes conflicts/uncertainty and retrieval limitations,
   - renders final citations,
   - owns user-facing response formatting.

10. **Evaluation + Observability**
   - measures component/end-to-end quality,
   - traces source configuration, ingestion publication, retrieval state/ranking, orchestration execution, context-assembly decisions, and generation outputs,
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
→ Construct immutable EvidencePolicy (local required)
→ Query + Temporal Understanding
→ Structured LocalRetrievalRequest
→ Dense + Lexical (+ Temporal when appropriate)
→ candidate eligibility
→ same-chunk consolidation + RRF
→ bounded retrieval adjustments
→ final authoritative current-state validation/backfill
→ EvidenceGatheringResult
→ Stage 5 relationship/conflict/coverage/sufficiency/context assembly
→ GenerationContext
→ Stage 6 prompt construction + grounded generation
→ Answer + Local Citations
```

### Hybrid query

```text
Query + Selected Corpora + Web ON
→ Construct immutable EvidencePolicy (local + web required)
→ Query + Temporal Understanding
→ Stage 4 executes both mandatory source obligations
→ optional bounded retry/reformulation/decomposition/recovery
→ EvidenceGatheringResult with required-source + per-run lineage
→ Stage 5 relationship/conflict/coverage/sufficiency/context assembly
→ GenerationContext with selected evidence + source failure/degradation state
→ Stage 6 prompt construction + grounded generation
→ Answer + Local/Web Citations
```

### Web-only query

```text
Query + Web ON + No Corpus
→ Construct immutable EvidencePolicy (web required)
→ Query + Temporal Understanding
→ Provider-neutral Web Retrieval
→ grounding-capable web evidence + acquisition/provenance metadata
→ EvidenceGatheringResult
→ Stage 5 evidence assessment/context assembly
→ GenerationContext
→ Stage 6 prompt construction + grounded generation
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
- no learned reranker initially,
- bounded interactive Stage 4 requests with ephemeral runtime state,
- no mandatory durable orchestration workflow engine in V1,
- bounded Stage 5 candidate sets,
- no generative evidence summarization in Stage 5 V1,
- no Stage 5 new-retrieval/adjacent-fetch behavior in V1.

These assumptions constrain later designs without requiring premature distributed infrastructure.

---

## Implementation-Time Validation Requirements

### Stage 3

Stage 3 implementation must validate retrieval quality, temporal correctness, corpus/eligibility isolation, provenance/lineage, cutover races, deterministic ordering under fixed state/config, and representative latency. Exact candidate budgets/RRF constants/temporal weights remain configuration.

### Stage 4

Stage 4 implementation must validate zero source-policy violations, correct mandatory-source statuses, interpretation/clarification behavior, intent-preserving transformations, bounded execution/termination, graceful partial success, malformed tool-response handling, grounding-capable web evidence/completeness state, structured causal trace completeness, latency/token/search cost, and no final conflict/sufficiency adjudication leakage into Stage 4.

### Stage 5

Stage 5 implementation must validate at least:

- zero source-boundary violations,
- effectively complete selected-context provenance retention,
- false independent-corroboration rate,
- exact/derivative/unknown-dependence handling,
- conflict preservation and materiality classification,
- coverage and sufficiency classification accuracy,
- supported partial-answer guidance,
- context precision and coverage/recall,
- critical-evidence omission rate,
- duplicate-token reduction without provenance loss,
- temporal ordering/uncertainty correctness,
- correct required-source failure/degradation propagation,
- policy-violating/unsupported evidence exclusion,
- context budget efficiency and safe budget-exhaustion behavior,
- assembly latency and cost where applicable.

Exact Stage 5 token budgets, ranking weights, relationship/conflict/coverage classifiers, and model assistance choices remain implementation/evaluation configuration.

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
- concrete orchestration framework adoption beyond the accepted framework-neutral semantic model,
- reasoning model/provider,
- concrete web-search/content-acquisition provider integration,
- exact orchestration attempt/rewrite/subquery ceilings,
- exact trace persistence backend/retention,
- exact Stage 5 token budgets and selection weights,
- concrete derivative/conflict/coverage classification mechanisms,
- learned/model-based Stage 5 reranking pending evaluation,
- generative evidence compression unless separately reviewed,
- source-authority/trust ranking,
- generation model/provider,
- concrete Stage 6 prompt architecture details within the accepted Stage 6 ownership boundary,
- exact external API schema,
- caching,
- artifact retention/garbage collection,
- production queue/topology,
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
- `ADR-009-v1-bounded-orchestration-execution-model.md` — Stage 4 uses a bounded adaptive application state machine with deterministic control, immutable EvidencePolicy, explicit budgets/stopping, and bounded semantic reasoning.
- `ADR-010-evidence-gathering-and-web-retrieval-contract.md` — Stage 4 emits EvidenceGatheringResult with required-source/run lineage and typed provenance through a provider-neutral grounding-capable web boundary.
- `ADR-011-evidence-relationship-and-corroboration-semantics.md` — Stage 5 distinguishes identity, exact duplicate, derivative, independent, and unknown dependence so copied/repeated evidence cannot inflate corroboration.
- `ADR-012-conflict-coverage-and-sufficiency-model.md` — Stage 5 owns material conflict grouping, semantic coverage, and semantic sufficiency while keeping conflict orthogonal to answerability and source authority out of V1.
- `ADR-013-generation-context-and-stage-5-stage-6-boundary.md` — Stage 5 emits structured GenerationContext; Stage 6 owns generation prompt construction, grounded answer synthesis, and final citation rendering.

---

## Stage Alignment

- **Stage 1** defines the behavioral contract and global evidence invariants.
- **Stage 2** owns ingestion, corpus/document lifecycle, immutable versions/generations, provenance capture, temporal metadata extraction, search representation generation, publication, reprocessing, and deletion.
- **Stage 3** owns deterministic query-time local retrieval, selected-corpus enforcement, authoritative eligibility/cutover handling, dense/lexical/temporal candidate retrieval, same-chunk consolidation, RRF/bounded retrieval ranking, and retrieval-specific failures/degradation.
- **Stage 4** owns Query + Temporal Understanding coordination, immutable EvidencePolicy enforcement, bounded adaptive orchestration, independent mandatory local/web execution, provider-neutral web retrieval coordination, bounded replanning/reformulation/decomposition, budgets/stopping, structured traces, and the EvidenceGatheringResult handoff. It does not own final evidence sufficiency, semantic deduplication/corroboration, or final conflict grouping.
- **Stage 5** owns final evidence-policy/provenance revalidation, semantic relationship/deduplication/corroboration, material conflict grouping, semantic coverage, final evidence sufficiency, context diversity/ordering/token budgeting, extractive selection, and the `GenerationContext` handoff. It does not perform new retrieval in V1 or construct the final generation prompt.
- **Stage 6** owns system/generation prompt construction, grounded response generation, user-facing conflict/uncertainty/partial-answer wording, final response formatting, and citation rendering from `GenerationContext`.
- **Stage 7** formalizes evaluation including accepted Stage 3 retrieval/race/temporal benchmarks, Stage 4 policy/trajectory/rewrite/retry/stopping evaluation, and Stage 5 relationship/conflict/coverage/sufficiency/context-selection evaluation.
- **Stage 8** formalizes end-to-end tracing and operational observability including Stage 3 state/ranking traces, Stage 4 structured orchestration traces, and Stage 5 structured assembly decisions.
- **Stage 9** adds reliability/guardrails, including stale evidence, timeout, loop/budget enforcement, tool-contract validation, and retrieved-content/prompt-injection protections, without weakening evidence boundaries or data/control separation.
- **Stage 10** defines production serving/scaling and may evolve worker/search/orchestration/context/generation deployment topology, durable workflows, queues, and horizontal scaling while preserving accepted semantic boundaries.
