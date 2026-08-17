# ADR-010: Evidence Gathering and Web Retrieval Contract

## Status

Proposed

## Context

Stage 4 coordinates local and web evidence gathering, while Stage 5 owns final evidence combination, semantic/source-level deduplication, corroboration semantics, conflict grouping, source grouping, ordering, token budgeting, sufficiency assessment, and final context selection.

Without a clear cross-stage contract, Stage 4 could accidentally flatten away retrieval lineage, force web sources into local-document identities, perform Stage 5 responsibilities prematurely, or couple downstream stages directly to a specific web provider.

ASTRAG also requires web evidence to support grounded generation. Search-engine snippets alone may be truncated, context-poor, or insufficient as authoritative evidence payloads.

Several viable designs were considered:

1. flatten all gathered evidence into one anonymous candidate list,
2. pass provider-specific local/web responses directly to Stage 5,
3. normalize all evidence into one rigid schema with fake local-style identities for web sources,
4. return a structured EvidenceGatheringResult with retrieval-run lineage, a small common evidence envelope, typed source-specific provenance, and a provider-neutral web retrieval boundary.

## Decision

ASTRAG adopts a structured **EvidenceGatheringResult** as the Stage 4 → Stage 5 contract.

The result preserves individual retrieval-run lineage and normalizes evidence at a common orchestration level without erasing source-specific provenance semantics.

### EvidenceGatheringResult

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

This allows Stage 5, evaluation, and observability to distinguish initial retrieval, operational retry outcomes, reformulation attempts, decomposition tasks, and source-specific failures.

### Orchestration completion is separate from retrieval outcome

Stage 4 reports orchestration-level completion independently from individual source outcomes.

Conceptual completion states include:

```text
COMPLETED
COMPLETED_DEGRADED
REJECTED
CLARIFICATION_REQUIRED
```

For example, if local retrieval succeeds and mandatory web retrieval persistently fails after bounded retries, Stage 4 may return `COMPLETED_DEGRADED` with successful local evidence and explicit web failure metadata.

Completion does not imply final answerability or sufficient evidence.

### Shared high-level source outcome model

Local and web source executions expose common high-level orchestration outcomes:

```text
SUCCESS_WITH_CANDIDATES
SUCCESS_NO_CANDIDATES
SUCCESS_DEGRADED
FAILURE
```

Source-specific metadata remains available beneath this common model.

Successful no-results and failure must never be conflated.

### Common evidence envelope

Stage 4 uses a small common evidence envelope:

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

The common envelope exists to let Stage 5 reason over gathered evidence without knowing Stage 4 control-flow internals.

It does not erase source-specific identity.

### Typed local provenance

Local evidence preserves the accepted Stage 2/3 identities and metadata, including as applicable:

```text
LocalProvenance
- corpus_id
- document_id
- document_version_id
- processing_generation_id
- search_representation_generation_id
- chunk_id
- page/section/source spans
- capability/degradation metadata
```

Canonical source text remains authoritative.

### Typed web provenance

Web evidence preserves external-source identity without pretending to be a local document:

```text
WebProvenance
- url
- canonical_url?
- source_name/domain
- publication_time?
- retrieved_at
- provider/source metadata as applicable
```

Web candidates do not receive fabricated `document_id`, `document_version_id`, or `chunk_id` values merely for schema symmetry.

### Provider-neutral Web Retrieval capability

Stage 4 depends on a logical provider-neutral web retrieval contract.

Conceptually:

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

The concrete V1 provider is replaceable. Provider-specific response schemas do not become Stage 5's evidence contract.

### Search and content acquisition form one logical web capability

Web retrieval may internally require:

```text
search
  -> result selection
  -> page/content acquisition
  -> normalization
```

Stage 4 treats this composition as one logical Web Retrieval capability rather than exposing low-level search/fetch mechanics as independent orchestration tools in V1.

This keeps provider/fetch mechanics replaceable and limits agent tool surface.

### Grounding-capable web evidence

A web evidence candidate must contain usable evidence text suitable for downstream grounding.

A search-engine snippet may be retained as metadata but is not sufficient as the authoritative evidence payload when it cannot reliably support downstream factual grounding.

The concrete acquisition method may vary by provider and implementation as long as the logical contract is satisfied.

### Typed web temporal semantics

Web temporal constraints must preserve semantic distinctions.

In particular, event/content time is not equivalent to page publication/source time.

A query about an event in 1945 must not automatically be converted into a requirement that web pages themselves were published in 1945.

Provider-supported publication/recency filters may be used only when they match the typed query constraint.

Temporal uncertainty and original interpretation metadata remain available downstream.

### Domain constraints without implicit authority policy

The web contract may support domain constraints when query/product semantics or an accepted bounded strategy require them.

V1 does not introduce an implicit trusted-domain list, authority score, preferred-site truth policy, or domain-based factual winner selection.

Source-authority ranking remains deferred unless separately accepted.

### Failure normalization

Cross-source failure metadata conceptually includes:

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

Stable failure classes include concepts such as:

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

Provider-native details remain available for diagnostics without controlling global orchestration semantics.

Executor outputs that violate the expected contract fail explicitly as `MALFORMED_TOOL_RESPONSE`; Stage 4 does not invent missing provenance or substantive evidence fields.

### Partial success and degraded gathering

A persistent failure of one required source does not discard successful evidence from another required source.

Stage 4 preserves:

- successful candidates,
- failed/degraded source identity,
- failure metadata,
- required-source execution status,
- final orchestration completion status.

If all required sources fail, Stage 4 returns the structured failure/degraded gathering state and does not substitute pretrained model knowledge as factual evidence.

### Identity-level consolidation only

Stage 4 may consolidate operationally identical evidence while retaining all retrieval-run associations.

Examples include:

- the same local canonical `chunk_id` returned across multiple Stage 4 attempts,
- the exact same confidently normalized web URL/result identity returned by repeated web attempts.

Stage 4 does not perform semantic duplicate detection, copied-source analysis, independent corroboration judgment, or final source-level deduplication. Those remain Stage 5 responsibilities.

### Conflict boundary

Stage 4 preserves contradictory evidence and may perform bounded follow-up retrieval under ADR-009 when conflict is a valid evidence-seeking trigger.

It does not choose which claim is true, suppress one side, group final conflicts, or assign final authority.

### Retrieved content is data, not control

All local/web evidence is data-plane content.

Retrieved text cannot modify:

- EvidencePolicy,
- source permissions,
- orchestration budgets,
- legal state transitions,
- tool permissions,
- system/control instructions.

Stage 9 may add defense-in-depth mechanisms, but this control/data separation is part of the Stage 4 contract.

## Consequences

### Positive

- Stage 5 receives enough lineage to evaluate and combine evidence without understanding the Stage 4 state-machine implementation.
- Local and web evidence share useful common fields without fabricating identities.
- Provider replacement does not force downstream schema changes.
- Web evidence is grounding-capable rather than snippet-dependent.
- Successful evidence survives independent source failures.
- No-results and failures remain distinguishable.
- Retry/reformulation/decomposition effects remain observable.
- Stage 4 cannot silently absorb Stage 5 semantic deduplication, corroboration, conflict, or sufficiency responsibilities.
- Prompt-injection boundaries are clearer because retrieved content is structurally data-plane input.

### Negative

- EvidenceGatheringResult and typed provenance schemas are richer than a flat candidate list.
- Web content acquisition may increase latency, external calls, and cost.
- Provider-normalization code must preserve both common and provider-specific metadata.
- Stage 5 must still perform semantic deduplication/corroboration across potentially redundant local/web evidence.
- Canonical URL identity may be imperfect and must not be mistaken for semantic duplicate certainty.

## Alternatives Considered

### Flatten all candidates before Stage 5

Rejected because it destroys run/reformulation/source-failure lineage and makes evaluation/reproduction harder.

### Pass provider-native responses directly downstream

Rejected because it couples Stage 5/6 to Stage 3 internals and the current web provider.

### Force one rigid evidence schema

Rejected because web evidence does not naturally have local corpus/document/version/chunk identities and fabricating those fields would weaken provenance semantics.

### Snippet-only web evidence

Rejected because snippets may not contain enough authoritative text for grounded context assembly and generation.

### Stage 4 semantic deduplication/corroboration

Rejected because Stage 5 already owns final duplicate, corroboration, source grouping, and conflict semantics.

### Separate agent-visible search and fetch tools

Deferred for V1. Exposing low-level web mechanics would increase orchestration complexity and tool surface without a demonstrated need.

### Implicit trusted-domain policy

Rejected because Stage 1 explicitly defers source-authority ranking and Stage 4 should not introduce it indirectly through web orchestration.

## Revisit Triggers

Revisit this ADR if:

- Stage 5 requires materially different evidence lineage for correct context assembly,
- the web provider cannot reliably provide/acquire grounding-capable content,
- a future product mode exposes separate search/browse/fetch tools to the agent,
- source-authority ranking becomes an accepted requirement,
- canonical URL identity proves inadequate for operational consolidation,
- future source classes require extending the common envelope/provenance type model.

## Affected Stages

- Stage 4 — Agent / Orchestration Layer
- Stage 5 — Context Assembly
- Stage 6 — Generation Layer
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
- `docs/architecture/decisions/ADR-003-temporal-evidence-representation.md`
- `docs/architecture/decisions/ADR-006-temporal-query-retrieval-policy.md`
- `docs/architecture/decisions/ADR-007-query-understanding-retrieval-boundary.md`
- `docs/architecture/decisions/ADR-009-v1-bounded-orchestration-execution-model.md`
