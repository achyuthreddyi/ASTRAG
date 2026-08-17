# ADR-009: V1 Bounded Orchestration Execution Model

## Status

Accepted

## Context

Stage 4 must coordinate Query + Temporal Understanding, mandatory source execution, local/web retrieval, bounded adaptation, retries, failures, and stopping while preserving the source-policy contract established by ADR-001 and the deterministic Stage 3 boundary established by ADR-007.

Several orchestration models are viable:

1. an open-ended ReAct-style agent loop,
2. a fully predetermined static workflow,
3. a bounded adaptive state machine with deterministic control transitions and limited agentic reasoning,
4. adoption of a general orchestration framework such as LangGraph or an agent SDK as the primary execution architecture.

ASTRAG V1 is interactive, single-tenant, low-concurrency, and explicitly does not target autonomous long-running research. Stage 3 already provides deterministic structured local retrieval. Stage 5 owns final evidence sufficiency, semantic deduplication/corroboration, conflict grouping, token budgeting, and context selection.

Stage 4 therefore requires adaptive retrieval behavior without allowing the reasoning model to control source permissions, loop bounds, or final answerability semantics.

## Decision

ASTRAG V1 uses a **bounded adaptive application state machine** for Stage 4 orchestration.

The control plane is explicit and deterministic. Agentic/LLM reasoning is invoked only at bounded decision points where semantic interpretation adds value.

### Deterministic control responsibilities

The orchestration state machine deterministically owns:

- request/schema validation,
- immutable EvidencePolicy construction,
- mandatory-source obligations,
- legal state transitions,
- execution-plan revisions,
- budget accounting,
- operational retry ceilings,
- evidence-seeking attempt ceilings,
- deadline enforcement,
- executor contract validation,
- outcome/failure normalization,
- stop-reason mapping,
- EvidenceGatheringResult construction.

The reasoning model cannot override these controls.

### Agentic reasoning responsibilities

LLM/semantic reasoning may be used for bounded tasks such as:

- difficult conversational-reference resolution,
- difficult query-time temporal interpretation,
- deciding whether ambiguity is material,
- intent-preserving query reformulation,
- bounded question decomposition,
- deciding whether an allowed evidence-seeking action is likely to be useful.

The LLM does not own the orchestration loop and cannot expand source scope or execution budgets.

### Immutable request-scoped EvidencePolicy

Stage 4 derives an immutable request-scoped EvidencePolicy from the current query configuration.

Conceptually:

```text
EvidencePolicy
- selected_corpus_ids[]
- web_enabled
- local_required
- web_required
```

`local_required` and `web_required` are derived from ADR-001 rather than independently supplied.

Conversation history, query transformations, retrieved evidence, tool output, or reasoning cannot mutate this policy.

### Mandatory source execution

When corpora are selected and Web is ON, local and web retrieval are both mandatory bounded execution obligations.

Success from one required source cannot cancel the initial execution obligation of the other.

Mandatory execution means a bounded execution-attempt obligation, not guaranteed provider success. Persistent failure remains explicit downstream.

When both required source classes are ready after shared query understanding, concurrent initial execution is the preferred V1 implementation strategy because it reduces latency and isolates source failures. Concurrency is **not** a semantic requirement of ADR-001: an implementation may sequence execution when a concrete dependency, executor limitation, or deadline strategy requires it, provided both mandatory source obligations remain independently enforced and one source's success cannot suppress the other's required initial attempt.

### Incremental execution planning

Stage 4 maintains an explicit ExecutionPlan but does not require the full future trajectory upfront.

The initial plan covers request interpretation and mandatory source execution. Later steps may be appended only after observing structured results and only when a permitted evidence-seeking trigger exists and budget remains.

Every plan revision is traceable.

### Operational retry versus evidence-seeking attempt

Stage 4 distinguishes:

- **operational retry** — repeat the same logical tool request after a retryable execution failure;
- **evidence-seeking attempt** — issue a new retrieval execution after changing retrieval strategy while preserving factual intent.

Evidence-seeking attempts require explicit traceable reasons, including concepts such as:

```text
NO_RESULTS
UNRESOLVED_REFERENCE
TEMPORAL_ANCHOR_RECOVERY
QUERY_OVERCONSTRAINED
SUBQUERY_UNCOVERED
RELEVANT_SOURCE_DEGRADED
CONFLICT_FOLLOWUP
```

`UNRESOLVED_REFERENCE` is a valid evidence-seeking trigger only when bounded retrieval can plausibly recover the missing anchor without inventing identity. Material ambiguity that would change the factual target requires clarification instead.

`RELEVANT_SOURCE_DEGRADED` is a valid trigger only when a different permitted strategy can plausibly recover useful evidence.

### Query reformulation and decomposition

V1 supports bounded intent-preserving reformulation and bounded decomposition into explicit retrieval tasks.

It does not support unrestricted multi-query fan-out.

All derived queries/tasks:

- preserve the immutable original question,
- retain parent/child or transformation lineage,
- inherit the same immutable EvidencePolicy,
- preserve the user's factual subject/entity target unless the transformation explicitly represents a bounded unresolved-reference recovery,
- preserve the requested factual relation or objective,
- preserve typed temporal constraints, precision, certainty, and unresolved state rather than strengthening them into false exactness,
- cannot introduce unsupported factual premises,
- cannot silently add new source restrictions or authority assumptions,
- record a traceable transformation reason and the resulting retrieval query.

A reformulation is intent-preserving only when it changes retrieval expression, not the factual proposition being asked. If a proposed rewrite would require assuming a disputed or unknown fact to form the query, it is rejected rather than treated as a valid reformulation.

### Multidimensional budgets

All execution is bounded.

Architectural budget dimensions include concepts such as:

```text
max_total_tool_calls
max_local_evidence_attempts
max_web_evidence_attempts
max_operational_retries_per_call
max_query_reformulations
max_subqueries
deadline
```

A global ceiling coexists with per-source ceilings so one source class cannot consume the entire adaptive-search budget.

Exact numeric values are versioned implementation/evaluation configuration, not architectural constants. The reasoning model cannot increase or reset these budgets.

### Stop semantics

Stage 4 emits explicit orchestration stop reasons such as:

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

Stage 4 does not emit final `SUFFICIENT_EVIDENCE` or `ANSWERABLE` judgments. Those remain Stage 5 responsibilities.

The normal successful stop state means required source obligations were attempted and no justified bounded retrieval action remains.

`REQUIRED_TOOL_FAILURE` indicates that a required source could not complete successfully within its bounded execution/retry policy. It may coexist with orchestration-level degraded completion when another required source succeeded and its evidence is preserved.

### Conflict handling

Stage 4 may perform one or more bounded follow-up retrieval attempts when it receives or derives a structured **possible-conflict signal** indicating that additional retrieval could materially improve the evidence set.

The signal is not a final conflict group or truth judgment. Stage 4 may use only lightweight structured cues needed to justify another retrieval action; it must not implement semantic conflict grouping, choose a winner, suppress one side, or assign source authority. Final conflict grouping and interpretation remain Stage 5 responsibilities.

### Runtime state and trace state

V1 separates:

- **runtime state** — mutable request-lifetime orchestration control state;
- **trace state** — append-oriented history of interpretations, transitions, requests, results, retries, transformations, failures, budget use, and stop decisions.

Runtime state is ephemeral in V1. Durable/resumable workflow checkpoint recovery is not required.

Trace information must be retained sufficiently for Stage 7 evaluation and Stage 8 debugging/observability. Trace records structured decisions, inputs, outputs, reasons, state transitions, and budget events; it does not require arbitrary model chain-of-thought prose.

### Framework policy

V1 does not require LangGraph, OpenAI Agents SDK, or another general orchestration framework as an architectural dependency.

The initial implementation should use a minimal explicit application-layer state machine with typed executors and structured reasoning calls.

A framework may be adopted later without revisiting the semantic model if implementation evidence shows that workflow complexity, durability, distributed execution, human-in-the-loop checkpoints, or tracing requirements materially justify it.

## Consequences

### Positive

- Source-policy enforcement remains deterministic and testable.
- Mandatory web/local behavior cannot be silently optimized away by the agent.
- Concurrency can be used for latency without freezing scheduling into the semantic architecture.
- Agentic reasoning is used where semantic reasoning adds value without controlling safety/correctness boundaries.
- Infinite/unbounded loops are structurally prevented.
- Retry semantics become observable and evaluable.
- Intent-preservation rules become directly testable.
- Conflict follow-up remains possible without absorbing Stage 5 conflict semantics.
- Exact execution trajectories remain reproducible from explicit state/trace data.
- V1 avoids unnecessary durable workflow infrastructure.
- The architecture remains compatible with future orchestration frameworks if requirements grow.

### Negative

- Application code must implement explicit transition, budget, and trace plumbing.
- Some framework-provided conveniences are deferred.
- Bounded execution may stop before exhaustive research finds every useful source.
- Reformulation/decomposition quality becomes an additional evaluation surface.
- Intent-preservation validation requires explicit tests and structured transformation metadata.
- Future long-running/distributed workflows may require a runtime migration.

## Alternatives Considered

### Open-ended ReAct loop

Rejected for V1 because it gives the reasoning model excessive control over execution trajectory, complicates source-policy guarantees, increases loop/cost risk, and weakens deterministic evaluation.

### Fully static workflow

Rejected because ASTRAG needs bounded recovery from no-results, unresolved references/temporal anchors, query over-constraint, relevant degradation, and possible conflict signals.

### Mandatory local/web concurrency as an architectural invariant

Rejected. ADR-001 defines mandatory source execution, not scheduling topology. Concurrent execution is the preferred V1 implementation when practical, but semantic correctness depends on independent bounded source obligations rather than parallelism itself.

### LangGraph as mandatory V1 foundation

Viable, particularly for explicit graphs and future checkpointing, but deferred because V1 does not require durable workflows and the current state machine is small enough to implement directly without accepting framework coupling.

### OpenAI Agents SDK as primary orchestration architecture

Useful for model/tool execution and tracing, but not selected as the owner of Stage 4 control semantics because deterministic policy/budget/transition enforcement must remain explicit application behavior.

### One global retry count

Rejected because operational retries, local evidence-seeking attempts, web evidence-seeking attempts, rewrites, and decomposition have materially different cost/quality semantics.

### Durable checkpointing for every request

Rejected for V1 because requests are bounded interactive workflows. Persisted traces are required, but resume-from-checkpoint semantics add infrastructure without a current product requirement.

## Revisit Triggers

Revisit this ADR if:

- Stage 4 becomes a long-running research workflow,
- durable/resumable execution becomes a product requirement,
- human approval/checkpoints enter the workflow,
- distributed execution materially increases orchestration complexity,
- the number of tools/states grows enough that custom transitions become difficult to maintain,
- framework-level tracing/checkpointing demonstrably reduces complexity without weakening policy guarantees,
- evaluation shows current bounded ceilings prevent acceptable retrieval quality.

## Affected Stages

- Stage 4 — Agent / Orchestration Layer
- Stage 5 — Context Assembly
- Stage 7 — Evaluation Framework
- Stage 8 — Observability & Debugging
- Stage 9 — Guardrails & Reliability
- Stage 10 — Production / Serving

## Related Documents

- `NORTHSTAR.md`
- `docs/architecture/architecture.md`
- `docs/stages/01-problem-definition.md`
- `docs/stages/03-retrieval.md`
- `docs/stages/04-agent-orchestration.md`
- `docs/architecture/decisions/ADR-001-query-source-execution-policy.md`
- `docs/architecture/decisions/ADR-007-query-understanding-retrieval-boundary.md`
