# Stage 4: Agent / Orchestration Layer

## Status

**Implementation Ready.**

The Stage 4 architecture has passed orchestrator review. ADR-009 and ADR-010 are accepted, the Stage 3 boundary is preserved, the Stage 5 handoff is established, and the corresponding project-wide invariants are recorded in `docs/architecture/architecture.md`.

## Objective

Define the bounded orchestration layer that converts the current user request, relevant short-term conversation context, and immutable request-scoped evidence policy into one or more traceable local/web retrieval executions, then returns a structured evidence-gathering result to Stage 5.

Stage 4 coordinates Query + Temporal Understanding, source-policy enforcement, mandatory source execution, bounded query reformulation/decomposition, retry/replanning, state, stopping, web retrieval, and the Stage 5 handoff.

Stage 4 does not perform final evidence sufficiency assessment, final semantic deduplication/corroboration, final conflict resolution/grouping, context token budgeting, or answer generation.

## Scope

Stage 4 owns:

- orchestration request validation,
- immutable request-scoped evidence policy construction,
- Query + Temporal Understanding coordination,
- conversational-reference resolution,
- query-time temporal interpretation,
- clarification-versus-inference behavior,
- incremental execution planning,
- mandatory local/web source execution,
- bounded operational retries,
- bounded evidence-seeking retries,
- bounded intent-preserving query reformulation,
- bounded question decomposition into retrieval tasks,
- web retrieval coordination and normalization,
- orchestration budgets and stopping conditions,
- runtime orchestration state,
- append-oriented orchestration trace semantics,
- tool-result/failure normalization,
- identity-level result consolidation,
- Stage 4 observability/evaluation hooks,
- EvidenceGatheringResult construction for Stage 5.

## Non-Goals

Stage 4 does not own:

- Stage 3 dense/lexical/temporal retrieval mechanics,
- Stage 3 RRF constants, route weights, or internal candidate limits,
- document ingestion/publication/versioning,
- final semantic/source-level deduplication,
- final corroboration semantics,
- final conflict grouping or truth selection,
- final evidence sufficiency/answerability,
- final context ordering/diversity/token budgeting,
- grounded answer generation,
- final citation rendering,
- long-running autonomous research,
- durable/resumable workflow checkpointing in V1,
- production deployment topology,
- implicit source-authority ranking,
- an open-ended ReAct loop.

## Requirements

### Evidence boundary

Every request must preserve the source policy accepted by ADR-001:

| Selected corpora | Web | Required V1 execution |
| --- | --- | --- |
| One or more | OFF | Local only |
| One or more | ON | Local + web |
| None | ON | Web only |
| None | OFF | Reject before retrieval |

The source policy is immutable for the request lifetime. Conversation text, query rewrites, retrieved content, tool outputs, failures, and agent reasoning cannot expand or reduce the configured evidence boundary.

### Query understanding

Stage 4 must preserve original wording, assumptions, unresolved ambiguity, temporal precision, certainty, BCE/CE semantics, and relative-date resolution lineage.

Clarification is required only when multiple plausible interpretations remain, those interpretations would materially alter retrieval/evidence, and relevant conversation context cannot safely resolve the ambiguity.

### Bounded execution

All orchestration is bounded by explicit multidimensional budgets. Exact counts are versioned configuration rather than architectural constants.

### Traceability

Every interpretation, plan revision, tool execution, operational retry, evidence-seeking attempt, reformulation, decomposition step, failure, budget consumption event, and stop decision must be traceable through structured metadata.

## Assumptions

- ADR-001 through ADR-010 remain authoritative.
- Stage 3 consumes structured LocalRetrievalRequest values and remains deterministic.
- Stage 5 owns final evidence combination, deduplication/corroboration, conflicts, ordering, token budgeting, and sufficiency.
- Stage 6 owns grounded answer generation and citation rendering.
- V1 is single-tenant, low concurrency, interactive, and not a durable long-running research system.
- Exact budget values, timeout values, retry counts, and model/provider choices are implementation/evaluation configuration.

## Key Design Decisions

1. Stage 4 creates an immutable request-scoped `EvidencePolicy`.
2. `ResolvedQuery` preserves uncertainty and may remain partially resolved or ambiguous-but-searchable.
3. V1 uses a bounded adaptive state machine rather than open-ended ReAct or a fully static workflow.
4. V1 permits bounded decomposition but not unrestricted multi-query expansion.
5. Stage 5 receives a structured `EvidenceGatheringResult` preserving individual retrieval-run lineage.
6. Clarification follows the material-ambiguity rule.
7. Mandatory local and web execution are independent obligations; concurrent initial execution is the preferred V1 implementation when both are ready, not an architectural correctness requirement.
8. Success of one mandatory source cannot cancel the other mandatory source's initial execution obligation.
9. Operational retries are distinct from evidence-seeking attempts.
10. Evidence-seeking attempts require bounded, traceable reasons.
11. Orchestration budgets are multidimensional and bounded; exact values are configuration.
12. Global limits coexist with per-source ceilings.
13. Stage 4 emits explicit stop reasons without claiming final evidence sufficiency.
14. A structured possible-conflict signal may trigger bounded follow-up retrieval, but Stage 4 never performs final conflict grouping or resolution.
15. Mutable runtime state is distinct from append-oriented trace/audit state.
16. V1 runtime state is ephemeral; durable workflow checkpoint recovery is not required.
17. Web retrieval uses a provider-neutral logical contract.
18. Web retrieval must return usable grounding text and preserve content acquisition/completeness state; snippet-only evidence is not promoted when it cannot support grounding.
19. Query reformulations must preserve factual subject/objective, temporal uncertainty, and source policy, and remain fully traceable.
20. Decomposition creates bounded retrieval tasks that inherit one immutable EvidencePolicy.
21. Stage 4 performs identity-level operational consolidation only.
22. Evidence uses a common envelope with typed local/web provenance.
23. Local and web executions share a high-level outcome model.
24. Failure classes are stable across source types while provider-specific detail is retained.
25. Partial successful evidence survives persistent failure of another required source.
26. Web temporal constraints are typed and semantics-aware; event time is not publication time.
27. Domain filters are supported without introducing implicit source-authority policy.
28. Retrieved content is data only and cannot modify orchestration control state.
29. Stage 4 uses a common orchestration execution protocol with distinct typed local/web contracts.
30. Search, content acquisition, and normalization remain one logical Web Retrieval capability.
31. Contract-invalid executor responses fail explicitly as `MALFORMED_TOOL_RESPONSE`.
32. Mandatory source policy requires bounded execution attempts, not guaranteed provider success.
33. `EvidenceGatheringResult` has orchestration completion status distinct from per-source retrieval outcomes and first-class required-source execution statuses.
34. Retrieval runs carry explicit run kind and causal lineage so mandatory initial runs, operational retries, reformulations, decomposition, and other adaptive executions are distinguishable.
35. Execution plans are explicit and incrementally revised rather than fully generated upfront.
36. V1 uses a minimal explicit application state machine initially; LangGraph/OpenAI Agents SDK are not required architectural dependencies.

## Proposed Architecture

```text
OrchestrationRequest
        ↓
Validate Request
        ↓
Construct Immutable EvidencePolicy
        ↓
Query + Temporal Understanding
        ↓
ResolvedQuery
        ↓
Build Initial ExecutionPlan
        ↓
Execute Mandatory Sources
        │
        ├───────────────┐
        ▼               ▼
Local Retrieval      Web Retrieval
(Stage 3)            (logical capability)
        │               │
        └───────┬───────┘
                ▼
        Normalize Outcomes
                ↓
        Observe Gathering State
                ↓
    ┌──────────────────────────┐
    │ Optional bounded actions │
    │ - operational retry      │
    │ - query reformulation    │
    │ - decomposition          │
    │ - anchor recovery        │
    │ - conflict follow-up     │
    └──────────────────────────┘
                ↓
        Budget + Stop Evaluation
                ↓
        EvidenceGatheringResult
                ↓
              Stage 5
```

The diagram shows logical source obligations, not a mandatory scheduling topology. When both local and web are required and ready, concurrent initial execution is preferred for V1 latency, but sequencing is permitted when a concrete dependency or executor limitation requires it.

## Components

### OrchestrationService

Owns request lifecycle, state-machine transitions, budget enforcement, plan revisions, source execution coordination, and result construction.

### EvidencePolicy

Conceptually:

```text
EvidencePolicy
- selected_corpus_ids[]
- web_enabled
- local_required   # derived
- web_required     # derived
```

`local_required` and `web_required` are derived rather than independently supplied.

### Query + Temporal Understanding

Produces an uncertainty-preserving `ResolvedQuery`:

```text
ResolvedQuery
- original_question
- retrieval_query
- resolved_references[]
- temporal_intents[]
- assumptions[]
- unresolved_ambiguities[]
- interpretation_status
- retrieval_profile_hint?
```

Interpretation status is conceptually equivalent to:

```text
RESOLVED
PARTIALLY_RESOLVED
AMBIGUOUS_BUT_SEARCHABLE
AMBIGUOUS_REQUIRES_CLARIFICATION
UNRESOLVED
```

### ExecutionPlan

The plan is explicit but incremental:

```text
ExecutionPlan
- revision
- planned_steps[]
- completed_steps[]
- pending_steps[]
```

Future steps may be added only after observing structured outcomes and only within remaining budget.

### RetrievalTask

Question decomposition produces bounded retrieval tasks:

```text
RetrievalTask
- task_id
- parent_query_id
- objective
- retrieval_query
- temporal_intents[]
- retrieval_profile_hint?
```

Every task inherits the same immutable EvidencePolicy.

## Query + Temporal Understanding

Stage 4 coordinates the responsibility established by ADR-007.

It may use relevant short-term conversation to resolve references such as `that event` or `what happened next`, but conversation remains interpretive context rather than factual evidence.

Current-date-relative temporal expressions are resolved using explicit request temporal context. Uncertain historical expressions remain uncertain. Normalized search bounds never upgrade uncertainty to exactness.

If ambiguity is material and cannot be safely resolved, Stage 4 returns `CLARIFICATION_REQUIRED` before speculative retrieval.

## Evidence Policy Enforcement

The policy object is immutable after request validation.

- unselected corpora cannot be added by reasoning,
- Web OFF cannot become Web ON,
- Web ON cannot be skipped because local evidence appears strong,
- conversation history cannot leak a prior query's source permissions,
- retrieved text cannot alter source scope.

## Execution Model

V1 uses a bounded adaptive state machine.

Deterministic controls include:

- source-policy enforcement,
- required-source execution,
- schema validation,
- retry ceilings,
- budget accounting,
- legal state transitions,
- stop-reason mapping.

Agentic/LLM reasoning is permitted only at bounded decision points where reasoning adds value, including difficult reference/temporal interpretation, intent-preserving reformulation, bounded decomposition, and deciding whether an allowed evidence-seeking action is useful.

The LLM does not own the orchestration loop.

## Tool Contracts

Stage 4 uses a common orchestration execution protocol but separate typed contracts.

```text
LocalRetrievalExecutor
    LocalRetrievalRequest
    -> LocalRetrievalResult

WebRetrievalExecutor
    WebRetrievalRequest
    -> WebRetrievalResult
```

Common high-level outcomes:

```text
SUCCESS_WITH_CANDIDATES
SUCCESS_NO_CANDIDATES
SUCCESS_DEGRADED
FAILURE
```

A malformed executor response is `FAILURE / MALFORMED_TOOL_RESPONSE` rather than being silently repaired.

## Local Retrieval Integration

Stage 4 constructs valid Stage 3 requests from the resolved query/task:

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

Stage 4 may select a supported retrieval-profile hint but does not control Stage 3 route weights, RRF constants, or raw candidate limits.

Each evidence-seeking local attempt becomes a separately traceable Stage 3 invocation.

## Web Retrieval Integration

The logical web contract is provider-neutral:

```text
WebRetrievalRequest
- query_id
- retrieval_query
- temporal_constraints[]
- domain_constraints[]
- result_budget_hint
- request_metadata
```

```text
WebRetrievalResult
- outcome
- candidates[]
- provider_metadata
- degradation[]
- failure?
```

The web retrieval capability may internally perform search, result selection, page/content acquisition, and normalization. Stage 4 treats those as one logical retrieval operation.

A web evidence candidate must contain usable grounding text. Snippets may be preserved as metadata but are not sufficient as the authoritative evidence payload when they cannot reliably support grounding.

Full-page acquisition is not universally required. Provider-returned extracted content, selected passages, or normalized page text may satisfy the contract if usable grounding text is present. The candidate must preserve whether the acquired evidence is complete, partial, or of unknown completeness.

Conceptually:

```text
ContentAcquisition
- acquisition_kind
- completeness
- acquired_at
- source_locator?
- truncation_or_extraction_notes?
```

If usable grounding text cannot be acquired, the result remains explicitly degraded/failed/no-usable-candidate rather than promoting an inadequate snippet.

Temporal constraints are typed. Event/content-time intent must not be silently translated into publication-date filtering.

Domain constraints are allowed, but V1 introduces no hidden source-authority ranking or preferred-domain truth policy.

## Retry / Replanning

### Operational retries

Operational retries repeat the same logical tool request after a retryable execution failure such as a timeout, rate limit, transient provider failure, or transient database failure.

### Evidence-seeking attempts

Evidence-seeking attempts alter retrieval strategy and must carry a traceable reason, conceptually including:

```text
NO_RESULTS
UNRESOLVED_REFERENCE
TEMPORAL_ANCHOR_RECOVERY
QUERY_OVERCONSTRAINED
SUBQUERY_UNCOVERED
RELEVANT_SOURCE_DEGRADED
CONFLICT_FOLLOWUP
```

`UNRESOLVED_REFERENCE` is usable only when bounded retrieval can plausibly recover the anchor without inventing identity. Material ambiguity that changes the factual target requires clarification.

`RELEVANT_SOURCE_DEGRADED` is usable only when another permitted retrieval strategy can plausibly recover useful evidence.

`CONFLICT_FOLLOWUP` requires a structured possible-conflict signal. Stage 4 may use that signal to justify another bounded retrieval attempt but does not perform final semantic conflict grouping or adjudication.

Allowed adaptations include bounded intent-preserving reformulation, bounded decomposition, temporal/reference recovery, and bounded conflict follow-up.

Unrestricted query fan-out is not permitted in V1.

### Reformulation intent preservation

A valid reformulation changes retrieval expression without silently changing the factual proposition being asked.

Derived queries/tasks must:

- preserve the immutable original question,
- preserve the factual subject/entity target unless the transformation explicitly represents bounded unresolved-reference recovery,
- preserve the requested factual relation/objective,
- preserve typed temporal constraints, precision, certainty, and unresolved state,
- inherit the same EvidencePolicy,
- avoid unsupported factual premises and implicit source-authority assumptions,
- record parent/transformation lineage and a traceable reason.

A rewrite that requires assuming an unknown or disputed fact to form the query is rejected rather than accepted as an intent-preserving reformulation.

## State Management

### Runtime state

Conceptually:

```text
OrchestrationState
- query_id
- evidence_policy
- resolved_query
- execution_plan
- completed_runs[]
- pending_steps[]
- remaining_budget
- current_phase
- stop_reason?
```

Runtime state is request-lifetime/ephemeral in V1.

### Trace state

The append-oriented trace records interpretation, assumptions, plan transitions, requests, outcomes, retries, reformulations, subquery lineage, failures, budget consumption, and the final stop decision.

V1 does not require durable workflow checkpoint recovery, but trace retention must be sufficient for evaluation and debugging. Traces record structured decisions/results and reasons; arbitrary model chain-of-thought prose is not part of the trace contract.

## Budgets

Conceptual budget dimensions include:

```text
OrchestrationBudget
- max_total_tool_calls
- max_local_evidence_attempts
- max_web_evidence_attempts
- max_operational_retries_per_call
- max_query_reformulations
- max_subqueries
- deadline
```

A global ceiling coexists with per-source ceilings. Exact numeric values are versioned configuration and evaluation-tuned. The reasoning model cannot increase, reset, or transfer these limits.

## Stopping Conditions

Conceptual stop reasons include:

```text
REQUIRED_EXECUTION_COMPLETE
NO_USEFUL_ADAPTATION
MAX_ATTEMPTS_REACHED
BUDGET_EXHAUSTED
DEADLINE_EXHAUSTED
REQUIRED_TOOL_FAILURE
INVALID_REQUEST
CLARIFICATION_REQUIRED
```

The normal successful stop condition means required execution obligations were attempted and no justified bounded retrieval action remains.

`REQUIRED_TOOL_FAILURE` indicates that a required source could not complete successfully within its bounded execution/retry policy. It may coexist with `COMPLETED_DEGRADED` when another required source succeeded and its evidence is preserved.

Stage 4 does not emit `SUFFICIENT_EVIDENCE` or `ANSWERABLE`; final sufficiency belongs to Stage 5.

## Failure / Degraded Behavior

Stable cross-source failure metadata conceptually includes:

```text
ToolFailure
- source_type
- operation
- error_code
- failure_class
- retryable
- attempt_id
- message_summary
- provider_detail?
```

Failure classes include concepts such as:

```text
INVALID_REQUEST
TIMEOUT
RATE_LIMIT
TRANSIENT_PROVIDER_FAILURE
PERMANENT_PROVIDER_FAILURE
MALFORMED_TOOL_RESPONSE
AUTH_OR_CONFIGURATION_FAILURE
INTERNAL_RETRIEVAL_FAILURE
```

Required-source execution tracks requirement separately from success:

```text
RequiredSourceStatus
- source_type
- required
- attempted
- completed
- outcome
- terminal_failure?
```

A bounded persistent failure satisfies the execution-attempt obligation but remains an explicit source failure.

If one required source succeeds and another fails, successful evidence is preserved and Stage 4 completes in degraded form. If all required sources fail, Stage 4 returns the structured failure state and does not substitute model memory.

## Evidence Normalization

Stage 4 returns a common evidence envelope with source-specific provenance:

```text
EvidenceCandidate
- evidence_id
- source_type
- source_text
- title?
- temporal_metadata[]
- retrieval_lineage[]
- source_provenance
- content_acquisition?
```

Local provenance preserves corpus/document/version/ProcessingGeneration/SearchRepresentationGeneration/chunk/location identity.

Web provenance preserves URL/canonical URL where known, source/domain identity, publication time where known, and retrieval time. Web evidence additionally preserves acquisition/completeness state when applicable.

Web evidence does not receive fake local document/chunk identities merely for schema symmetry.

Stage 4 may consolidate only exact/identity-level operational duplicates while preserving all retrieval-run associations. Semantic/source-level deduplication and corroboration remain Stage 5 responsibilities.

## Stage 5 Handoff Contract

Conceptually:

```text
EvidenceGatheringResult
- query_id
- original_question
- resolved_query
- evidence_policy
- completion_status
- required_source_statuses[]
- retrieval_runs[]
- interpretation_assumptions[]
- tool_failures[]
- degraded_sources[]
- execution_summary
- stop_reason
```

Required-source status is first-class so ADR-001 compliance is machine-readable rather than inferred from summary text.

Each retrieval run preserves at least:

```text
RetrievalRun
- run_id
- task_id
- parent_task_id?
- run_kind
- parent_run_id?
- trigger_reason?
- query_transform_id?
- source_type
- query_used
- outcome
- candidates[]
- degradation[]
- failure?
```

`run_kind` distinguishes mandatory initial runs, operational retries, reformulation/decomposition executions, anchor recovery, conflict follow-up, and other bounded evidence-seeking executions. Exact enum names are implementation details; causal classification is required.

Conceptual completion states:

```text
COMPLETED
COMPLETED_DEGRADED
REJECTED
CLARIFICATION_REQUIRED
```

Completion status describes whether Stage 4 fulfilled its orchestration responsibility; it does not assert answerability.

## Prompt-Injection Boundary

Retrieved local/web content is data-plane input only.

It cannot modify:

- EvidencePolicy,
- budgets,
- source permissions,
- orchestration state transitions,
- tool permissions,
- system/control instructions.

Stage 9 may add additional defensive mechanisms, but Stage 4 must preserve this structural data/control separation.

## Evaluation Criteria

Stage 4 evaluation must cover at least:

- source-policy compliance,
- mandatory web execution compliance,
- mandatory local execution compliance,
- required-source status correctness,
- corpus-boundary violation rate,
- reference-resolution correctness,
- temporal interpretation correctness,
- material-ambiguity clarification correctness,
- query-rewrite intent preservation,
- transformation lineage completeness,
- decomposition correctness,
- retrieval-run kind/causal-lineage correctness,
- unnecessary tool-call rate,
- operational retry correctness,
- evidence-seeking retry usefulness,
- stopping correctness,
- loop/budget violation rate,
- failure/no-results distinction,
- graceful degradation correctness,
- malformed-tool-response handling,
- partial/extracted web-content representation,
- possible-conflict-trigger usefulness and false-positive behavior,
- trace completeness,
- latency,
- token usage,
- external-search cost.

Test classes include local-only, hybrid, web-only, invalid no-source, conversational follow-up, relative-date, ambiguous temporal, local failure + web success, web failure + local success, both fail, local/web no-results, reformulation-helpful/unhelpful, intent-drifting rewrite rejection, conflict follow-up, duplicate evidence, partial web content, malformed tool output, and budget/deadline exhaustion.

## Observability Requirements

Trace at least:

- query/request identity,
- immutable EvidencePolicy,
- resolved references and temporal intents,
- assumptions/unresolved ambiguity,
- execution-plan revisions,
- required source statuses,
- local/web request lineage,
- retrieval run kind and parent/trigger lineage,
- operational retries,
- evidence-seeking reasons,
- query transformations,
- decomposition lineage,
- web acquisition/completeness state,
- tool outcomes/failures/degradation,
- budget consumption,
- stop reason,
- EvidenceGatheringResult completion status,
- latency/tokens/cost where applicable.

## Performance / Cost Requirements

V1 prioritizes correctness and predictable bounded behavior over minimum tool-call cost.

- when local and web are both required and ready, concurrent initial execution is the preferred V1 implementation strategy,
- concurrency itself is not required for semantic correctness; independent mandatory execution obligations are,
- exact concurrency/timeout/retry values are implementation configuration,
- all adaptive execution is bounded,
- Stage 4 must expose latency and external-search cost for evaluation,
- framework/runtime choices must not require durable workflow infrastructure for V1.

## Dependencies

### Stage 3

Consumes accepted LocalRetrievalRequest and returns structured local candidates/outcomes. Stage 4 must not silently alter Stage 3 ranking mechanics or eligibility semantics.

### Stage 5

Consumes EvidenceGatheringResult and owns final semantic deduplication, corroboration, conflicts, source grouping, diversity, ordering, token budgeting, sufficiency, and final context selection.

### Stage 6

Requires evidence provenance, failures/degradation, interpretation assumptions, and web acquisition/completeness semantics to survive for grounded generation and citation behavior.

### Stage 7

Must evaluate query understanding, policy compliance, trajectories, transformations, retries, stopping, latency, and cost.

### Stage 8

Must support full structured orchestration trace inspection without requiring hidden reasoning prose.

### Stage 9

Must harden tool/retrieved-content boundaries, loop/budget enforcement, and prompt-injection handling.

### Stage 10

May later revisit deployment topology, distributed execution, durable workflows, queues, and horizontal scaling.

## Implementation Plan

1. Define typed Stage 4 request, EvidencePolicy, ResolvedQuery, TemporalIntent integration, runtime state, trace event, plan, budget, failure, RequiredSourceStatus, RetrievalRun, and EvidenceGatheringResult schemas.
2. Implement deterministic request/source-policy validation and clarification terminal behavior.
3. Implement Query + Temporal Understanding adapter with structured outputs and uncertainty preservation.
4. Implement typed LocalRetrievalExecutor adapter over Stage 3.
5. Implement provider-neutral WebRetrievalExecutor including usable-content acquisition/normalization and explicit completeness metadata.
6. Implement bounded state-machine transitions, independent mandatory-source execution, preferred concurrent initial scheduling where practical, budget accounting, and stop semantics.
7. Implement operational retry policy separately from evidence-seeking adaptation.
8. Implement intent-preserving reformulation and bounded decomposition with explicit transformation/run lineage.
9. Implement identity-level result consolidation and EvidenceGatheringResult construction.
10. Add trace instrumentation and Stage 7 evaluation fixtures before broad tuning.
11. Benchmark latency/cost and tune configuration ceilings without changing the architectural bounds.
12. Reconsider orchestration frameworks only if accepted revisit triggers emerge.

## Alternatives Considered

### Open-ended ReAct loop

Rejected for V1 because it weakens deterministic policy enforcement, bounded execution, reproducibility, and cost/latency control.

### Fully static workflow

Rejected because Stage 4 needs bounded reformulation, decomposition, reference/temporal recovery, and possible-conflict follow-up.

### Mandatory local/web concurrency as an architectural invariant

Rejected because ADR-001 requires both configured source classes to be attempted, not a particular scheduling mechanism. Concurrent initial execution remains the preferred V1 implementation when practical.

### LangGraph as initial orchestration foundation

Viable but not required for current V1 semantics. Durable checkpointing and richer workflow machinery are not currently needed. Revisit if workflow complexity/durability requirements increase.

### OpenAI Agents SDK as initial orchestration foundation

Useful for model/tool interaction and tracing, but not required to own Stage 4's deterministic state-machine control plane. It may be evaluated later for bounded reasoning/tool integrations without transferring policy control to a generic agent loop.

### Unrestricted multi-query expansion

Rejected because it increases cost, latency, duplicate evidence, and evaluation complexity without a bounded semantic need.

### One flattened evidence list with no run lineage

Rejected because retries/reformulations/source failures would become difficult to reproduce and evaluate.

### Infer run type from ordering or query text

Rejected because Stage 5/7/8 must not reconstruct orchestration trajectory semantics heuristically.

### Require full-page acquisition for every web result

Rejected because grounding requires usable source text, not universal full-page retention. Partial/extracted content is valid only when its completeness state is explicit.

## Open Questions

No architecture-blocking semantic questions remain.

Implementation configuration still requires evaluation-driven choices for:

- exact attempt/rewrite/subquery ceilings,
- timeout/backoff values,
- reasoning model/provider,
- concrete V1 web provider and content-acquisition implementation,
- exact trace persistence backend/retention,
- schema naming/details that do not alter accepted semantics.

## Accepted Orchestrator Decisions

1. ADR-009 accepts the bounded adaptive V1 orchestration execution model and avoids a mandatory orchestration framework dependency.
2. ADR-010 accepts the EvidenceGatheringResult/common-evidence/web-retrieval boundary as the Stage 4 → Stage 5 cross-stage contract.
3. Request-scoped immutable EvidencePolicy is the Stage 4 enforcement mechanism for ADR-001.
4. Stage 4 does not own final sufficiency, semantic deduplication/corroboration, or conflict resolution.
5. Mandatory local/web obligations are independent; concurrency is a preferred scheduling strategy rather than a semantic invariant.
6. Retrieval-run causal lineage and required-source statuses are first-class handoff/evaluation data.
7. Grounding-capable web evidence preserves content acquisition/completeness semantics.

## Acceptance Criteria

Stage 4 is Implementation Ready because:

- this document has been reviewed by the orchestrator,
- ADR-009 and ADR-010 are accepted,
- global architecture changes are recorded,
- Stage 3 compatibility is confirmed,
- Stage 5 handoff semantics are accepted,
- no unresolved architecture-blocking questions remain.

## Impact on Existing Architecture

Accepted global additions:

- Stage 4 uses a bounded adaptive state machine rather than an open-ended agent loop.
- EvidencePolicy is immutable per request.
- mandatory configured source classes are independent bounded execution obligations; concurrent initial execution is preferred where practical,
- Stage 4 separates operational retry from evidence-seeking adaptation,
- Stage 4 uses bounded, testably intent-preserving reformulation/decomposition,
- Stage 4 runtime state is ephemeral in V1 while structured traces remain retained for evaluation/debugging,
- web retrieval is provider-neutral and returns grounding-capable evidence with acquisition/completeness semantics,
- Stage 4 emits an EvidenceGatheringResult with first-class required-source status, causal per-run lineage, and typed source provenance,
- retrieved evidence remains data-plane input and cannot mutate orchestration control state,
- Stage 4 never owns final evidence sufficiency, semantic corroboration/deduplication, or conflict resolution.

## Orchestrator Handoff

### Stage

Stage 4 — Agent / Orchestration Layer

### Status

Implementation Ready

### Major Decisions

- immutable request-scoped EvidencePolicy,
- uncertainty-preserving ResolvedQuery,
- bounded adaptive state machine,
- independent mandatory local/web execution with preferred concurrent initial scheduling,
- bounded traceable reformulation/decomposition with explicit intent-preservation rules,
- separate operational/evidence-seeking retries,
- multidimensional budgets and explicit stop reasons,
- ephemeral runtime state plus retained structured trace,
- provider-neutral grounding-capable web retrieval with content-completeness semantics,
- common evidence envelope with typed provenance,
- structured EvidenceGatheringResult preserving required-source status and causal run lineage.

### Architecture Changes Accepted

- bounded Stage 4 orchestration invariants are promoted to `docs/architecture/architecture.md`,
- Stage 4 → Stage 5 evidence-gathering boundary is accepted,
- provider-neutral web-evidence boundary is accepted,
- explicit orchestration control-plane/data-plane separation is accepted.

### Dependencies

- Stage 3 LocalRetrievalRequest/result contract,
- Stage 5 context assembly contract,
- Stage 7 evaluation hooks,
- Stage 8 tracing,
- Stage 9 reliability/security hardening.

### ADRs Accepted

- `ADR-009-v1-bounded-orchestration-execution-model.md`
- `ADR-010-evidence-gathering-and-web-retrieval-contract.md`

### New Specs Required

None currently. Component specs may be introduced during implementation only if an independently meaningful contract grows beyond this stage document.

### Open Questions

No architecture-blocking questions remain.

### Risks

- query-understanding/reformulation can drift factual intent unless schema/evaluation is strict,
- web content acquisition can increase latency/cost,
- overly generous adaptive budgets can recreate open-ended behavior,
- Stage 4 must not absorb Stage 5 sufficiency/dedup/conflict responsibilities during implementation.

### Files Created or Updated

- `docs/stages/04-agent-orchestration.md`
- `docs/architecture/decisions/ADR-009-v1-bounded-orchestration-execution-model.md`
- `docs/architecture/decisions/ADR-010-evidence-gathering-and-web-retrieval-contract.md`
- `docs/architecture/architecture.md`
