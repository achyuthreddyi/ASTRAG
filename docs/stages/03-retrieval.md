# Stage 3: Retrieval Pipeline

## Status

**Implementation Ready.**

Orchestrator review is complete. ADR-005, ADR-006, ADR-007, and ADR-008 are accepted, and the corresponding project-wide invariants are recorded in `docs/architecture/architecture.md`.

## Objective

Define how ASTRAG converts an authorized local retrieval request into a ranked set of eligible, provenance-complete local evidence candidates for later orchestration and context assembly.

Stage 3 owns deterministic query-time local retrieval across user-selected corpora. It consumes the canonical/searchable representations produced by Stage 2 and preserves the evidence-boundary, publication, generation, provenance, temporal-uncertainty, duplicate-lineage, and deletion invariants accepted by Stage 1 and Stage 2.

Historical and temporal QA remain the primary retrieval optimization target.

## Scope

Stage 3 defines:

- the structured local retrieval request and result contracts,
- selected-corpus enforcement,
- authoritative evidence eligibility validation,
- request/cutover consistency,
- dense retrieval,
- lexical retrieval and bounded exact-token/phrase fallback,
- temporal candidate retrieval and ranking signals,
- hybrid candidate generation and Reciprocal Rank Fusion,
- same-chunk retrieval-hit consolidation,
- retrieval profiles and candidate budgets,
- light document-level diversity control,
- degraded capability behavior,
- retrieval scoring/provenance metadata,
- retrieval failure semantics,
- retrieval observability,
- retrieval evaluation,
- V1 performance benchmarks and revisit triggers for ANN/reranking/search infrastructure.

## Non-Goals

Stage 3 does not own:

- parsing, normalization, chunking, temporal extraction, or representation generation,
- document/version/publication lifecycle,
- raw conversation-history interpretation,
- autonomous conversational reference resolution,
- autonomous LLM query rewriting,
- agentic alias expansion or multi-query loops,
- cross-tool/source orchestration,
- web retrieval,
- final evidence sufficiency assessment,
- semantic contradiction/conflict resolution,
- final semantic/source-level deduplication or corroboration semantics,
- final context diversity/source grouping,
- final context token budgeting,
- final chronological context ordering,
- final citation rendering,
- answer generation,
- ANN as an initial V1 requirement,
- a learned reranker in the initial V1 baseline,
- a dedicated vector database or lexical search engine in V1.

Stage 4 coordinates Query + Temporal Understanding, broader orchestration, web/local execution, multi-step strategies, and replanning. Stage 5 owns final evidence combination, semantic duplicate/corroboration handling, context diversity/ordering, token budgeting, sufficiency assessment, and final context selection. Stage 6 owns grounded generation and citation rendering.

## Requirements

### 1. Evidence-boundary correctness

Every returned local candidate must satisfy all applicable authoritative constraints:

- `corpus_id` is in the executable selected corpus scope,
- the logical document is query-visible and not deleting/deleted,
- `document_version_id` matches the active published source version,
- `processing_generation_id` matches the active published processed chunk set,
- `search_representation_generation_id` matches the coherent request search space,
- publication/readiness state permits search visibility,
- mandatory lineage is valid.

No result from an unselected corpus, deleted document, stale DocumentVersion, stale ProcessingGeneration, inactive/mixed SearchRepresentationGeneration, unpublished replacement, partial ingestion state, or stale derived index row may appear in Stage 3 output.

Target unauthorized/ineligible leakage rate: **0**.

### 2. Defense-in-depth eligibility enforcement

Eligibility is structural and layered:

```text
search-time hard predicates
        ↓
candidate eligibility validation
        ↓
same-chunk consolidation + fusion / ranking
        ↓
final authoritative output-time validation
        ↓
backfill from lower-ranked validated candidates
```

Search/index membership alone is never evidence authority.

If authoritative eligibility cannot be established reliably, Stage 3 fails closed.

### 3. Concurrent publication/deletion/generation consistency

Per ADR-008, each retrieval captures a request-scoped retrieval state identity including at least the active SearchRepresentationGeneration, retrieval configuration identity, executable corpus scope, and a traceable database snapshot/eligibility epoch or equivalent.

All candidate-generation routes use the captured SearchRepresentationGeneration. One result may never mix incompatible SearchRepresentationGenerations.

Immediately before output, candidates are revalidated against current committed authoritative lifecycle state. Candidates that became deleted, moved out of scope, superseded by a new DocumentVersion/ProcessingGeneration, or otherwise ineligible are rejected and may be backfilled.

If the globally active SearchRepresentationGeneration changes after candidate generation begins, the request search space is invalidated. Stage 3 may perform a small bounded transparent restart against the new generation when the deadline permits. Otherwise it fails closed with a stable state-change reason such as `SEARCH_GENERATION_CHANGED` or `ELIGIBILITY_STATE_CHANGED`.

Publication/deletion/corpus-move churn need not restart the entire request when final validation can safely reject affected candidates and backfill coherent eligible results.

### 4. Structured retrieval input

Stage 3 consumes a structured request rather than raw conversation history:

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

Query + Temporal Understanding is an upstream logical responsibility coordinated by Stage 4. It resolves relevant conversational references and temporal language where safe, preserves uncertainty/assumptions, and produces a deterministic request for Stage 3.

Stage 3 may perform deterministic search normalization but does not autonomously invoke an LLM to paraphrase the query or create agentic multi-query loops.

### 5. Temporal intent representation

A request may carry multiple independent `TemporalIntent` values.

Each intent conceptually preserves:

```text
type / relation
original_expression
normalized bounds or anchor when safely resolved
precision
certainty
calendar / era semantics
query semantic role
resolution status
```

Supported V1 shapes include:

- exact point/date,
- year/period point,
- range overlap,
- before,
- after,
- approximate/proximity (`AROUND`),
- recurring month/day semantics such as `on this day`,
- BCE/CE comparable forms while preserving original wording.

Current-date-relative query expressions are resolved upstream. Unresolved anchors remain explicit; Stage 3 degrades to meaningful semantic/lexical retrieval when possible and fails rather than inventing an anchor when the request is unusable.

### 6. Temporal route predicates versus hard global exclusion

Temporal metadata is not a universal hard evidence filter.

The temporal candidate route may use strict temporal predicates to generate candidates matching an intent. Those route-local predicates do not automatically exclude dense/lexical candidates from the fused pool.

Dense/lexical evidence without temporal mentions, with zero mentions, or with degraded temporal extraction remains eligible.

Cross-route hard temporal exclusion is permitted only for explicit typed constraints whose semantics genuinely require exclusion, such as an explicit source/publication-time constraint. Such constraints must be represented in the request, traced, and evaluated separately from ordinary temporal interpretation.

### 7. Dense retrieval

Dense retrieval executes for every normal local request unless the dense path fails.

Initial V1 policy:

- exact vector search against PostgreSQL/pgvector-style storage,
- query embedding generation inside the dense retriever,
- embedding generation using the request's captured active SearchRepresentationGeneration,
- compatibility validation before vector search,
- similarity metric owned by SearchRepresentationGeneration configuration,
- selected-corpus and generation predicates applied during search.

Exact vector search is the baseline, not a permanent requirement. ANN is reconsidered only when representative implementation benchmarks show exact search misses agreed latency targets.

### 8. Lexical retrieval

Lexical retrieval executes for every normal local request unless the lexical path fails.

PostgreSQL full-text search is the primary V1 lexical mechanism. The lexical query is derived deterministically from `retrieval_query` while preserving `original_question` in execution metadata.

The implementation must preserve useful literal behavior for:

- quoted phrases,
- proper names,
- rare historical entities,
- dates and numbers,
- acronyms/codes,
- uncommon identifier-like tokens.

When FTS normalization produces an empty/weak representation or materially loses critical literal structure, Stage 3 uses a **bounded deterministic exact-token/phrase fallback inside PostgreSQL**. Exact tokenizer/operators/indexes are implementation/evaluation choices.

This fallback is not broad semantic alias expansion. Autonomous synonym/alias expansion remains upstream/Stage 4 strategy.

### 9. Temporal candidate route

Strongly temporal profiles may execute an additional structured temporal candidate route alongside dense and lexical retrieval.

Stage 3 decides route activation from `TemporalIntent[]` and the retrieval profile. Callers do not supply low-level route flags.

The temporal route:

- searches structured Stage 2 TemporalMentions,
- obeys selected-corpus/publication/generation/deletion constraints,
- evaluates multiple mentions per chunk,
- supports point/range/before/after/proximity/recurrence semantics,
- preserves precision, certainty, origin, semantic role, and unresolved state,
- does not fabricate normalized values for unresolved expressions.

### 10. Temporal matching and ranking

Temporal ranking is explainable and not a fictitious calibrated probability.

Signals may include:

```text
matched_mentions[]
relation / overlap type
precision compatibility
certainty
origin
semantic role
temporal distance / proximity
temporal route rank
```

For event-oriented queries, event-time-like mentions may receive a configurable ranking preference over relevant unknown-role/source-metadata mentions. For source/publication-date queries, the preference may reverse.

Approximate periods use overlap/proximity plus precision/certainty compatibility rather than exact-date coercion. `circa 1200 BCE` and `early 5th century` remain approximate evidence.

When multiple mentions match one chunk, the strongest match may drive route ranking while all matching mentions remain exposed downstream.

### 11. Hybrid execution and fusion

Dense and lexical execute by default. Strongly temporal requests may additionally execute the temporal route.

Route lists are first consolidated by canonical `chunk_id`. If the same chunk appears in multiple routes, Stage 3 emits one candidate with all route signals.

Different chunks remain distinct even when text/hashes indicate duplicate content. Stage 5 owns semantic/source-level duplicate and corroboration semantics.

V1 uses Reciprocal Rank Fusion (RRF):

```text
RRF_score(chunk) = Σ route_contribution(rank_in_route)
```

Initial route contributions are equal. The exact RRF constant is versioned configuration and evaluation-tuned.

RRF score is a ranking signal, not a relevance probability.

### 12. Bounded temporal post-fusion adjustment

Strong temporal profiles may apply a small deterministic temporal adjustment after RRF. The adjustment must be bounded and traceable so temporal relevance is not double-counted without limit.

Temporal adjustment weights are evaluation-tuned profile configuration.

### 13. Retrieval profiles

Supported V1 profiles:

- `FACT_LOOKUP`
- `TEMPORAL_POINT`
- `TEMPORAL_RANGE`
- `TIMELINE`
- `BROAD`

Profiles control internal candidate budgets, temporal-route activation, temporal-adjustment strength, diversity behavior, and output breadth. Callers do not micromanage RRF constants, route weights, or raw candidate counts.

If `retrieval_profile` is omitted, Stage 3 derives a deterministic default from structured intent:

- point/recurring month-day intent → `TEMPORAL_POINT`,
- range/before/after/proximity intent → closest supported temporal profile, normally `TEMPORAL_RANGE`,
- no temporal intent → `FACT_LOOKUP` unless upstream explicitly selected `TIMELINE` or `BROAD`.

An explicitly unknown profile is `INVALID_RETRIEVAL_REQUEST`; Stage 3 does not silently downgrade it to `FACT_LOOKUP`.

`TIMELINE` uses broader candidate/output budgets and may use a weaker document-diversity penalty. Final chronological ordering remains Stage 5.

### 14. Candidate budgets

Stage 3 distinguishes:

```text
dense_candidate_limit
lexical_candidate_limit
temporal_candidate_limit
fusion_candidate_limit
reranker_input_limit   # reserved for future use
retrieval_output_limit
```

Exact values are versioned configuration and evaluation-tuned.

Stage 3 intentionally returns a moderately broad candidate set for Stage 5, not final prompt-ready context.

### 15. Multi-corpus union semantics

Selected corpora use union semantics. V1 does not reserve per-corpus quotas; candidates compete globally by relevance within the permitted scope.

Invalid/deleted requested corpus IDs are omitted from executable scope and recorded as degraded scope metadata. If no valid selected corpus remains, Stage 3 returns `FAILURE / NO_EXECUTABLE_CORPUS_SCOPE`.

### 16. Document-level diversity

Stage 3 may apply a mild configurable rank penalty after a configurable number of highly ranked chunks from one document.

This is a retrieval-quality safeguard, not Stage 5 context diversity or corroboration logic. It must remain weak, configurable, traceable, and evaluated on/off. Timeline profiles may use a weaker penalty.

Automatic neighboring-chunk expansion is not part of the default V1 retrieval architecture.

### 17. No initial reranker

V1 begins without a cross-encoder, LLM, or learned reranker.

Reranking is reconsidered when evaluation shows relevant evidence consistently appears inside the fused candidate pool but ranks too poorly to fit Stage 5's practical candidate budget.

### 18. Relevance and sufficiency semantics

Stage 3 does not use one universal absolute relevance threshold initially and does not decide answerability.

It reports candidate and execution state. Final evidence sufficiency belongs downstream.

Stage 3 therefore does not infer `NO_RELEVANT_RESULTS` solely from a low RRF/fusion score.

### 19. Degraded Stage 2 capabilities

`TEMPORAL = READY` with zero temporal mentions and `TEMPORAL = DEGRADED` are distinct states.

A temporal-extraction failure does not make an otherwise valid dense/lexical chunk ineligible. Missing optional page/section location metadata similarly does not invalidate evidence. Capability degradation is preserved downstream.

### 20. Retrieval configuration identity

Every execution records `retrieval_config_version` or equivalent stable identity covering profile/ranking configuration relevant to reproducibility.

V1 does not introduce a first-class immutable `RetrievalGeneration` lifecycle entity.

## Assumptions

- Stage 2 is Implementation Ready and its persisted contract is authoritative.
- V1 is single-tenant with one primary user and low concurrency.
- V1 scale is hundreds to thousands of documents and approximately up to one million chunks.
- PostgreSQL is the accepted V1 relational/search foundation.
- pgvector-style integrated vector search and PostgreSQL FTS remain the V1 search mechanisms.
- one SearchRepresentationGeneration is globally active at a time,
- dense and lexical representations are mandatory for query-visible evidence,
- temporal and provenance-location capabilities may be degraded,
- Query + Temporal Understanding can produce a resolved query and structured temporal intent or explicitly preserve unresolved state,
- exact budgets/weights/latency targets are established by implementation evaluation.

## Key Design Decisions

1. Stage 3 consumes a structured `LocalRetrievalRequest`, not raw conversation history.
2. Query + Temporal Understanding is upstream and coordinated by Stage 4.
3. Dense and lexical retrieval execute by default in V1.
4. Strongly temporal requests may additionally execute a structured temporal candidate route.
5. PostgreSQL FTS has a bounded literal fallback contract for FTS-poor queries.
6. V1 starts with exact PostgreSQL vector search; ANN is benchmark-triggered.
7. Query embeddings are generated inside the dense retriever using the captured SearchRepresentationGeneration.
8. Dense/lexical/temporal routes use RRF rather than raw-score addition.
9. Same canonical chunk hits are consolidated while all route signals are preserved.
10. Strong temporal profiles may use a bounded post-RRF temporal adjustment.
11. Temporal route predicates do not become global evidence filters by default.
12. Temporal uncertainty/origin/role/precision/ranges/multiple mentions remain visible.
13. Optional temporal degradation never silently removes valid semantic/lexical evidence.
14. No reranker is included in the initial V1 baseline.
15. Candidate budgets are separate internal configuration dimensions.
16. Multi-corpus retrieval uses global union semantics without per-corpus quotas.
17. Stage 3 may apply only mild document-level diversity adjustment.
18. Authoritative eligibility uses layered validation and final output-time revalidation.
19. One result never mixes incompatible SearchRepresentationGenerations; cutover invalidation restarts boundedly or fails closed.
20. Stage 3 does not own final sufficiency, conflict semantics, corroboration, or chronology.
21. Retrieval outcomes/degradation/failures are structured and machine-readable.
22. Retrieval configuration/state identities are traceable for reproducibility.

## Proposed Architecture

```text
Resolved Question
+ Selected Corpora
+ TemporalIntent[]
+ Supported/Derived Retrieval Profile
        ↓
Capture retrieval_config_version
+ active SearchRepresentationGeneration
+ request retrieval-state identity
        ↓
Validate Request + Resolve Executable Corpus Scope
        ↓
┌─────────────────────────────────────────────┐
│ Dense Retrieval                            │
│ Lexical Retrieval + bounded literal fallback│
│ Temporal Retrieval (when profile requires) │
└─────────────────────────────────────────────┘
        ↓
Candidate Eligibility Validation
        ↓
Same-Chunk Signal Consolidation
        ↓
Reciprocal Rank Fusion
        ↓
Bounded Temporal Adjustment
        ↓
Light Document Diversity Adjustment
        ↓
Final Current-State Eligibility Validation
        ↓
Backfill / bounded restart on SRG cutover
        ↓
LocalRetrievalResult
        ↓
Stage 4 / Stage 5
```

## Components

### Query + Temporal Understanding (upstream contract)

Coordinated by Stage 4. Resolves conversational references and query-time temporal language where safe, preserves assumptions/uncertainty, and produces structured retrieval intent. It is not part of core Stage 3 retrieval execution.

### Local Retrieval Coordinator

Validates request/scope, captures request state/config identities, derives omitted profiles deterministically, executes routes, consolidates/fuses/ranks, coordinates final validation/backfill, and builds `LocalRetrievalResult`.

It does not perform agentic multi-step reasoning.

### Dense Retriever

Generates compatible query embeddings and performs exact V1 vector search under selected-corpus and request-generation predicates.

### Lexical Retriever

Uses PostgreSQL FTS plus the bounded deterministic literal fallback when required. It returns lexical ranks/signals under the same corpus/eligibility constraints.

### Temporal Retriever

Searches all applicable structured TemporalMentions for temporal profiles and returns explainable temporal match details/ranks without fabricating precision.

### Eligibility Validator

Enforces selected corpus, document lifecycle, active version, active ProcessingGeneration, coherent SearchRepresentationGeneration, readiness, deletion/tombstone, and mandatory lineage constraints.

Failure to perform authoritative validation reliably fails local retrieval closed.

### Candidate Consolidator / Fusion

Collapses repeated route hits for the same `chunk_id`, preserves route signals, performs RRF, and exposes fusion rank/score.

### Temporal Rank Adjuster

Applies bounded deterministic temporal adjustment for strongly temporal profiles.

### Document Diversity Adjuster

Applies a mild configurable same-document rank penalty without performing Stage 5 context/corroboration logic.

### Retrieval Result Builder

Produces the immutable result envelope with canonical evidence, provenance, temporal metadata, duplicate lineage, ranking signals, degradation/failure details, scope warnings, and execution/state metadata.

## Data Flow

### Standard fact lookup

```text
LocalRetrievalRequest
→ validate/derive profile/scope
→ capture request state
→ Dense + Lexical
→ candidate eligibility
→ same-chunk consolidation
→ RRF
→ light diversity
→ final current-state eligibility + backfill
→ LocalRetrievalResult
```

### Temporal point/range query

```text
LocalRetrievalRequest + TemporalIntent[]
→ Dense + Lexical + Temporal Route
→ candidate eligibility
→ same-chunk consolidation
→ RRF
→ bounded temporal adjustment
→ light diversity
→ final current-state eligibility + backfill
→ LocalRetrievalResult
```

### Search-generation cutover during retrieval

```text
candidate generation under SRG-A
→ global cutover to SRG-B
→ final validation detects incompatible search-space change
→ bounded restart under SRG-B if deadline permits
   OR fail closed with SEARCH_GENERATION_CHANGED
```

### Degraded temporal capability

```text
Temporal query
→ Dense + Lexical remain available
→ temporal route/documents may be degraded
→ valid semantic/lexical candidates remain eligible
→ LocalRetrievalResult carries degradation metadata
```

### Partial route failure

```text
Dense fails
Lexical + Temporal succeed
→ continue with usable routes
→ SUCCESS_DEGRADED
→ candidates + path failure details
```

## Interfaces / Contracts

### LocalRetrievalRequest

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

Only known typed metadata constraints are accepted. Arbitrary SQL-like filters are rejected.

### TemporalIntent

```text
TemporalIntent
- relation / type
- original_expression
- normalized_start / normalized_end / anchor where available
- precision
- certainty
- era / calendar semantics
- query_semantic_role
- resolution_status
```

Multiple intents are allowed.

### LocalRetrievalResult

```text
LocalRetrievalResult
- query_id
- status
- execution_metadata
- degradation_details[]
- scope_warnings[]
- candidates[]
```

### LocalEvidenceCandidate

```text
LocalEvidenceCandidate
- corpus_id
- document_id
- document_version_id
- processing_generation_id
- search_representation_generation_id
- chunk_id

- source_text
- provenance
- temporal_mentions[]
- duplicate_lineage

- retrieval_routes[]
- dense_signal
- lexical_signal
- temporal_match
- fusion_score
- fusion_rank
- final_stage3_rank

- capability / degradation metadata
```

`source_text` is always authoritative canonical evidence text, never contextualized embedding text or rewritten query text.

Duplicate-lineage values remain separate from provenance and do not cause Stage 3 to collapse distinct canonical chunks.

### Retrieval execution metadata

Preserve at least:

```text
query_id
original_question
retrieval_query
selected/executable/invalid corpus scope
retrieval profile + derivation source
TemporalIntent interpretation
captured SearchRepresentationGeneration
retrieval state / snapshot / eligibility epoch identity where available
retrieval_config_version
routes executed
route candidate counts
filters / typed constraints
lexical fallback activation
fusion configuration identity
eligibility rejection reasons
state-change/restart details
latency by phase
```

## Retrieval Outcome Semantics

Top-level status values:

```text
SUCCESS_WITH_CANDIDATES
SUCCESS_NO_CANDIDATES
SUCCESS_DEGRADED
FAILURE
```

`SUCCESS_DEGRADED` means a configured/required route or requested scope failed but usable retrieval completed. It may contain zero candidates if the remaining successful paths found nothing.

Stage 3 does not equate low ranking scores with insufficient evidence.

## Failure Handling

Stable reason codes include at least:

```text
DATABASE_UNAVAILABLE
QUERY_EMBEDDING_FAILED
EMBEDDING_GENERATION_INCOMPATIBLE
VECTOR_SEARCH_FAILED
LEXICAL_SEARCH_FAILED
TEMPORAL_SEARCH_FAILED
ELIGIBILITY_VALIDATION_FAILED
ELIGIBILITY_STATE_CHANGED
SEARCH_GENERATION_CHANGED
REQUEST_DEADLINE_EXCEEDED
INVALID_RETRIEVAL_REQUEST
NO_EXECUTABLE_CORPUS_SCOPE
MALFORMED_CANDIDATE_METADATA
```

Human-readable detail is separate.

### Invalid request

Malformed temporal intent, explicitly unknown retrieval profile, unsupported typed constraint, invalid structure, or other contract violation fails before search.

### Invalid corpus IDs

Invalid/deleted requested corpora are excluded from executable scope and traced as degraded scope. No valid selected corpus yields `FAILURE / NO_EXECUTABLE_CORPUS_SCOPE`.

### Query embedding failure

Dense may fail independently. If lexical/temporal routes remain usable, return `SUCCESS_DEGRADED`.

Embedding-provider failure remains distinguishable from vector-search failure.

### Embedding generation incompatibility

Incompatible query embedding/search generation is a correctness/configuration failure, not ordinary degradation.

### Lexical failure

If dense and/or temporal remain usable, return degraded results. Failure of the optional bounded literal fallback is traced separately if primary FTS still executed.

### Temporal route failure

If the selected profile does not require the route, nonexecution is not degradation. Required-route failure may degrade to dense/lexical evidence.

### Dense and lexical both fail

Temporal-only evidence may be returned only when the request is explicitly temporal and the temporal route can produce semantically meaningful candidates. Otherwise local retrieval fails rather than treating date overlap alone as generic relevance.

### Eligibility validation / state-change failure

If authoritative eligibility cannot be determined, fail closed.

Individual stale/ineligible candidates are rejected and traced. State changes that invalidate the coherent request search space follow ADR-008 bounded restart/fail-closed behavior.

### PostgreSQL failure

Database-wide unavailability is `FAILURE`, never `SUCCESS_NO_CANDIDATES`.

### Timeouts

One route may time out and degrade to successful routes. Overall deadline expiry before coherent usable output yields `FAILURE / REQUEST_DEADLINE_EXCEEDED`.

### Retry boundary

Stage 3 may perform small bounded infrastructure retries and the bounded state-change restart defined by ADR-008. Query rewriting, alternate-query generation, broader/narrower strategy retries, and multi-step evidence-seeking loops belong to Stage 4.

## Scalability

V1 targets:

- hundreds to thousands of documents,
- approximately up to one million chunks,
- one primary user,
- low concurrency,
- PostgreSQL + integrated vector/FTS search.

The design intentionally avoids dedicated vector/search infrastructure initially.

Exact vector search, FTS + bounded literal fallback, temporal joins/indexes, final validation, and backfill must be benchmarked at representative scale.

## Latency / Throughput Requirements

Stage 3 uses a benchmark-first latency policy rather than inventing a hardware-independent number before implementation.

Measure from the first implementation:

- query-embedding latency,
- exact dense-search latency,
- lexical FTS latency,
- lexical fallback latency/activation rate,
- temporal-search latency,
- eligibility-validation latency,
- state-change restart rate/cost,
- fusion/ranking latency,
- total retrieval latency,
- candidate counts by route/phase.

ANN is reconsidered when exact vector search fails established representative latency targets. Dedicated lexical/search infrastructure is reconsidered only if PostgreSQL evaluation misses quality/performance requirements under ADR-004 revisit triggers.

## Alternatives Considered

### Dense-only retrieval

Rejected because rare names, exact phrases, dates, numbers, and historical entities benefit materially from lexical retrieval.

### Lexical-only retrieval

Rejected because semantic paraphrase retrieval is a core capability.

### Query classifier choosing dense versus lexical

Deferred. Always-on routes provide a deterministic evaluation baseline and avoid another classifier failure mode.

### PostgreSQL FTS with no literal fallback contract

Rejected because critical historical literal forms must remain retrievable/testable when FTS normalization weakens them.

### Raw-score weighted fusion

Rejected because route scores are heterogeneous and uncalibrated.

### Learned fusion

Deferred until sufficient labeled retrieval data exists.

### ANN as initial requirement

Deferred until exact-search benchmarks require it.

### Initial cross-encoder/LLM reranker

Deferred until ranking rather than recall is demonstrated to be the limiting factor.

### Hard temporal filtering across the fused pool by default

Rejected because it can destroy recall under missing/degraded temporal metadata.

### One long-lived repeatable-read snapshot with no output-time current-state validation

Rejected because deletion/publication changes committed during retrieval could otherwise produce stale output.

### Fresh unrelated reads with no captured search state

Rejected because one result could mix incompatible SearchRepresentationGenerations.

### Per-corpus quotas

Rejected because Stage 1 specifies union semantics.

### Automatic neighbor expansion

Deferred to Stage 5 unless retrieval evaluation demonstrates a Stage 3 need.

### Broad alias/query expansion inside Stage 3

Rejected as a Stage 3 responsibility. Stage 4/upstream may own controlled expansion strategies.

## Dependencies

### Stage 1

Provides evidence-boundary, grounding, union-semantics, insufficient-evidence, conflict-preservation, duplicate-evidence, and temporal behavior requirements.

### Stage 2

Provides canonical chunks, active publication/version/processing-generation selection, globally active SearchRepresentationGeneration, dense/lexical representations, TemporalMentions, provenance, capability/degradation state, deletion eligibility, and duplicate-lineage signals.

### Stage 4

Coordinates Query + Temporal Understanding, produces/coordinates structured retrieval requests, selects supported profiles where appropriate, runs web + local orchestration, and owns multi-step query strategies/replanning. It cannot bypass Stage 3 corpus/eligibility invariants.

### Stage 5

Consumes broad Stage 3 candidates and owns final context selection, semantic deduplication/corroboration, token budgeting, source grouping/diversity, evidence sufficiency, and chronological ordering.

### Stage 6

Consumes provenance-preserving context and owns grounded generation/citation rendering.

### Stage 7

Owns durable evaluation infrastructure/datasets while incorporating Stage 3 retrieval, temporal, boundary, race, and benchmark metrics.

### Stage 8

Consumes Stage 3 execution/state traces for debugging and observability.

### Stage 9

Builds reliability/guardrails around retrieval failures, stale evidence, timeouts, malicious retrieved text/prompt injection, and unsupported-answer behavior without weakening Stage 3's fail-closed evidence boundary.

### Stage 10

May revisit deployment/search infrastructure if concurrency/latency/scale exceeds V1 assumptions.

## Evaluation Criteria

### Ranking/retrieval metrics

Measure at least:

- Recall@K,
- MRR,
- nDCG@K,
- Hit Rate@K,
- Precision@K where useful,
- temporal Recall@K,
- temporal ranking correctness.

### Mandatory ablations

Compare at minimum:

```text
dense only
lexical only
dense + lexical
dense + lexical + temporal
```

Also compare bounded lexical fallback enabled/disabled for FTS-poor literal queries and document-diversity adjustment enabled/disabled.

### Temporal test classes

Include:

- exact date,
- year,
- range,
- before,
- after,
- approximate period,
- early/mid/late century-style approximation,
- BCE/CE,
- recurring month/day,
- multiple temporal mentions,
- no temporal metadata,
- temporal extraction degraded,
- source-date versus content-event-date distinction,
- timeline/broad-period retrieval,
- unresolved relative temporal evidence.

### Evidence-boundary tests

Mandatory negative cases:

- unselected corpus,
- deleted document,
- old DocumentVersion,
- old ProcessingGeneration,
- inactive SearchRepresentationGeneration,
- stale index entry,
- document moved between corpora,
- unpublished replacement/partial ingestion state.

Required result: **zero unauthorized/ineligible evidence leakage**.

### Concurrency / cutover tests

Exercise retrieval concurrently with:

- deletion/tombstoning,
- corpus move,
- DocumentVersion publication,
- ProcessingGeneration cutover,
- global SearchRepresentationGeneration cutover.

Verify no stale output, no mixed-generation result, deterministic backfill/restart/failure behavior, and correct state-change tracing.

### Capability-degradation tests

Explicitly distinguish:

```text
TEMPORAL_READY with matching mentions
TEMPORAL_READY with zero mentions
TEMPORAL_DEGRADED
```

### Lexical tests

Include proper names, rare historical entities, dates, numbers, quoted phrases, acronyms/codes, punctuation-heavy identifiers, FTS-empty/weak normalization cases, and fallback activation correctness.

### Provenance tests

Verify returned evidence preserves corpus/document/version/processing/search-generation/chunk lineage and optional location degradation semantics.

### Determinism tests

Given the same request, persisted state, captured active generation, and retrieval config, Stage 3 should produce deterministic ordering with stable tie-breaking.

### Performance tests

Benchmark representative corpus sizes up to the accepted V1 envelope and record per-phase latency/candidate counts, including final validation/backfill and worst-case stale-candidate rejection.

### Reranker revisit trigger

Reconsider reranking when relevant evidence reliably appears in the fused pool but ranks too low to fit Stage 5's practical candidate budget.

### ANN revisit trigger

Benchmark ANN options when exact vector search fails representative V1 latency targets.

## Observability Requirements

Every execution traces at least:

```text
query_id
original_question
retrieval_query
selected/executable/invalid corpus IDs
retrieval profile + derivation
TemporalIntent[]
captured SearchRepresentationGeneration
retrieval state / eligibility epoch where available
retrieval_config_version
routes executed
route latencies
route candidate counts
lexical fallback activation
filters / typed constraints
eligibility rejection IDs/reasons
route scores/ranks
fusion output
bounded temporal adjustments
document diversity adjustments
state-change invalidation/restart details
final candidate IDs/ranks
degradation/failure details
total latency
```

Full candidate source text may be retained in an explicit debugging mode for the single-user V1 because it materially helps diagnosis. It should be configurable and should default toward minimization before broader production/multi-user deployment.

Rejected candidates should retain IDs and rejection reasons by default; full rejected text is unnecessary.

## Implementation Plan

Suggested order:

1. define request/result/state contracts and authoritative eligibility validator,
2. implement exact dense retrieval,
3. implement PostgreSQL FTS and bounded literal fallback,
4. implement same-chunk consolidation and RRF,
5. implement temporal candidate retrieval,
6. implement bounded temporal adjustment,
7. implement profiles and mild document diversity,
8. implement final current-state validation/backfill and ADR-008 cutover handling,
9. implement structured failure/degradation handling,
10. add observability/tracing,
11. build retrieval evaluation and representative benchmarks,
12. tune budgets/configuration,
13. revisit ANN/reranking/search infrastructure only when evidence justifies it.

Corpus isolation, eligibility/cutover correctness, deterministic ranking, temporal degradation, and malformed-contract tests should land before ranking/performance optimization.

## Open Questions

No unresolved architecture question blocks Stage 3 implementation.

The following remain implementation/evaluation choices:

- exact embedding provider/model,
- exact dense similarity metric for the selected model,
- exact PostgreSQL vector operator/index configuration,
- exact FTS configuration/tokenization,
- exact bounded literal fallback operators/indexes,
- exact candidate-budget defaults,
- exact RRF constant,
- exact bounded temporal-adjustment weights,
- exact document-diversity penalty/threshold,
- exact database isolation/epoch implementation satisfying ADR-008,
- exact bounded infrastructure retry/restart counts,
- exact numeric latency targets after representative benchmarking,
- optional query-embedding cache.

## Decisions Requiring Orchestrator Approval

None.

ADR-005, ADR-006, ADR-007, and ADR-008 are accepted.

## Impact on Existing Architecture

Accepted Stage 3 decisions promoted to `docs/architecture/architecture.md` include:

1. Query + Temporal Understanding is an upstream logical component coordinated by Stage 4 and produces structured local retrieval requests.
2. Stage 3 performs deterministic local dense + lexical retrieval by default with an optional structured temporal route.
3. PostgreSQL FTS retains a bounded literal fallback contract for important FTS-poor queries.
4. RRF is the V1 hybrid fusion baseline with same-chunk signal consolidation and optional bounded temporal adjustment.
5. Temporal route predicates do not become cross-route hard evidence filters by default.
6. No learned reranker and no ANN requirement are present in the initial V1 baseline; both are benchmark/evaluation-triggered.
7. Authoritative eligibility includes layered validation, final current-state validation, backfill, and coherent cutover behavior under ADR-008.
8. Stage 3 exposes structured success/no-candidate/degraded/failure semantics and provenance-complete candidates.
9. Stage 4 retains broader orchestration/replanning; Stage 5 retains final context/sufficiency/deduplication/corroboration/ordering.

## Acceptance Criteria

Stage 3 architecture is accepted and **Implementation Ready** when implementation follows these documented contracts and ADRs.

Implementation-time validation requirements remain mandatory:

- zero corpus/eligibility leakage,
- no mixed SearchRepresentationGeneration results,
- concurrency/cutover race tests,
- dense/lexical/hybrid/temporal ablations,
- lexical fallback tests,
- temporal degradation tests,
- representative exact-vector/PostgreSQL performance benchmarks,
- deterministic ordering/tie-breaking,
- complete retrieval tracing.
