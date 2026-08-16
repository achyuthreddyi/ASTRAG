# ADR-007: Query Understanding and Retrieval Boundary

## Status

Accepted

## Context

ASTRAG must support conversational follow-ups and temporal questions such as:

- `What happened immediately after that?`
- `What happened 100 years ago today?`
- `What occurred before event X?`

The system therefore needs a clear boundary between:

1. interpreting the user's current question and relevant short-term conversation,
2. resolving query-time temporal language,
3. executing deterministic local retrieval,
4. running broader agentic multi-step strategies.

Without an explicit boundary, Stage 3 could gradually absorb conversation resolution, LLM query rewriting, multi-query generation, retry loops, and tool orchestration, collapsing the intended separation between Retrieval (Stage 3) and Agent/Orchestration (Stage 4).

Conversely, pushing every dense/lexical/temporal implementation detail into Stage 4 would tightly couple the orchestrator to search-engine mechanics and make retrieval harder to evaluate as a deterministic component.

## Decision

ASTRAG separates **Query + Temporal Understanding** from **core local retrieval execution** through a structured `LocalRetrievalRequest` contract.

The Query + Temporal Understanding component is an upstream logical responsibility coordinated by Stage 4. Stage 4 owns when interpretation/re-interpretation or additional evidence-seeking steps occur; Stage 3 does not own that agentic lifecycle.

### Query + Temporal Understanding owns

Before Stage 3 core retrieval executes, the upstream component is responsible for:

- interpreting the current question using relevant short-term conversation,
- resolving conversational references such as `that event` when reasonably possible,
- producing a resolved `retrieval_query`,
- resolving current-date-relative expressions such as `on this day` and `100 years ago today`,
- producing zero or more structured `TemporalIntent` values,
- preserving original temporal wording, precision, certainty, and resolution assumptions,
- selecting or recommending a supported Stage 3 retrieval profile where the intent requires one.

Conversation history remains interpretive context and is not a factual evidence source.

### Stage 3 receives a structured request

Core local retrieval conceptually receives:

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

Stage 3 does not require raw conversation history as part of its core retrieval contract.

This makes a retrieval execution reproducible from its explicit request, captured retrieval-state identity, persisted corpus state, and retrieval configuration.

### Stage 3 owns deterministic retrieval mechanics

Stage 3 owns:

- validating the retrieval request,
- validating/executing selected local corpus scope,
- generating the query embedding using the active SearchRepresentationGeneration,
- deriving the lexical query from the resolved retrieval query,
- deriving a deterministic default retrieval profile when the profile is omitted,
- selecting retrieval routes from structured intent/profile,
- dense, lexical, and temporal candidate retrieval,
- eligibility enforcement,
- candidate consolidation,
- fusion/ranking,
- bounded retrieval-level adjustments,
- retrieval-specific failure/degradation semantics,
- retrieval output/provenance/scoring metadata.

Stage 3 may perform deterministic normalization needed by the underlying retrieval implementation.

### Retrieval profile derivation and validation

Stage 4/upstream query understanding may select from the supported Stage 3 retrieval profiles, but Stage 3 defines the meaning/configuration of those profiles.

When the profile is omitted, Stage 3 derives a deterministic default from the structured request:

- point or recurring-day temporal intent → `TEMPORAL_POINT`,
- range/before/after/proximity temporal intent → the closest supported temporal profile, normally `TEMPORAL_RANGE`,
- no temporal intent → `FACT_LOOKUP` unless an explicit broad/timeline intent selects another supported profile.

An explicitly unknown profile is an invalid V1 request. It must not silently become `FACT_LOOKUP`, because doing so could weaken the retrieval strategy for a temporal query.

Callers do not directly control internal RRF constants, arbitrary route weights, or raw candidate budgets.

### Stage 3 does not own agentic query rewriting

Stage 3 does not autonomously:

- ask an LLM to paraphrase the query,
- create multiple semantic query variants,
- discover a missing temporal anchor through an agentic search loop,
- repeatedly broaden/narrow the query based on retrieved evidence,
- coordinate web search or other tools,
- decide when the overall agent should stop gathering evidence.

These behaviors belong to Stage 4 orchestration or the Query + Temporal Understanding component when Stage 4 coordinates it.

### Unresolved references/anchors

If Query + Temporal Understanding cannot safely resolve a conversational or temporal reference, it preserves the unresolved/degraded interpretation rather than inventing facts.

Stage 3 may still execute semantic/lexical retrieval when the structured request remains meaningful. If the missing anchor makes meaningful retrieval impossible, Stage 3 fails the request with structured reason metadata.

Stage 4 may then perform a separate evidence-seeking step to resolve the anchor and issue a new explicit `LocalRetrievalRequest`.

### Multi-step retrieval

If one retrieval execution is insufficient, Stage 4 may issue another explicit `LocalRetrievalRequest` as part of a broader agent trajectory.

Each Stage 3 execution remains independently traceable and deterministic given its explicit inputs and captured state.

## Consequences

### Positive

- Stage 3 remains a focused retrieval subsystem rather than becoming the whole agent.
- Stage 4 has explicit ownership of interpretation/replanning coordination without controlling pgvector/FTS mechanics.
- Conversation context cannot silently expand factual evidence permissions.
- Temporal interpretation is explicit, inspectable, and testable.
- Retrieval executions become reproducible and easier to evaluate independently.
- Profile omission cannot silently weaken temporal retrieval.
- Agentic query expansion can evolve later without changing Stage 3's core retrieval semantics.

### Negative

- The system needs an explicit Query + Temporal Understanding contract before local retrieval.
- Stage 4 must coordinate unresolved-reference/anchor recovery when it requires additional evidence.
- Upstream components must preserve enough interpretation metadata for Stage 3 and observability.
- Some failures require coordination between query understanding and retrieval rather than one monolithic component handling everything internally.

## Alternatives Considered

### Stage 3 consumes raw query + conversation and resolves everything

Rejected because it blurs Retrieval and Agent/Orchestration responsibilities, reduces deterministic evaluation, and encourages agentic loops to accumulate inside the retriever.

### Stage 4 constructs low-level dense/lexical/temporal search queries

Rejected because it couples orchestration to retrieval-engine mechanics and makes Stage 3 less independently evolvable.

### Stage 3 autonomously performs LLM multi-query expansion

Rejected for V1 because multi-query strategy is agentic orchestration and should be evaluated as such rather than hidden inside one retrieval call.

### Unknown profiles silently fall back to FACT_LOOKUP

Rejected because malformed cross-stage input should not silently weaken temporal retrieval behavior.

### No structured temporal intent

Rejected because temporal retrieval is a primary ASTRAG capability and requires explicit, uncertainty-preserving query semantics.

## Revisit Triggers

Revisit this ADR if:

- evaluation shows tightly integrated retrieval-time query rewriting is necessary for acceptable recall,
- Stage 4's orchestration becomes unnecessarily coupled to query-understanding internals,
- a dedicated shared query-understanding service/component becomes a deployment-level requirement,
- or production/API constraints require moving interpretation boundaries while preserving the same evidence invariants.

## Affected Stages

- Stage 3 — Retrieval Pipeline
- Stage 4 — Agent / Orchestration Layer
- Stage 5 — Context Assembly
- Stage 7 — Evaluation Framework
- Stage 8 — Observability & Debugging
- Stage 9 — Guardrails & Reliability

## Related Documents

- `NORTHSTAR.md`
- `docs/architecture/architecture.md`
- `docs/stages/01-problem-definition.md`
- `docs/stages/03-retrieval.md`
- `docs/architecture/decisions/ADR-001-query-source-execution-policy.md`
- `docs/architecture/decisions/ADR-005-v1-local-hybrid-retrieval-fusion-policy.md`
- `docs/architecture/decisions/ADR-006-temporal-query-retrieval-policy.md`
- `docs/architecture/decisions/ADR-008-retrieval-eligibility-consistency-cutover-policy.md`
