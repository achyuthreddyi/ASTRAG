# ADR-001: Query Source Execution Policy

## Status

Accepted

## Context

ASTRAG supports evidence retrieval from two source classes:

- user-selected document corpora,
- external web search.

During Stage 1, two viable V1 policies were considered for web execution:

1. **Agent-decided web invocation** — enabling web gives the agent permission to search the web, but the agent may skip web search when local evidence appears sufficient.
2. **Query-controlled mandatory web invocation** — enabling web means web retrieval is always performed for that query. If corpora are also selected, both source classes are searched.

The original North Star leaned toward agent-decided web invocation. Stage 1 introduced an explicit per-query web toggle and a research-quality product target where correctness, grounding, and predictable evidence behavior are prioritized above latency.

The source configuration also acts as a user-visible evidence boundary. Allowing the agent to reinterpret an enabled web toggle would make the meaning of that boundary less predictable and complicate evaluation of source-selection behavior.

## Decision

For V1, ASTRAG uses **query-controlled mandatory web invocation**.

The execution matrix is:

| Selected corpora | Web | Required behavior |
| --- | --- | --- |
| One or more | OFF | Search only the selected corpora |
| One or more | ON | Search the selected corpora and the web |
| None | ON | Search the web only |
| None | OFF | Reject the query because no evidence source is available |

Additional invariants:

- Unselected corpora must never provide factual evidence for the query.
- The agent may choose retrieval strategies, query transformations, ranking, retries, evidence combination, and stopping behavior within the configured source boundary.
- The agent must not override the query's corpus selection or web setting.
- When web is disabled, model knowledge may assist reasoning but cannot substitute for missing retrieved factual evidence.
- A failure of one configured source may degrade gracefully to evidence from another successful configured source, but the failure must be disclosed.

The concrete web-search provider is not part of this ADR. Tavily is the current intended V1 implementation provider and may be replaced without revisiting this decision.

## Consequences

### Positive

- The web toggle has deterministic, user-visible semantics.
- Hybrid queries are easier to test and evaluate consistently.
- Research-quality queries receive web evidence whenever the user explicitly requests it.
- Stage 4 orchestration does not need to infer whether an enabled web source should actually be invoked.
- Source-boundary violations are easier to detect in evaluation and tracing.

### Negative

- Web-enabled queries incur web-search cost even when corpus evidence would have been sufficient.
- Web-enabled queries may have higher latency.
- Some queries will retrieve redundant evidence from both local and web sources.
- Context assembly must handle duplicates and conflicts across source classes.

## Alternatives Considered

### Agent-Decided Web Invocation

Web search would be available but optional when enabled.

Rejected for V1 because it weakens the explicit meaning of the user's source configuration and makes behavior less deterministic. It may be reconsidered after the V1 evaluation framework can reliably measure when web retrieval is unnecessary.

### Rich Source-Mode Selector

Expose modes such as local-only, web-only, hybrid, or agent-decides.

Deferred because it adds product and orchestration complexity before the basic corpus/web contract has been validated.

## Revisit Triggers

Revisit this ADR if:

- web-search cost becomes materially problematic,
- web latency becomes a product bottleneck,
- evaluation shows that mandatory web retrieval harms answer quality,
- users require explicit web-only or agent-decided modes while corpora are selected,
- or a reliable sufficiency classifier demonstrates that adaptive web invocation preserves quality while materially reducing cost or latency.

## Affected Stages

- Stage 3 — Retrieval Pipeline
- Stage 4 — Agent / Orchestration Layer
- Stage 5 — Context Assembly
- Stage 6 — Generation Layer
- Stage 7 — Evaluation Framework
- Stage 8 — Observability & Debugging
- Stage 9 — Guardrails & Reliability

## Related Documents

- `NORTHSTAR.md`
- `docs/stages/01-problem-definition.md`
- `docs/architecture/architecture.md`
