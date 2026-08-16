# Stage 3: Retrieval Pipeline

## Status

**Architecture Ready — awaiting orchestrator review and acceptance of proposed ADRs.**

Implementation must not begin until orchestrator-impacting decisions are accepted and any required global architecture updates are completed.

## Objective

Define how ASTRAG converts an authorized local retrieval request into a ranked set of eligible, provenance-complete local evidence candidates for later orchestration and context-assembly stages.

Stage 3 owns query-time local retrieval across the user-selected corpora. It consumes the canonical/searchable representations produced by Stage 2 and must preserve the evidence-boundary, publication, generation, provenance, temporal-uncertainty, and deletion invariants already accepted by Stage 1, ADR-002, ADR-003, ADR-004, and the global architecture.

Stage 3 optimizes for historical and temporal question answering while remaining useful for general retrieval-augmented QA.

## Scope

Stage 3 defines:

- the structured local retrieval request and result contracts,
- selected-corpus enforcement,
- query-time authoritative evidence eligibility validation,
- dense retrieval,
- lexical retrieval,
- temporal candidate retrieval and temporal ranking signals,
- hybrid candidate fusion,
- same-chunk retrieval-hit consolidation,
- retrieval profiles and candidate budgets,
- light document-level diversity control,
- retrieval outcome/degradation semantics,
- query-time handling of degraded ingestion capabilities,
- retrieval provenance and scoring metadata,
- failure taxonomy and graceful partial-path degradation,
- retrieval observability,
- retrieval-specific evaluation requirements,
- V1 retrieval performance/benchmark requirements,
- implementation sequencing and revisit triggers for ANN, reranking, and specialized search infrastructure.

## Non-Goals

Stage 3 does not own:

- parsing, normalization, chunking, temporal extraction, or representation generation,
- document/version/publication lifecycle,
- full conversational-reference resolution,
- autonomous LLM query rewriting,
- agentic multi-query loops,
- cross-tool/source orchestration,
- web-search execution,
- final evidence sufficiency assessment,
- semantic contradiction/conflict detection,
- final semantic/source-level deduplication or corroboration semantics,
- neighboring-chunk/context expansion by default,
- final context token budgeting,
- final chronological context ordering,
- final citation rendering,
- answer generation,
- ANN infrastructure in the initial V1 baseline,
- a reranker in the initial V1 baseline,
- a dedicated vector database or dedicated lexical-search engine in V1.

Stage 4 owns broader orchestration and multi-step search/retry strategy. Stage 5 owns final evidence combination, semantic duplicate/corroboration handling, token budgeting, context diversity/ordering, and final context selection. Stage 6 owns grounded generation and citation presentation.

## Requirements

### 1. Evidence-boundary correctness

For every returned local candidate:

- its `corpus_id` must belong to the query's selected corpora,
- its logical document must be currently query-visible and non-deleted,
- its `document_version_id` must match the active published source version,
- its `processing_generation_id` must match the active published processed chunk set,
- its `search_representation_generation_id` must match the globally active SearchRepresentationGeneration captured for the request,
- its publication/readiness state must permit search visibility.

No candidate from an unselected corpus, inactive publication, inactive search generation, stale processed generation, or deleted/tombstoned evidence may appear in Stage 3 output.

Target violation rate: **0**.

### 2. Defense-in-depth eligibility enforcement

Eligibility is enforced in layers:

```text
search-time hard predicates
        ↓
candidate eligibility validation
        ↓
fusion / ranking
        ↓
final authoritative eligibility validation
        ↓
backfill from lower-ranked validated candidates
```

Search/index membership alone is never evidence authority.

Selected-corpus membership and active SearchRepresentationGeneration are checked both during candidate generation and during authoritative validation.

If authoritative eligibility cannot be evaluated reliably, Stage 3 fails closed and returns no candidates.

### 3. Structured retrieval input

Stage 3 consumes a structured request rather than raw conversation history.

Conceptually:

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

Conversational references such as `that event` or `what happened next` are resolved upstream before core retrieval. Upstream query/temporal understanding also converts temporal language into structured `TemporalIntent` values while preserving the user's original wording and uncertainty.

Stage 3 may perform deterministic retrieval normalization but does not autonomously paraphrase the query with an LLM or create agentic multi-query loops.

### 4. Temporal intent representation

A request may contain multiple independent temporal intents.

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

Supported V1 temporal retrieval shapes include:

- exact point/date,
- year/period point,
- range overlap,
- before,
- after,
- approximate/proximity (`AROUND`),
- recurring month/day semantics such as `on this day`.

Relative expressions depending on the current date are resolved upstream so the retrieval request remains deterministic.

Unresolved temporal anchors degrade where possible. If an unresolved anchor makes meaningful retrieval impossible, the request may fail rather than invent a date.

### 5. Hard versus soft temporal semantics

Temporal constraints are not universal hard filters.

Hard eligibility constraints are reserved for correctness boundaries such as selected corpus, active publication, active generations, and deletion state.

Temporal intent may become a hard query-semantic filter only when the resolved semantics clearly justify exclusion. Otherwise temporal metadata is used for candidate generation and ranking so missing/degraded temporal metadata does not destroy semantic recall.

For date-range and timeline queries, semantically/lexically relevant chunks without temporal metadata remain eligible candidates.

### 6. Dense retrieval

Dense retrieval executes for every normal local retrieval request in V1 unless the dense path fails.

Initial V1 behavior:

- use exact vector search against PostgreSQL/pgvector-style storage,
- do not require ANN initially,
- generate the query embedding inside the dense retriever,
- generate the embedding using the globally active SearchRepresentationGeneration captured for the request,
- reject incompatible embedding-space/model/configuration combinations as correctness failures,
- treat the similarity metric as part of SearchRepresentationGeneration configuration rather than a hardcoded global invariant.

Exact versus ANN is a benchmark-driven implementation decision. HNSW/IVFFlat or other ANN indexing is reconsidered only when representative V1 benchmarks show exact search misses agreed latency requirements.

### 7. Lexical retrieval

Lexical retrieval also executes for every normal local retrieval request in V1 unless the lexical path fails.

The lexical query is derived from `retrieval_query` while preserving `original_question` in execution metadata.

The V1 lexical strategy uses PostgreSQL full-text capabilities and should deliberately preserve useful exact/rare-token behavior for:

- quoted phrases,
- proper nouns,
- historical names,
- dates and numbers,
- acronyms/codes,
- uncommon entity tokens.

Broad semantic alias expansion is not owned by Stage 3. Deterministic, explicitly configured normalization may be used, but autonomous historical synonym/alias expansion belongs upstream or to Stage 4 strategy.

### 8. Temporal candidate route

Temporal retrieval is an additional candidate route for strongly temporal requests.

Stage 3 decides whether to execute this route from the structured `TemporalIntent` and retrieval profile. Upstream does not supply a low-level `execute_temporal_route` implementation flag.

The temporal route searches structured TemporalMentions associated with otherwise searchable chunks and must obey the same selected-corpus/publication/generation/deletion constraints as every other retrieval route.

A chunk may contain multiple temporal mentions. Temporal retrieval evaluates all applicable mentions rather than collapsing the chunk to one canonical date.

Unresolved relative mentions without safe normalized values do not participate in structured temporal filtering; their source text remains available through dense/lexical retrieval.

### 9. Temporal matching and ranking

Temporal ranking preserves interpretability rather than exposing a fictitious probability.

Potential match factors include:

```text
matched_mentions[]
relation
precision compatibility
certainty
origin
semantic role
temporal distance / overlap
```

For event-oriented queries, `EVENT_TIME`-like semantic roles may be preferred over relevant unknown roles and source metadata, but this is a configurable ranking preference, not an eligibility rule.

For source/publication-date queries, the preference may reverse and favor `SOURCE_METADATA`.

Approximate periods use overlap/proximity plus precision/certainty compatibility rather than binary exact matching.

When multiple mentions match one chunk, the strongest temporal match drives ranking while all matching mentions remain exposed for downstream explanation and reasoning.

### 10. Hybrid execution and fusion

Dense and lexical retrieval execute by default for every V1 local request.

Strongly temporal profiles may additionally execute the temporal candidate route.

Candidate lists are consolidated by canonical `chunk_id` before final fusion. If the same chunk appears in multiple routes, Stage 3 emits one candidate and preserves all route signals.

Different canonical chunks remain distinct even when their text is identical or their duplicate-lineage hashes match. Stage 5 owns final semantic/source-level deduplication and corroboration semantics.

V1 uses Reciprocal Rank Fusion (RRF) as the baseline hybrid fusion method because route score distributions are not directly comparable.

Conceptually:

```text
RRF_score(chunk) = Σ route_contribution(rank_in_route)
```

Initial route contribution is equal across participating routes. The exact RRF constant is configurable and evaluation-tuned rather than an architectural invariant.

RRF score is a ranking signal, not a calibrated relevance probability.

### 11. Bounded temporal post-fusion adjustment

For strongly temporal profiles, Stage 3 may apply a small deterministic temporal adjustment after RRF so exact/strong temporal intent is not washed out by rank fusion.

The adjustment must be bounded to avoid uncontrolled double-counting of temporal relevance.

Temporal adjustment weights are profile configuration and must be evaluated rather than guessed as permanent constants.

### 12. Retrieval profiles

V1 uses a small deterministic profile set:

- `FACT_LOOKUP`
- `TEMPORAL_POINT`
- `TEMPORAL_RANGE`
- `TIMELINE`
- `BROAD`

Profiles define internally controlled behavior such as candidate budgets, temporal-route activation, temporal adjustment strength, diversity behavior, and output breadth.

Upstream query understanding selects a profile where possible. Stage 3 validates it and defaults deterministically to `FACT_LOOKUP` when omitted or unknown, recording a warning/degradation when an unknown profile was supplied.

Callers may choose among supported profiles but do not supply arbitrary RRF weights, candidate counts, or ranking parameters.

`TIMELINE` uses broader retrieval/output budgets and a weaker document-diversity penalty, but Stage 3 continues to rank by retrieval relevance. Final chronological ordering belongs to Stage 5.

### 13. Candidate budgets

Stage 3 distinguishes separate budgets rather than overloading one `top_k`:

```text
dense_candidate_limit
lexical_candidate_limit
temporal_candidate_limit
fusion_candidate_limit
reranker_input_limit   # reserved for future use
retrieval_output_limit
```

Exact values are configuration and must be tuned using representative evaluation/benchmark datasets.

Stage 3 returns a moderately broad candidate set for Stage 5 rather than pretending to return final prompt-ready context.

### 14. Multi-corpus union semantics

Multiple selected corpora use union semantics.

V1 does not reserve per-corpus quotas. Candidates compete globally by relevance within the selected evidence boundary.

If some requested corpus IDs are nonexistent or no longer valid, Stage 3 ignores those IDs for execution but records degraded scope metadata. If no valid selected corpus remains, Stage 3 returns `FAILURE` with `NO_EXECUTABLE_CORPUS_SCOPE`.

### 15. Document-level diversity

Stage 3 may apply a mild configurable rank penalty after a configurable number of highly ranked chunks from the same document.

This is a retrieval-quality safeguard against one large document dominating the candidate pool; it is not Stage 5 context-diversity or corroboration logic.

The penalty is applied after fusion/eligibility and should remain weak. Timeline profiles may use a weaker penalty.

Automatic neighbor-chunk expansion is not part of the default V1 retrieval architecture.

### 16. No initial reranker

V1 begins without a cross-encoder, LLM, or other learned reranker.

Reranking is reconsidered when evaluation shows that relevant evidence consistently appears inside the fused candidate pool but ranks too poorly to fit Stage 5's practical candidate budget.

This keeps the baseline deterministic, cheaper, and easier to evaluate before another ranking layer is introduced.

### 17. Relevance and sufficiency semantics

Stage 3 does not use one universal absolute relevance threshold initially.

It distinguishes whether candidates were returned and whether retrieval paths executed successfully, but it does not claim that the evidence is sufficient to answer the user.

Final evidence sufficiency and answerability belong downstream.

Stage 3 therefore does not infer `NO_RELEVANT_RESULTS` solely from a low fusion score.

### 18. Degraded Stage 2 capabilities

`TEMPORAL = READY` with zero temporal mentions and `TEMPORAL = DEGRADED` are distinct states.

If temporal extraction failed but dense and lexical representations are valid, the document remains retrievable semantically/lexically. A temporal query does not make optional temporal enrichment a mandatory evidence-eligibility requirement.

Missing optional page/section location metadata similarly does not invalidate otherwise eligible evidence; degradation is preserved in candidate metadata.

### 19. Request snapshot consistency

A retrieval execution captures one active SearchRepresentationGeneration at the start and uses that generation consistently throughout the request.

Where practical, authoritative publication/eligibility checks should use a consistent database transaction/snapshot so a document cannot change active publication halfway through ranking and produce inconsistent provenance.

### 20. Retrieval configuration identity

Every execution records a `retrieval_config_version` or equivalent stable configuration identity covering profile/ranking configuration relevant to reproducibility.

V1 does not introduce a full first-class immutable `RetrievalGeneration` lifecycle entity. A versioned configuration identity in traces/results is sufficient initially.

## Assumptions

- Stage 2 is Implementation Ready and its persisted contract is authoritative.
- V1 is single-tenant with one primary user and low concurrency.
- V1 scale is hundreds to thousands of documents and approximately up to one million chunks.
- PostgreSQL is the accepted V1 relational/search foundation.
- pgvector-style integrated vector search and PostgreSQL full-text search remain the V1 search mechanisms.
- One SearchRepresentationGeneration is globally active for query-time local retrieval.
- Dense and lexical representations are mandatory for query-visible evidence.
- Temporal and provenance-location capabilities may be degraded.
- Upstream query understanding can produce a resolved `retrieval_query`, structured temporal intents, and an optional retrieval profile.
- Exact numeric budgets/weights will be established by evaluation rather than architecture decree.

## Key Design Decisions

1. Stage 3 consumes a structured `LocalRetrievalRequest`, not raw conversation history.
2. Conversational reference resolution and structured temporal interpretation occur upstream.
3. Dense and lexical retrieval always execute by default in V1.
4. Strongly temporal requests may additionally execute a structured temporal candidate route.
5. V1 starts with exact PostgreSQL vector search; ANN is benchmark-triggered.
6. Query embeddings are generated inside the dense retriever using the active SearchRepresentationGeneration.
7. Dense/lexical/temporal routes use rank-based RRF fusion rather than raw-score summation.
8. The same canonical chunk is consolidated across retrieval routes while all route signals are preserved.
9. Strong temporal profiles may apply a bounded deterministic post-RRF temporal adjustment.
10. Temporal constraints are not hard filters by default.
11. Temporal uncertainty, origin, role, precision, ranges, and multiple mentions remain visible to retrieval and downstream stages.
12. Optional temporal capability degradation never silently removes otherwise valid semantic/lexical evidence.
13. No reranker is included in the initial V1 baseline.
14. Separate candidate budgets exist for dense, lexical, temporal, fusion, reranker-input reservation, and Stage 3 output.
15. Multi-corpus retrieval uses global union semantics without per-corpus quotas.
16. Stage 3 may apply only a mild document-level diversity penalty; Stage 5 owns final context diversity.
17. Authoritative eligibility uses layered validation and fails closed if eligibility cannot be established.
18. Stage 3 does not decide final evidence sufficiency, conflict semantics, corroboration, or final chronology.
19. Retrieval outcomes and degradation are structured and machine-readable.
20. Retrieval configuration is versioned for evaluation reproducibility.

## Proposed Architecture

```text
Resolved Question
+ Selected Corpora
+ TemporalIntent[]
+ Retrieval Profile
        ↓
Capture retrieval_config_version
+ active SearchRepresentationGeneration
        ↓
Validate Request + Resolve Executable Corpus Scope
        ↓
┌─────────────────────────────────────────────┐
│ Dense Retrieval                            │
│ Lexical Retrieval                          │
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
Final Authoritative Eligibility Validation
        ↓
Backfill Valid Candidates
        ↓
LocalRetrievalResult
        ↓
Stage 4 / Stage 5
```

## Components

### Local Retrieval Coordinator

Validates `LocalRetrievalRequest`, captures request-scoped generation/config identity, resolves valid selected-corpus scope, executes enabled routes, consolidates route outputs, applies fusion/ranking, and constructs `LocalRetrievalResult`.

It does not perform agentic multi-step reasoning.

### Dense Retriever

- generates the query embedding,
- validates embedding-generation compatibility,
- performs exact V1 vector search,
- applies selected-corpus and active-generation predicates,
- returns route-specific ranks/similarity signals.

### Lexical Retriever

- derives the lexical query from `retrieval_query`,
- uses PostgreSQL FTS,
- preserves useful phrase/rare-term behavior,
- applies selected-corpus and active-generation predicates,
- returns lexical scores/ranks.

### Temporal Retriever

- activates for profiles/intents requiring structured temporal retrieval,
- searches all structured mentions associated with eligible chunks,
- handles point/range/before/after/proximity/recurrence semantics,
- respects precision, certainty, origin, role, and unresolved state,
- returns explainable temporal match details and route ranks.

### Eligibility Validator

Applies the authoritative Stage 2 query-visibility contract:

- selected corpus,
- active logical document/publication,
- active DocumentVersion,
- active ProcessingGeneration,
- active SearchRepresentationGeneration,
- non-deleted/tombstoned state,
- valid mandatory lineage.

Failure to execute the validator reliably fails local retrieval closed.

### Candidate Consolidator / Fusion

Collapses repeated route hits for the same `chunk_id`, preserves all route signals, performs RRF, and exposes fusion rank/score.

It does not remove distinct chunks solely because content hashes match.

### Temporal Rank Adjuster

Applies a bounded profile-specific deterministic adjustment after RRF for strongly temporal requests.

### Document Diversity Adjuster

Applies a mild configurable rank penalty after too many top candidates originate from the same document.

### Retrieval Result Builder

Constructs the immutable Stage 3 result envelope with candidate evidence snapshots, provenance, scores/signals, degradation details, scope warnings, and execution metadata.

## Data Flow

### Standard fact lookup

```text
LocalRetrievalRequest
        ↓
validate request/scope
        ↓
Dense + Lexical
        ↓
eligibility
        ↓
same-chunk consolidation
        ↓
RRF
        ↓
light diversity
        ↓
final eligibility + backfill
        ↓
LocalRetrievalResult
```

### Temporal point/range query

```text
LocalRetrievalRequest + TemporalIntent[]
        ↓
Dense + Lexical + Temporal Route
        ↓
eligibility
        ↓
same-chunk consolidation
        ↓
RRF
        ↓
bounded temporal adjustment
        ↓
light diversity
        ↓
final eligibility + backfill
        ↓
LocalRetrievalResult
```

### Degraded temporal capability

```text
Temporal query
        ↓
Dense + Lexical succeed
Temporal route / some documents degraded
        ↓
semantic/lexical evidence remains eligible
        ↓
result carries structured degradation metadata
```

### Partial route failure

```text
Dense fails
Lexical + Temporal succeed
        ↓
continue with usable routes
        ↓
SUCCESS_DEGRADED
        ↓
return candidates + path failure details
```

## Interfaces / Contracts

### LocalRetrievalRequest

Conceptual contract:

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

`retrieval_profile` may be omitted and defaults to `FACT_LOOKUP`.

V1 supports only known typed metadata constraints. Arbitrary SQL-like filter expressions are rejected.

### TemporalIntent

Conceptual contract:

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

Conceptual contract:

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

Conceptual fields:

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

`source_text` is always authoritative canonical evidence text, never embedding-context text or rewritten query text.

Core lineage is mandatory. Page/section/source-span location metadata may degrade where Stage 2 permits it.

Duplicate-lineage values such as `chunk_content_hash` and source-level hash signals are exposed separately from provenance and do not cause Stage 3 to collapse distinct canonical chunks.

### Retrieval execution metadata

Should preserve at least:

```text
query_id
original_question
retrieval_query
selected corpus scope
retrieval profile
TemporalIntent interpretation
active SearchRepresentationGeneration
retrieval_config_version
routes executed
route candidate counts
filters applied
fusion configuration identity
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

`SUCCESS_DEGRADED` is used when a configured/required retrieval path or requested scope fails but usable retrieval can still be returned.

A degraded execution may contain zero candidates; for example, dense fails while lexical succeeds but finds nothing. This remains degraded because the complete configured retrieval strategy did not execute successfully.

Stage 3 does not equate low ranking scores with insufficient evidence.

## Failure Handling

Stable machine-readable reason codes should include at least:

```text
DATABASE_UNAVAILABLE
QUERY_EMBEDDING_FAILED
EMBEDDING_GENERATION_INCOMPATIBLE
VECTOR_SEARCH_FAILED
LEXICAL_SEARCH_FAILED
TEMPORAL_SEARCH_FAILED
ELIGIBILITY_VALIDATION_FAILED
REQUEST_DEADLINE_EXCEEDED
INVALID_RETRIEVAL_REQUEST
NO_EXECUTABLE_CORPUS_SCOPE
MALFORMED_CANDIDATE_METADATA
```

Human-readable detail is recorded separately.

### Invalid request

Malformed temporal intent, unsupported typed constraint, invalid structure, or other contract violations fail before search.

### Invalid corpus IDs

Invalid/deleted requested corpus IDs are ignored for execution and recorded as degraded scope warnings.

If no valid selected corpus remains, Stage 3 returns `FAILURE / NO_EXECUTABLE_CORPUS_SCOPE`.

### Query embedding failure

Dense retrieval may fail independently. If lexical/temporal routes can produce usable results, return `SUCCESS_DEGRADED`.

Embedding-provider failure remains distinguishable from vector-database search failure.

### Embedding generation incompatibility

A query embedding incompatible with the captured active SearchRepresentationGeneration is a correctness/configuration failure, not ordinary degraded retrieval.

### Lexical search failure

If dense and/or temporal retrieval remains usable, return degraded results.

### Temporal route failure

If the selected profile does not require the temporal route, nonexecution is not degradation.

If a temporal route is required and fails while dense/lexical remain usable, return degraded semantic/lexical results with temporal failure details.

### Dense and lexical both fail

Temporal-only evidence may be returned only when the request is explicitly temporal and the temporal route can produce semantically meaningful candidates. Otherwise the local operation fails rather than treating date overlap alone as generic relevance.

### Eligibility validation failure

If the system cannot authoritatively determine candidate eligibility, Stage 3 fails closed.

Individual stale/ineligible candidates are rejected and traced; other validated candidates may continue and backfill.

### Malformed candidate metadata

A malformed derived row is rejected and traced. The overall execution becomes degraded if the defect materially affects retrieval; isolated rejected rows need not crash an otherwise reliable request.

### PostgreSQL failure

Database-wide unavailability is `FAILURE`, never `SUCCESS_NO_CANDIDATES`.

### Timeouts

One timed-out route may degrade to successful routes. If the overall request deadline expires before usable output can be assembled, return `FAILURE / REQUEST_DEADLINE_EXCEEDED`.

### Retry boundary

Stage 3 may perform small bounded infrastructure-level retries for clearly transient failures. Query rewriting, alternate-query generation, broader strategy retries, and multi-step evidence-seeking loops belong to Stage 4.

## Scalability

V1 targets:

- hundreds to thousands of documents,
- approximately up to one million chunks,
- one primary user,
- low concurrency,
- PostgreSQL + integrated vector/FTS search.

The architecture intentionally avoids dedicated vector/search infrastructure initially.

Exact vector search is the initial baseline. Representative benchmarks determine whether ANN is necessary.

PostgreSQL remains the V1 lexical-search foundation. A dedicated lexical/search system is a future architecture change only if later evaluation/scale requirements justify revisiting ADR-004.

## Latency / Throughput Requirements

Stage 3 uses a benchmark-first latency policy rather than inventing a hardware-independent hard target.

From the first implementation, measure at least:

- query-embedding latency,
- dense-search latency,
- lexical-search latency,
- temporal-search latency,
- eligibility-validation latency,
- fusion/ranking latency,
- total retrieval latency,
- candidate counts by route and phase.

After representative V1 deployment data exists, the project should establish numeric service targets.

ANN should be reconsidered only if exact vector search fails those targets at representative corpus sizes and workloads.

## Alternatives Considered

### Dense-only retrieval

Rejected as the V1 baseline because rare names, exact phrases, dates, numbers, and historical entities benefit materially from lexical retrieval.

### Lexical-only retrieval

Rejected because semantic paraphrase and meaning-based retrieval are core product requirements.

### Query classifier choosing dense versus lexical

Deferred. Always executing both routes provides a simpler, deterministic baseline and avoids introducing another classifier failure mode before evaluation evidence exists.

### Raw-score weighted fusion

Rejected initially because dense similarity, PostgreSQL lexical scores, and temporal signals are not naturally calibrated onto a common scale.

### Learned fusion

Deferred until sufficient labeled retrieval data exists to justify the added complexity.

### ANN as initial vector-search requirement

Deferred. Exact search keeps V1 simpler and must be benchmarked before ANN complexity is justified.

### Initial cross-encoder/LLM reranker

Deferred until evaluation demonstrates that recall is adequate but ranking quality is the limiting factor.

### Hard temporal filtering by default

Rejected because it destroys recall when temporal extraction is missing/degraded or relevant evidence describes a period without an explicit matching date.

### Per-corpus candidate quotas

Rejected for V1 because Stage 1 specifies union semantics and does not require corpus balancing.

### Automatic neighbor expansion

Deferred to Stage 5/context assembly unless retrieval evaluation proves it necessary.

### Broad alias/query expansion inside Stage 3

Rejected as a Stage 3 responsibility. Upstream query understanding or Stage 4 may own controlled query expansion strategies.

## Decisions

The Stage 3 architecture conversation resolved the following architecture-significant decisions:

- structured query/retrieval boundary,
- layered authoritative eligibility enforcement,
- dense + lexical always-on V1 hybrid retrieval,
- optional structured temporal candidate route,
- RRF baseline fusion,
- bounded temporal post-fusion adjustment,
- uncertainty-preserving temporal retrieval policy,
- graceful optional-capability degradation,
- no initial reranker,
- exact vector-search baseline,
- deterministic retrieval profiles,
- broad Stage 3 candidate output for Stage 5,
- structured result/degradation/failure contracts,
- benchmark/evaluation-triggered ANN and reranking adoption.

Architecture-wide decisions are proposed separately in ADR-005, ADR-006, and ADR-007 and are not accepted until orchestrator review.

## Dependencies

### Stage 1

Provides the evidence-boundary, grounding, union-semantics, insufficient-evidence, conflict-preservation, duplicate-evidence, and temporal-behavior requirements.

### Stage 2

Provides canonical query-visible chunks, active publication/version/processing-generation selection, active SearchRepresentationGeneration, dense/lexical representations, temporal mentions, provenance, capability state, deletion eligibility, and duplicate-lineage signals.

### Stage 4

Must produce/coordinate upstream query understanding and broader execution strategy. It may select supported retrieval profiles and perform multi-step query strategies, but it must not bypass Stage 3 eligibility/corpus invariants.

### Stage 5

Consumes broad Stage 3 candidates and owns final context selection, semantic deduplication/corroboration, token budgeting, source grouping, and chronological ordering.

### Stage 6

Consumes provenance-preserving context and renders grounded answers/citations.

### Stage 7

Owns the durable evaluation framework/datasets while incorporating Stage 3 retrieval metrics and test classes.

### Stage 8

Consumes Stage 3 traces for end-to-end observability/debugging.

### Stage 9

Builds guardrails/reliability mechanisms around retrieval failures, stale evidence, timeouts, and unsupported-answer behavior while preserving Stage 3's fail-closed evidence boundary.

### Stage 10

May revisit deployment/search infrastructure if concurrency/latency/scale exceeds accepted V1 assumptions.

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

Recall/ranking quality is especially important because Stage 5 performs final candidate selection.

### Mandatory ablations

Compare at minimum:

```text
dense only
lexical only
dense + lexical
dense + lexical + temporal
```

Hybrid retrieval should not merely be assumed beneficial; evaluation should verify improvement over single-route baselines.

### Temporal test classes

Include:

- exact date,
- year,
- range,
- before,
- after,
- approximate period,
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
- document moved between corpora.

Required result: **zero unauthorized/ineligible evidence leakage**.

### Capability-degradation tests

Explicitly distinguish:

```text
TEMPORAL_READY with matching mentions
TEMPORAL_READY with zero mentions
TEMPORAL_DEGRADED
```

### Provenance tests

Verify returned evidence preserves correct corpus/document/version/processing/search-generation/chunk lineage and optional location degradation semantics.

### Determinism tests

Given the same request, persisted state, active generations, and retrieval config, Stage 3 should produce deterministic ordering with stable tie-breaking.

### Performance tests

Benchmark representative corpus sizes up to the accepted V1 envelope and record per-phase latency/candidate counts.

### Reranker revisit trigger

Reconsider reranking when relevant evidence reliably appears in the fused candidate pool but ranks too low to fit Stage 5's practical candidate budget.

### ANN revisit trigger

Benchmark ANN options when exact vector search fails representative V1 latency targets.

## Observability Requirements

Every retrieval execution should trace at least:

```text
query_id
original_question
retrieval_query
selected corpus IDs
invalid/ignored corpus IDs
retrieval profile
TemporalIntent[]
active SearchRepresentationGeneration
retrieval_config_version
routes executed
route latencies
route candidate counts
filters applied
eligibility rejection IDs/reasons
route scores/ranks
fusion output
bounded temporal adjustments
document diversity adjustments
final candidate IDs/ranks
degradation/failure details
total latency
```

For V1, full candidate source text may also be retained in debugging traces because it materially improves diagnosis. This carries storage/privacy cost and should be revisited before broader production deployment or multi-user use.

Rejected candidates should at minimum retain IDs and rejection reasons. Full rejected-candidate text is not required by default.

## Implementation Plan

Suggested implementation order:

1. define retrieval contracts and eligibility validator,
2. implement exact dense retrieval,
3. implement lexical retrieval,
4. implement same-chunk consolidation and RRF,
5. implement temporal query execution,
6. implement bounded temporal post-fusion adjustment,
7. implement retrieval profiles and mild document diversity,
8. implement failure/degradation handling,
9. add observability/tracing,
10. build retrieval evaluation and representative benchmarks,
11. tune candidate budgets/configuration,
12. revisit ANN/reranking only when evaluation demonstrates need.

Corpus isolation, eligibility, deterministic ranking, and degradation tests should land before ranking/performance optimization work.

## Open Questions

No unresolved Stage 3 question currently blocks architecture consolidation.

The following remain implementation/evaluation choices rather than architecture blockers:

- exact embedding provider/model,
- exact dense similarity metric for the selected model,
- exact PostgreSQL vector operator/index configuration,
- exact FTS configuration/tokenization details,
- exact candidate-budget defaults,
- exact RRF constant,
- exact bounded temporal-adjustment weights,
- exact document-diversity penalty/threshold,
- exact infrastructure-level retry counts/backoff,
- exact numeric latency targets after representative benchmarking,
- optional query-embedding cache implementation.

## Decisions Requiring Orchestrator Approval

### Proposed ADR-005 — V1 Local Hybrid Retrieval and Fusion Policy

Requires orchestrator approval before implementation readiness.

Proposes dense + lexical always-on V1 retrieval, optional temporal candidate routing, same-chunk signal consolidation, RRF fusion, bounded temporal post-fusion adjustment, and independent retrieval-path degradation.

### Proposed ADR-006 — Temporal Query and Retrieval Policy

Requires orchestrator approval before implementation readiness.

Proposes structured multi-intent temporal input, uncertainty-preserving query-time semantics, hard-versus-soft temporal policy, temporal candidate routing/matching, role/origin-aware ranking, and degraded temporal behavior.

### Proposed ADR-007 — Query Understanding and Retrieval Boundary

Requires orchestrator approval before implementation readiness.

Proposes that conversational-reference resolution and structured query/temporal understanding happen upstream of core Stage 3 retrieval; Stage 3 receives `LocalRetrievalRequest`, owns deterministic retrieval mechanics, and excludes autonomous agentic query-rewrite/multi-query loops.

## Impact on Existing Architecture

If ADR-005 through ADR-007 are accepted, `docs/architecture/architecture.md` should be updated to record the following global architecture refinements:

1. **Query + Temporal Understanding → Local Retrieval contract**
   - upstream query understanding resolves conversational references,
   - produces resolved `retrieval_query`, `TemporalIntent[]`, and retrieval-profile intent,
   - Stage 3 does not consume raw conversation history for core retrieval.

2. **Local Corpus Retrieval architecture**
   - dense and lexical routes execute by default in V1,
   - strongly temporal requests may additionally execute a temporal candidate route,
   - same-chunk route hits are consolidated,
   - RRF is the initial V1 fusion baseline,
   - temporal profiles may apply bounded deterministic temporal adjustment,
   - no initial reranker,
   - exact vector search is the initial benchmark baseline.

3. **Authoritative query-time eligibility**
   - make the layered search-predicate + authoritative-validation + final-revalidation/backfill behavior explicit while retaining ADR-002 as the source decision.

4. **Retrieval outcome contract**
   - record structured success/no-candidate/degraded/failure semantics and independent retrieval-path degradation.

5. **Stage boundary clarification**
   - Stage 3 owns deterministic local retrieval mechanics,
   - Stage 4 owns broader multi-step orchestration/query strategies,
   - Stage 5 owns final evidence sufficiency/context selection/semantic duplicate and corroboration handling.

These changes should not be added to the accepted global architecture until the orchestrator accepts the proposed ADRs.

## Acceptance Criteria

Stage 3 may become **Implementation Ready** only when:

- this design is reviewed by the orchestrator,
- ADR-005, ADR-006, and ADR-007 are accepted or revised,
- required `architecture.md` changes are applied after ADR acceptance,
- request/result/provenance/failure contracts are internally consistent,
- boundary/deletion/generation leakage tests are defined with target violation rate `0`,
- temporal degradation behavior is explicitly testable,
- dense/lexical/hybrid/temporal ablation criteria are documented,
- observability captures enough state to diagnose retrieval decisions,
- implementation begins from a dedicated Stage 3 branch rather than improvising architecture on `main`.
