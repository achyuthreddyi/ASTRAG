# Stage 4: Agent / Orchestration Layer

## Status

**Architecture Ready — Awaiting Orchestrator Review.**

Stage 4 semantics have been consolidated in this document, but Stage 4 must not be marked **Implementation Ready** until the proposed ADRs and any resulting global architecture updates are reviewed and accepted by the orchestrator.

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

Every interpretation, plan revision, tool execution, operational retry, evidence-seeking attempt, reformulation, decomposition step, failure, budget consumption event, and stop decision must be traceable.

## Assumptions

- ADR-001 through ADR-008 remain authoritative.
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
7. Mandatory local and web retrieval execute concurrently after shared query understanding when both are configured.
8. Success of one mandatory source cannot cancel the other mandatory source's initial execution obligation.
9. Operational retries are distinct from evidence-seeking attempts.
10. Evidence-seeking attempts require bounded, traceable reasons.
11. Orchestration budgets are multidimensional and bounded; exact values are configuration.
12. Global limits coexist with per-source ceilings.
13. Stage 4 emits explicit stop reasons without claiming final evidence sufficiency.
14. Conflict may trigger bounded follow-up retrieval but Stage 4 never resolves the conflict.
15. Mutable runtime state is distinct from append-oriented trace/audit state.
16. V1 runtime state is ephemeral; durable workflow checkpoint recovery is not required.
17. Web retrieval uses a provider-neutral logical contract.
18. Web retrieval must return usable grounding text, not snippet-only evidence.
19. Query reformulations must preserve factual intent and remain fully traceable.
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
33. `EvidenceGatheringResult` has orchestration completion status distinct from per-source retrieval outcomes.
34. Execution plans are explicit and incrementally revised rather than fully generated upfront.
35. Proposed implementation choice: V1 uses a minimal explicit application state machine; LangGraph/OpenAI Agents SDK are not required architectural dependencies initially.

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

A web evidence candidate must contain usable grounding text. Snippets may be preserved as metadata but are not sufficient as the authoritative evidence payload.

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

Allowed adaptations include bounded intent-preserving reformulation, bounded decomposition, temporal/reference recovery, and bounded conflict follow-up.

Unrestricted query fan-out is not permitted in V1.

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

V1 does not require durable workflow checkpoint recovery, but trace retention must be sufficient for evaluation and debugging.

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

A global ceiling coexists with per-source ceilings. Exact numeric values are versioned configuration and evaluation-tuned.

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

The normal successful stop condition means required execution obligations were satisfied and no justified bounded retrieval action remains.

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
- required
- attempted
- completed
- outcome
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
```

Local provenance preserves corpus/document/version/ProcessingGeneration/SearchRepresentationGeneration/chunk/location identity.

Web provenance preserves URL/canonical URL where known, source/domain identity, publication time where known, and retrieval time.

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
- retrieval_runs[]
- interpretation_assumptions[]
- tool_failures[]
- degraded_sources[]
- execution_summary
- stop_reason
```

Each retrieval run preserves at least:

```text
RetrievalRun
- run_id
- parent_task_id?
- source_type
- query_used
- outcome
- candidates[]
- degradation[]
- failure?
```

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
- corpus-boundary violation rate,
- reference-resolution correctness,
- temporal interpretation correctness,
- material-ambiguity clarification correctness,
- query-rewrite intent preservation,
- decomposition correctness,
- unnecessary tool-call rate,
- operational retry correctness,
- evidence-seeking retry usefulness,
- stopping correctness,
- loop/budget violation rate,
- failure/no-results distinction,
- graceful degradation correctness,
- malformed-tool-response handling,
- trace completeness,
- latency,
- token usage,
- external-search cost.

Test classes include local-only, hybrid, web-only, invalid no-source, conversational follow-up, relative-date, ambiguous temporal, local failure + web success, web failure + local success, both fail, local/web no-results, reformulation-helpful/unhelpful, conflict follow-up, duplicate evidence, malformed tool output, and budget/deadline exhaustion.

## Observability Requirements

Trace at least:

- query/request identity,
- immutable EvidencePolicy,
- resolved references and temporal intents,
- assumptions/unresolved ambiguity,
- execution-plan revisions,
- required source statuses,
- local/web request lineage,
- operational retries,
- evidence-seeking reasons,
- query transformations,
- decomposition lineage,
- tool outcomes/failures/degradation,
- budget consumption,
- stop reason,
- EvidenceGatheringResult completion status,
- latency/tokens/cost where applicable.

## Performance / Cost Requirements

V1 prioritizes correctness and predictable bounded behavior over minimum tool-call cost.

- mandatory local/web source classes may execute concurrently,
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

Requires evidence provenance, failures/degradation, and interpretation assumptions to survive for grounded generation and citation behavior.

### Stage 7

Must evaluate query understanding, policy compliance, trajectories, retries, stopping, latency, and cost.

### Stage 8

Must support full orchestration trace inspection.

### Stage 9

Must harden tool/retrieved-content boundaries, loop/budget enforcement, and prompt-injection handling.

### Stage 10

May later revisit deployment topology, distributed execution, durable workflows, queues, and horizontal scaling.

## Implementation Plan

1. Define typed Stage 4 request, EvidencePolicy, ResolvedQuery, TemporalIntent integration, runtime state, trace event, plan, budget, failure, and EvidenceGatheringResult schemas.
2. Implement deterministic request/source-policy validation and clarification terminal behavior.
3. Implement Query + Temporal Understanding adapter with structured outputs and uncertainty preservation.
4. Implement typed LocalRetrievalExecutor adapter over Stage 3.
5. Implement provider-neutral WebRetrievalExecutor including usable-content acquisition/normalization.
6. Implement bounded state-machine transitions, mandatory-source concurrency, budget accounting, and stop semantics.
7. Implement operational retry policy separately from evidence-seeking adaptation.
8. Implement intent-preserving reformulation and bounded decomposition with lineage.
9. Implement identity-level result consolidation and EvidenceGatheringResult construction.
10. Add trace instrumentation and Stage 7 evaluation fixtures before broad tuning.
11. Benchmark latency/cost and tune configuration ceilings without changing the architectural bounds.
12. Reconsider orchestration frameworks only if accepted revisit triggers emerge.

## Alternatives Considered

### Open-ended ReAct loop

Rejected for V1 because it weakens deterministic policy enforcement, bounded execution, reproducibility, and cost/latency control.

### Fully static workflow

Rejected because Stage 4 needs bounded reformulation, decomposition, reference/temporal recovery, and conflict follow-up.

### LangGraph as initial orchestration foundation

Viable but not required for current V1 semantics. Durable checkpointing and richer workflow machinery are not currently needed. Revisit if workflow complexity/durability requirements increase.

### OpenAI Agents SDK as initial orchestration foundation

Useful for model/tool interaction and tracing, but not required to own Stage 4's deterministic state-machine control plane. It may be evaluated later for bounded reasoning/tool integrations without transferring policy control to a generic agent loop.

### Unrestricted multi-query expansion

Rejected because it increases cost, latency, duplicate evidence, and evaluation complexity without a bounded semantic need.

### One flattened evidence list with no run lineage

Rejected because retries/reformulations/source failures would become difficult to reproduce and evaluate.

## Open Questions

No blocking semantic questions remain in the current Stage 4 discovery pass.

Implementation configuration still requires evaluation-driven choices for:

- exact attempt/rewrite/subquery ceilings,
- timeout/backoff values,
- reasoning model/provider,
- concrete V1 web provider and content-acquisition implementation,
- exact trace persistence backend/retention,
- schema naming/details that do not alter accepted semantics.

## Decisions Requiring Orchestrator Approval

1. Accept the bounded adaptive V1 orchestration execution model and initial decision to avoid a mandatory orchestration framework dependency.
2. Accept the EvidenceGatheringResult/common-evidence/web-retrieval boundary as the Stage 4 → Stage 5 cross-stage contract.
3. Accept request-scoped immutable EvidencePolicy representation as the concrete Stage 4 enforcement mechanism for ADR-001.
4. Accept the explicit Stage 4 / Stage 5 boundary that prohibits Stage 4 final sufficiency, semantic deduplication/corroboration, and conflict resolution.
5. Accept the global architecture updates implied by the proposed ADRs after review.

## Acceptance Criteria

Stage 4 becomes Implementation Ready only when:

- this document is reviewed by the orchestrator,
- proposed ADRs are accepted or revised,
- global architecture changes are accepted and recorded,
- Stage 3 compatibility is confirmed,
- Stage 5 handoff semantics are accepted,
- no unresolved architecture-blocking questions remain.

## Impact on Existing Architecture

Proposed global additions, pending orchestrator acceptance:

- Stage 4 is a bounded adaptive state machine rather than an open-ended agent loop.
- EvidencePolicy is immutable per request.
- mandatory configured source classes execute independently and concurrently where possible,
- Stage 4 separates operational retry from evidence-seeking adaptation,
- Stage 4 runtime state is ephemeral in V1 while traces remain retained for evaluation/debugging,
- web retrieval is provider-neutral and returns grounding-capable evidence,
- Stage 4 emits an EvidenceGatheringResult with per-run lineage and typed source provenance,
- Stage 4 never owns final evidence sufficiency, semantic corroboration/deduplication, or conflict resolution.

## Orchestrator Handoff

### Stage

Stage 4 — Agent / Orchestration Layer

### Status

Architecture Ready — Awaiting Orchestrator Review

### Major Decisions

- immutable request-scoped EvidencePolicy,
- uncertainty-preserving ResolvedQuery,
- bounded adaptive state machine,
- concurrent mandatory local/web initial execution,
- bounded traceable reformulation/decomposition,
- separate operational/evidence-seeking retries,
- multidimensional budgets and explicit stop reasons,
- ephemeral runtime state plus retained trace,
- provider-neutral grounding-capable web retrieval,
- common evidence envelope with typed provenance,
- structured EvidenceGatheringResult preserving run lineage.

### Architecture Changes Proposed

- add bounded Stage 4 orchestration invariants to `docs/architecture/architecture.md` after approval,
- add Stage 4 → Stage 5 evidence-gathering boundary,
- add provider-neutral web-evidence boundary,
- add explicit orchestration control-plane/data-plane separation.

### Dependencies

- Stage 3 LocalRetrievalRequest/result contract,
- Stage 5 context assembly contract,
- Stage 7 evaluation hooks,
- Stage 8 tracing,
- Stage 9 reliability/security hardening.

### ADRs Required

- `ADR-009-v1-bounded-orchestration-execution-model.md`
- `ADR-010-evidence-gathering-and-web-retrieval-contract.md`

### New Specs Required

None currently. Component specs may be introduced during implementation only if an independently meaningful contract grows beyond this stage document.

### Open Questions

No architecture-blocking questions in the current discovery pass.

### Risks

- query-understanding/reformulation can drift factual intent unless schema/evaluation is strict,
- web content acquisition can increase latency/cost,
- overly generous adaptive budgets can recreate open-ended behavior,
- Stage 4 must not absorb Stage 5 sufficiency/dedup/conflict responsibilities during implementation.

### Files Created or Updated

- `docs/stages/04-agent-orchestration.md`
- proposed ADR-009
- proposed ADR-010

`docs/architecture/architecture.md` should be updated only after orchestrator acceptance of the proposed global decisions.
