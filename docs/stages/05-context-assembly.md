# Stage 5: Context Assembly

## Status

**Architecture Ready — Awaiting Orchestrator Review.**

Stage 5 semantics have been consolidated in this document. Stage 5 must not be marked **Implementation Ready** until proposed ADR-011, ADR-012, ADR-013, the Stage 4 contract deltas, and the prompt-construction ownership clarification are reviewed and accepted by the orchestrator.

Stage 5 is designed against the current Stage 4 working contract on `agent/stage-4-orchestration-architecture`. Stage 4 itself is still Architecture Ready and ADR-009/ADR-010 are still Proposed, so Stage 5 must reconcile against their accepted forms before implementation.

## Objective

Transform a completed Stage 4 `EvidenceGatheringResult` into the smallest safe, provenance-complete, temporally coherent, conflict-preserving, duplicate-aware structured context package required for Stage 6 grounded generation.

Stage 5 is the final evidence-preparation boundary before generation. It determines what gathered evidence is usable, how evidence relationships affect corroboration, how conflicts and coverage are represented, which evidence fits the context budget, and whether the supported evidence is sufficient for a full or partial answer.

Conceptually:

```text
EvidenceGatheringResult
        ↓
Validate Assembly Eligibility
        ↓
Normalize Evidence Without Flattening Provenance
        ↓
Analyze Evidence Relationships / Duplicates
        ↓
Analyze Independence / Corroboration
        ↓
Group Material Conflicts
        ↓
Map Question Coverage
        ↓
Reassess Final Context Utility
        ↓
Organize Temporal Evidence
        ↓
Apply Soft Diversity Controls
        ↓
Allocate Context Budget
        ↓
Select / Extract Context
        ↓
Assess Sufficiency
        ↓
GenerationContext
        ↓
Stage 6
```

## Scope

Stage 5 owns:

- validation of Stage 4 assembly inputs,
- evidence normalization for context assembly,
- exact/semantic/derivative evidence relationship analysis,
- independent corroboration semantics,
- conflict detection and grouping,
- semantic coverage tracking,
- final evidence relevance/usefulness reassessment,
- source/document/domain/task diversity control,
- temporal grouping and ordering,
- context token budgeting,
- context selection,
- provenance-preserving extractive trimming,
- final evidence sufficiency assessment,
- unsupported/partial-answer state,
- structured Stage 5 -> Stage 6 `GenerationContext`,
- Stage 5 evaluation hooks,
- Stage 5 observability hooks.

## Non-Goals

Stage 5 does not own:

- Stage 2 ingestion, canonical evidence creation, versioning, or publication,
- Stage 3 dense/lexical/temporal retrieval mechanics,
- Stage 3 RRF or retrieval-profile internals,
- Stage 4 query understanding, retries, decomposition, reformulation, source execution, or stopping,
- initiating new retrieval after Stage 4 completion,
- fetching adjacent chunks or other new datastore evidence in V1,
- source-authority ranking or trusted-domain truth policy,
- majority-vote truth selection,
- choosing a winner among materially conflicting claims in V1,
- generative/LLM evidence summarization in V1,
- final answer wording,
- final citation rendering,
- final response formatting,
- user-facing conflict/uncertainty prose,
- long-running/distributed context-assembly infrastructure.

## Requirements

### Evidence boundary

Only evidence permitted by the current immutable `EvidencePolicy` may enter `GenerationContext`.

Stage 5 must revalidate the source boundary at assembly time. Any candidate outside selected corpora or violating the current web policy is unusable and must be rejected with a structured contract-violation trace. Stage 5 never expands the legal source set.

### Provenance

Every selected context item must remain traceable to authoritative evidence provenance and Stage 4 retrieval lineage.

Stage 5 must not fabricate missing local IDs, web identities, citation targets, temporal values, or lineage.

### Temporal semantics

Temporal origin, semantic role, precision, certainty, BCE/CE semantics, source wording, and unresolved temporal state survive context assembly.

Source/publication time is not event/content time. Approximate or uncertain dates must not become falsely exact during ordering or extraction.

### Conflict preservation

Materially incompatible factual claims and supported interpretation divergences remain visible as structured competing claims.

Stage 5 does not silently reconcile, suppress, majority-vote, or nominate a factual winner in V1.

### Duplicate/corroboration safety

Repeated, copied, syndicated, or derivative evidence must not count as independent corroboration merely because it appears in multiple documents, URLs, domains, corpora, or retrieval runs.

### Partial answers

Supported portions of compound/timeline questions remain usable even when other portions are unsupported. Stage 5 explicitly represents supported and unsupported aspects for Stage 6.

## Assumptions

- ADR-001 through ADR-008 are accepted and authoritative.
- Stage 4's current architecture and ADR-009/ADR-010 are the working upstream contract pending orchestrator acceptance.
- V1 is single-tenant, low concurrency, bounded-candidate, interactive.
- Exact context token budgets and tuning weights are versioned configuration, not architectural constants.
- Stage 6 will consume structured `GenerationContext` and own final generation instructions, answer synthesis, formatting, and citation rendering if the proposed boundary is accepted.

## Inputs

Stage 5 consumes a structured Stage 4 result conceptually equivalent to:

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

Each retrieval run should preserve enough lineage to distinguish mandatory execution, retries, reformulations, decomposition, anchor recovery, and conflict follow-up:

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

Evidence candidates conceptually include:

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

`content_acquisition` is especially relevant for web evidence and should expose completeness semantics such as `FULL`, `PARTIAL`, or `UNKNOWN` where applicable.

## Input Validation

### Completion-state behavior

- `COMPLETED` is eligible for normal assembly.
- `COMPLETED_DEGRADED` is eligible for normal assembly; degradation propagates.
- `CLARIFICATION_REQUIRED` does not enter normal evidence assembly and produces a non-applicable assembly result.
- `REJECTED` does not enter normal evidence assembly and produces a non-applicable assembly result.

Stage 5 may assemble when one required source succeeded and another failed, provided Stage 4 completed its bounded execution obligations and preserved the failure/degradation state.

### Candidate validity

A candidate is unusable when required provenance, legal source identity, authoritative evidence text, or other contract-critical fields are missing or malformed.

Missing optional metadata may degrade a candidate without invalidating it. Examples include unknown publication time or absent optional temporal annotations.

Invalid candidates may be dropped individually when safe evidence remains. If corruption is widespread enough that Stage 5 cannot safely construct a provenance-complete context, assembly fails rather than inventing missing fields.

### Empty evidence

A structurally valid completed gathering result containing no usable evidence is not a Stage 5 internal error. Stage 5 may return an assembled context with `INSUFFICIENT` evidence.

## Evidence Normalization

Stage 5 may create an internal `ContextCandidate` analytical view, but normalization must not impose fake symmetry between local and web sources.

Conceptually:

```text
ContextCandidate
- evidence_id
- source_type
- source_text
- source_provenance
- temporal_metadata[]
- retrieval_lineage[]
- acquisition_completeness?
- degradation[]
- upstream_ranking_signals
- coverage_links[]
```

Local provenance retains corpus/document/version/generation/chunk identities. Web provenance retains external URL/source/domain identity. Normalization is for analysis, not identity replacement.

## Evidence Relationship and Duplicate Semantics

Stage 5 distinguishes five evidence-dependence states:

```text
SAME_IDENTITY
EXACT_DUPLICATE
DERIVATIVE
INDEPENDENT
UNKNOWN_DEPENDENCE
```

### Same identity

The same canonical local chunk or confidently identical canonical web resource is one evidence identity regardless of how many Stage 4 runs returned it.

### Exact duplicate

Different source identities may contain substantially identical evidence payloads. Different uploaded documents containing copied text still form one corroborative unit for that copied information.

### Derivative

Syndicated, mirrored, copied, lightly rewritten, or otherwise materially derivative sources belong to the same dependency family when derivation is reasonably suspected.

V1 uses a conservative policy: suspected derivation prevents counting the members as independent corroboration unless independence is reasonably established.

### Independent

Independent evidence means Stage 5 has adequate basis to treat the supporting information as not known to derive from the same underlying information source.

Different URL, domain, document, corpus, or retrieval run does not by itself prove independence.

### Unknown dependence

When Stage 5 cannot safely establish whether two sources are independent, it records `UNKNOWN_DEPENDENCE` rather than upgrading uncertainty to independence.

Stage 6 may describe such items as multiple sources but must not describe them as multiple independent sources based solely on this relationship.

### Relationship representation

Conceptually:

```text
EvidenceRelationshipGroup
- group_id
- relationship_type
- member_evidence_ids[]
- representative_evidence_id?
- alternate_provenance[]
- relationship_basis[]
```

Stage 5 normally selects one textual representative from exact/derivative duplicate families while retaining alternate provenance and retrieval lineage. Additional family members are retained only when they contribute materially distinct useful context or provenance.

V1 does not introduce a numeric corroboration-confidence score.

## Corroboration Semantics

Corroboration is descriptive and structural, not a calibrated truth probability.

Stage 5 may expose:

```text
supporting_evidence_ids[]
independent_support_units[]
dependency_groups[]
dependence_uncertain
```

Raw evidence count is never treated as independent-support count.

Stage 5 does not introduce source-authority ranking, domain trust scoring, or majority-vote factual selection.

## Conflict Handling

Stage 5 classifies material evidence relationships using:

```text
FACTUAL_CONFLICT
QUANTITATIVE_CONFLICT
TEMPORAL_CONFLICT
INTERPRETATION_DIVERGENCE
NOT_A_CONFLICT
```

### Materiality

Textual differences are not automatically conflicts. A discrepancy becomes a conflict when the claims are materially incompatible for the user's question or requested coverage unit.

### Interpretation divergence

Different supported explanations or historical interpretations are distinct from factual contradiction. Stage 5 preserves these viewpoints without requiring one to be false.

### No preferred claim in V1

Stage 5 does not nominate a preferred or winning claim in V1, even if one side has more independent supporting evidence. Evidence-support structure may be exposed descriptively, but truth selection is not inferred from count alone.

### Conflict representation

Conceptually:

```text
ConflictGroup
- conflict_id
- conflict_type
- proposition_or_topic
- materiality_basis
- competing_claims[]
- supporting_evidence_ids_by_claim
- coverage_unit_ids[]
```

Conflict is orthogonal to sufficiency. For example, evidence may be sufficient to answer while `conflicts_present = true`.

## Coverage Model

Stage 5 explicitly tracks semantic coverage units for the material parts of the question.

Coverage units originate from the original/resolved question and Stage 4 decomposition. Stage 5 may consolidate overlapping Stage 4 tasks into the same coverage unit but must not freely invent unrelated answer requirements.

Conceptually:

```text
CoverageUnit
- coverage_id
- description
- support_status
- conflicts_present
- supporting_evidence_ids[]
- missing_aspects[]
- source/task_lineage[]
```

Support states:

```text
SUPPORTED
PARTIALLY_SUPPORTED
UNSUPPORTED
```

Conflict remains an orthogonal flag.

Timeline/range questions may contain multiple temporal coverage units or segments. Meaningful missing requested periods may make the overall result partially sufficient.

## Relevance / Context Utility Reassessment

Stage 5 performs a final context-usefulness reassessment because the complete gathered evidence may combine:

- multiple Stage 3 runs,
- multiple decomposition tasks,
- query reformulations,
- local and web evidence,
- conflicting evidence,
- retrieval results whose upstream scores are not directly comparable.

V1 does not require an LLM judge or learned reranker.

Initial structured signals include:

- upstream retrieval rank/signals,
- coverage-unit match,
- temporal relevance,
- evidence relationship/duplicate status,
- conflict participation,
- acquisition completeness,
- degradation state,
- provenance completeness.

Exact weighting/rules are implementation/evaluation configuration.

Learned reranking should be reconsidered only if evaluation shows that useful evidence is consistently gathered but poorly selected under the practical context budget.

## Retrieval-Run Lineage Use

Retrieval-run lineage is used to:

- map evidence to coverage units/tasks,
- preserve why evidence was gathered,
- distinguish retries/reformulations/decomposition paths,
- avoid treating repeated retrieval as repeated corroboration,
- support evaluation and debugging.

The number of times evidence was retrieved does not increase independent support.

Stage 6 does not need raw Stage 4 retrieval runs for normal generation; Stage 5 preserves enough lineage references for traceability.

## Diversity

Diversity is a soft context-quality control, not a quota system.

Stage 5 should avoid pathological domination by:

- one document,
- one corpus where multiple selected corpora contain useful evidence,
- one web domain,
- one duplicate/dependency family,
- one retrieval task.

Soft diversity pressure must not displace clearly stronger or uniquely necessary evidence solely to create cosmetic variety.

V1 has no fixed local/web split and no mandatory per-corpus/per-document token quota.

A required source may contribute zero selected context items when its evidence is weak/redundant, while its execution/failure/degradation status still propagates to Stage 6.

## Temporal Organization

Context ordering is query-sensitive rather than universally chronological.

### Timeline/date-range queries

Primarily chronological organization, while preserving approximate/uncertain placement and unresolved temporal segments.

### Exact fact lookups

Primarily relevance/usefulness ordering.

### Before/after queries

Organization centers on the anchor and requested temporal relation.

### Conflict-focused evidence

Competing claims remain grouped when conflict comparison is more useful than strict chronology.

### Temporal uncertainty

Approximate or uncertain dates retain their precision/certainty. Stage 5 does not assign fake exact ordering when evidence only supports coarse/uncertain placement.

Temporally unresolved evidence may still be selected, but its unresolved state remains explicit.

### Structured timeline

For timeline-like questions, Stage 5 may produce structured timeline entries for Stage 6. Stage 5 does not generate narrative timeline prose.

## Token Budgeting

Context token budget is versioned configuration.

Stage 5 owns allocation within the generation-context budget. Allocation prioritizes:

1. material question coverage,
2. preservation of material conflict sides,
3. independent evidence,
4. temporal completeness when relevant,
5. provenance metadata necessary for grounding/citations.

No fixed local/web/document/corpus quotas are architectural requirements.

Exact token values, reserve sizes, tuning weights, and profile-specific allocations are implementation/evaluation configuration.

## Context Selection

Every candidate considered for final context receives a structured selection decision.

Conceptually:

```text
ContextSelectionDecision
- evidence_id
- selected
- reasons[]
```

Example reason concepts:

```text
SELECTED_PRIMARY
SELECTED_COVERAGE
SELECTED_INDEPENDENT_SUPPORT
SELECTED_CONFLICT_SIDE
SELECTED_TEMPORAL_SEGMENT
DROPPED_DUPLICATE
DROPPED_REDUNDANT
DROPPED_LOW_RELEVANCE
DROPPED_DIVERSITY_PRESSURE
DROPPED_DEGRADED_CONTENT
DROPPED_INVALID_PROVENANCE
DROPPED_BUDGET
DROPPED_POLICY_VIOLATION
```

The reason taxonomy is versioned and extensible.

## Evidence Compression Policy

V1 does not use generative/LLM summarization for source evidence.

Stage 5 may perform provenance-preserving extractive trimming or passage selection to reduce token cost.

Any selected text must expose extent semantics such as:

```text
FULL
EXTRACTED
```

An extracted passage must retain exact lineage to its original evidence span and must not masquerade as complete/full source content.

Generated summaries may be reconsidered in a future ADR if evaluation shows extractive selection is insufficient and the architecture can preserve derived-text status and compression lineage safely.

## Neighboring Context

Stage 5 performs no new datastore retrieval or adjacent-chunk fetch in V1.

Already-gathered parent/neighbor text or metadata may be used only if it is already part of the Stage 4 evidence contract. New evidence acquisition would cross the accepted Stage 4 completion boundary and requires an explicit future architecture change.

## Sufficiency Assessment

Sufficiency is semantic rather than count-based.

Overall states:

```text
SUFFICIENT
PARTIALLY_SUFFICIENT
INSUFFICIENT
```

`SUFFICIENT` means the material requested aspects are supported strongly enough for grounded generation under the current evidence policy. It does not mean a minimum chunk count was reached.

A required-source failure does not automatically force `INSUFFICIENT` if remaining permitted evidence still supports the material requested aspects. The failure remains visible downstream.

Stage 5 returns explicit supported and unsupported aspects so Stage 6 does not need to rediscover coverage from prose.

Conceptually:

```text
SufficiencyAssessment
- status
- coverage_units[]
- supported_aspects[]
- unsupported_aspects[]
- conflicts_present
- source_failures[]
- degraded_sources[]
- rationale_codes[]
```

## Assembly Outcome Model

Assembly execution status is distinct from evidence sufficiency.

Conceptually:

```text
ContextAssemblyResult
- assembly_status
- generation_context?
- failure?
```

Assembly states:

```text
ASSEMBLED
NOT_APPLICABLE
FAILED
```

Examples:

- valid empty evidence -> `ASSEMBLED + INSUFFICIENT`,
- all required sources failed but Stage 4 result is structurally valid -> may be `ASSEMBLED + INSUFFICIENT`,
- `CLARIFICATION_REQUIRED` -> `NOT_APPLICABLE`,
- `REJECTED` -> `NOT_APPLICABLE`,
- malformed Stage 4 contract -> `FAILED`,
- provenance corruption preventing safe packaging -> `FAILED`,
- internal Stage 5 processing failure -> `FAILED`.

If the configured context budget is too small to represent minimum material supported evidence safely, including necessary conflict sides and coverage, Stage 5 returns `FAILED` with a specific context-budget reason rather than silently dropping critical evidence.

## Stage 6 Handoff Contract

Stage 5 returns a formal structured `GenerationContext`.

Conceptually:

```text
GenerationContext
- query_id
- original_question
- resolved_query
- evidence_policy
- sufficiency_assessment
- context_items[]
- evidence_relationship_groups[]
- conflict_groups[]
- coverage_units[]
- timeline?
- required_source_statuses[]
- source_failures[]
- degraded_sources[]
- interpretation_assumptions[]
- assembly_metadata
```

Each selected item conceptually includes:

```text
ContextItem
- context_item_id
- representative_evidence_id
- related_evidence_ids[]
- selected_text
- text_extent
- source_type
- source_provenance
- temporal_metadata[]
- coverage_unit_ids[]
- evidence_relationship_group_id?
- conflict_group_ids[]
- selection_reasons[]
- ordering_metadata
- retrieval_lineage_refs[]
```

Stage 6 should not require raw Stage 4 retrieval runs for normal generation.

Stage 6 receives enough structured metadata to:

- ground material claims,
- produce supported partial answers,
- disclose conflicts,
- avoid false independent-corroboration statements,
- disclose source failures/degradation,
- render citations from real source provenance,
- abstain where coverage is unsupported.

Stage 5 does not fabricate citation targets.

## Prompt Construction Boundary

Stage 5 proposes a cleaner boundary than the historical wording in `stages.md`:

```text
Stage 5 -> structured GenerationContext
Stage 6 -> system/generation instructions + GenerationContext -> LLM
```

Under this proposal, Stage 6 owns:

- system/generation prompt construction,
- grounding instructions,
- response-format instructions,
- final citation-rendering instructions,
- natural-language answer generation.

This is a cross-stage/global architecture clarification because `stages.md` currently lists prompt construction as a Stage 5 responsibility. It requires orchestrator review before becoming accepted architecture.

## Failure / Degraded Behavior

### Malformed EvidenceGatheringResult

`FAILED`. Stage 5 does not repair contract-critical missing fields by inference.

### Missing candidate provenance

The candidate is invalid and dropped. If safe context can still be assembled, assembly continues with degradation metadata. If provenance loss prevents safe packaging materially, assembly fails.

### Empty evidence

`ASSEMBLED + INSUFFICIENT` when the input is structurally valid.

### Only degraded evidence

Assembly may proceed. Degradation affects selection/sufficiency and propagates to Stage 6.

### Partial web content

May be usable when the selected text itself supports the required claim and provenance is valid. Acquisition completeness remains visible. Stage 5 must not treat `PARTIAL` as `FULL`.

### All required sources failed

May still produce `ASSEMBLED + INSUFFICIENT` if the Stage 4 result is structurally valid and contains no usable evidence.

### Duplicate-only apparent corroboration

Context may still be supported by one corroborative unit, but duplicates do not increase independence. Sufficiency depends on the semantic needs of the question, not duplicate count.

### Unresolved conflict

Conflict is preserved. It does not automatically make the evidence insufficient.

### Context budget too small

`FAILED` with a specific budget/assembly reason when critical supported evidence cannot be represented safely.

## Evaluation Criteria

Stage 5 evaluation must include at least:

- provenance retention rate,
- false independent-corroboration rate,
- evidence-relationship classification quality,
- conflict preservation rate,
- coverage classification accuracy,
- sufficiency classification accuracy,
- context precision,
- context coverage/recall,
- duplicate-token reduction without loss of unique provenance,
- temporal organization correctness,
- unsupported/policy-violating evidence inclusion rate,
- context-budget efficiency,
- assembly latency,
- assembly cost where applicable.

Target invariants include effectively 100% provenance retention for selected context, zero known source-boundary violations, and zero false independent corroboration on deterministic duplicate/derivative benchmark cases.

Benchmark cases should cover:

- single-fact lookup,
- multi-source corroboration,
- copied local documents,
- local copy plus original web source,
- syndicated/rewritten web evidence,
- uncertain dependency,
- conflicting dates,
- conflicting quantitative claims,
- supported interpretation divergence,
- timeline/range queries,
- BCE/CE and approximate dates,
- missing timeline segments,
- multi-corpus evidence,
- local + web hybrid evidence,
- one required source failure,
- partial web acquisition,
- decomposed compound questions,
- insufficient evidence,
- duplicate-only apparent corroboration,
- malformed provenance,
- context-budget exhaustion.

## Observability

Structured traces should include at least:

```text
input_candidate_count
valid_candidate_count
invalid_candidate_count
relationship_groups[]
conflict_groups[]
coverage_units[]
relevance_reassessment
selection_decisions[]
drop_reasons[]
ordering_strategy
token_budget
token_allocation
selected_token_count
sufficiency_assessment
assembly_status
source_failures[]
degraded_sources[]
configuration_version
assembly_latency
```

Stage 5 traces structured decisions and reasons. It does not persist arbitrary model chain-of-thought.

## Scalability

V1 assumes bounded candidate sets from Stage 4, one primary user, low concurrency, and interactive use.

Stage 5 should initially be implemented as an application-layer component/service boundary rather than distributed context-assembly infrastructure.

Revisit scaling architecture if candidate volume, concurrency, semantic relationship analysis, or learned reranking/compression becomes a measured bottleneck.

## Latency / Throughput Requirements

Stage 5 should remain a bounded fraction of interactive request latency. Exact latency targets require benchmark data and are configuration/evaluation concerns rather than current architecture constants.

Costly model-based reranking or summarization is not part of the V1 baseline. Relationship/conflict/coverage mechanisms should be benchmarked for quality first and optimized only when measured latency requires it.

## Alternatives Considered

### Trust upstream retrieval ordering entirely

Rejected because Stage 5 receives heterogeneous evidence across runs, tasks, source classes, conflict states, and duplicate families whose upstream ranks are not globally comparable.

### LLM judge for all evidence selection

Deferred because it adds cost, latency, nondeterminism, and another hallucination surface before deterministic/structured signals are benchmarked.

### Raw URL/document count as corroboration

Rejected because copied/syndicated evidence would create false independence.

### Binary independent/not-independent relationship model

Rejected because uncertain dependence must not silently become independence.

### Majority-vote conflict resolution

Rejected because source count is not factual authority and duplicate families distort counts.

### Global chronological ordering

Rejected because chronology is appropriate for timeline/range questions but not every query.

### Fixed local/web quotas

Rejected because source execution obligations do not imply equal final-context representation.

### Generative evidence summarization in V1

Deferred because generated summaries are derived text and create additional provenance/faithfulness risks.

### Stage 5 adjacent-chunk retrieval

Rejected for V1 because it crosses the completed Stage 4 evidence-gathering boundary.

## Key Design Decisions

1. Stage 5 distinguishes evidence identity, exact duplicates, derivative evidence, independent evidence, and unknown dependence.
2. Different documents containing copied evidence count as one corroboration unit for that evidence.
3. V1 uses a conservative derivative policy: suspected derivation does not count as independent corroboration.
4. Unknown dependence remains explicit rather than being upgraded to independence.
5. Duplicate/derivative families normally use one representative text plus alternate provenance.
6. V1 uses no numeric corroboration-confidence score.
7. Material conflicts are categorized as factual, quantitative, temporal, or interpretation divergence.
8. Interpretation divergence is distinct from factual contradiction.
9. Conflict is orthogonal to sufficiency.
10. Stage 5 does not nominate a preferred conflict claim in V1.
11. Minor discrepancies become conflicts only when material to the question.
12. Stage 5 explicitly tracks semantic coverage units derived from the resolved question and Stage 4 decomposition.
13. Coverage states are supported, partially supported, or unsupported; conflict remains orthogonal.
14. Overall sufficiency is sufficient, partially sufficient, or insufficient.
15. Required-source failure does not automatically force insufficiency.
16. Sufficiency is based on material requested aspects, not chunk count.
17. Timeline gaps may produce partial sufficiency.
18. Stage 5 returns explicit supported and unsupported aspects.
19. Stage 5 performs final context-usefulness reassessment.
20. V1 uses structured/deterministic signals before learned/LLM reranking.
21. Diversity is soft and not quota-driven.
22. No fixed local/web context split exists.
23. Required-source execution/failure state propagates even when that source contributes no selected context item.
24. Every candidate receives a structured selection/drop reason.
25. Context ordering is query-sensitive rather than universally chronological.
26. Timeline/range queries are primarily chronological; fact lookup is relevance-first; before/after queries organize around the anchor.
27. Conflict grouping may override strict chronological grouping where necessary.
28. Temporal uncertainty, origin, and unresolved state survive ordering.
29. Stage 5 may produce structured timeline entries but not narrative timeline prose.
30. Context budget values are versioned configuration.
31. Allocation prioritizes material coverage, conflict preservation, independence, temporal completeness, and provenance.
32. V1 has no fixed source/document quotas.
33. V1 has no generative/LLM evidence summarization.
34. Provenance-preserving extractive trimming is permitted.
35. Extracted text retains exact source lineage and explicit extent status.
36. Stage 5 performs no new adjacent-chunk/datastore retrieval in V1.
37. Budget inability to preserve minimum material evidence safely is an assembly failure, not silent evidence dropping.
38. `COMPLETED` and `COMPLETED_DEGRADED` are assembly-eligible.
39. `CLARIFICATION_REQUIRED` and `REJECTED` are not normal assembly inputs.
40. Empty valid evidence produces assembled insufficiency rather than internal failure.
41. Missing required provenance invalidates the candidate; widespread unsafe corruption fails assembly.
42. Stage 5 revalidates the immutable evidence boundary.
43. Assembly execution status is separate from evidence sufficiency.
44. Assembly states are assembled, not applicable, and failed.
45. Stage 5 -> Stage 6 uses a formal structured `GenerationContext`.
46. Stage 6 does not need raw Stage 4 retrieval runs for normal generation.
47. Stage 6 receives structured conflicts, coverage, sufficiency, duplicate/dependence semantics, required-source failures, and degradation.
48. Stage 5 proposes structured-context-only ownership; Stage 6 owns final prompt construction and answer generation, subject to orchestrator acceptance.

## Exact Stage 4 Contract Deltas Required

The current Stage 4/ADR-010 working contract is close but not fully sufficient for the accepted Stage 5 semantics.

The following deltas should be reviewed and incorporated into Stage 4/ADR-010 before Stage 5 implementation:

### 1. Add `required_source_statuses[]` explicitly to `EvidenceGatheringResult`

Stage 4 already defines `RequiredSourceStatus`, but ADR-010's top-level conceptual result currently omits the field.

Stage 5 requires explicit required-versus-attempted/completed/outcome state so source execution obligations remain visible independently from selected context.

### 2. Make retrieval-task identity explicit on every `RetrievalRun`

Add/confirm:

```text
- task_id
- parent_task_id?
```

Stage 5 uses this for coverage mapping and must not infer task identity from free-form queries.

### 3. Add explicit run-kind semantics

Add/confirm:

```text
- run_kind
```

This should distinguish at least initial mandatory execution from operational retry and evidence-seeking executions as needed for trace semantics.

### 4. Preserve parent-run / transformation lineage

Add/confirm:

```text
- parent_run_id?
- trigger_reason?
- query_transform_id?
```

These fields let Stage 5/evaluation distinguish repeated retrieval from new informational support and map reformulations/decomposition to the original request.

### 5. Expose web content-acquisition completeness on evidence candidates

Add/confirm an optional typed field such as:

```text
content_acquisition
- completeness: FULL | PARTIAL | UNKNOWN
- acquisition metadata as applicable
```

Stage 5 needs to preserve partial/unknown web-content completeness rather than treating every grounding payload as semantically complete.

### 6. Define retrieval-lineage references precisely

`EvidenceCandidate.retrieval_lineage[]` should reference stable run/task/transform identities rather than only carrying opaque/free-form metadata.

### 7. Confirm provenance contract-criticality

ADR-010 should explicitly state that evidence candidates missing required source provenance are contract-invalid for downstream grounding. Stage 5 will not invent missing provenance.

These deltas do not move semantic deduplication, conflict grouping, or sufficiency into Stage 4.

## Proposed Global Architecture / `stages.md` Changes

These changes are **proposed only** until orchestrator acceptance.

### `docs/architecture/architecture.md`

Add accepted Stage 5 invariants after ADR review:

- final evidence relationship model distinguishes exact/derivative/independent/unknown dependence,
- duplicate/derivative evidence does not inflate independent corroboration,
- material conflict is structurally grouped and remains orthogonal to sufficiency,
- Stage 5 tracks coverage and semantic sufficiency,
- assembly execution status is distinct from evidence insufficiency,
- Stage 5 emits structured `GenerationContext`,
- V1 uses no generative evidence compression and performs no new retrieval during context assembly,
- context ordering is query-sensitive and temporal uncertainty is preserved,
- Stage 6 receives source failures/degradation and provenance-complete selected evidence.

### `stages.md`

Clarify Stage 5 responsibilities to include:

- evidence relationship/corroboration analysis,
- conflict grouping,
- coverage/sufficiency assessment,
- provenance-safe context selection,
- structured `GenerationContext` output.

Move/clarify **prompt construction** from Stage 5 to Stage 6 if the orchestrator accepts the proposed boundary:

```text
Stage 5: structured context assembly
Stage 6: generation prompt/instructions + answer generation
```

### Stage 4 documents / ADR-010

Apply the explicit contract deltas listed above after orchestrator review.

## Dependencies

### Stage 2

Depends on canonical evidence/provenance identity, source hashes/lineage signals, temporal metadata, and publication correctness.

### Stage 3

Depends on deterministic retrieval candidates, upstream ranks/signals, canonical chunk identity, eligibility enforcement, temporal match metadata, and retrieval degradation.

### Stage 4

Depends on accepted `EvidenceGatheringResult`, stable retrieval/task/transformation lineage, required-source statuses, and grounding-capable local/web evidence.

### Stage 6

Consumes `GenerationContext` and owns grounded answer generation under the proposed boundary.

### Stage 7

Must evaluate evidence relationships, corroboration errors, conflicts, coverage, sufficiency, selection quality, temporal ordering, and provenance retention.

### Stage 8

Must trace structured Stage 5 decisions, selected/dropped evidence, budget use, context presented to Stage 6, and assembly outcomes.

### Stage 9

Stage 5 structurally preserves retrieved content as data rather than control instructions and keeps citation/provenance lineage intact for guardrail enforcement.

### Stage 10

No additional production topology is required for Stage 5 V1 beyond the accepted bounded interactive architecture.

## Implementation Plan

Implementation should follow accepted ADRs and orchestrator-approved contract updates.

### Milestone 1: Types and validation

- define `ContextAssemblyResult`, `GenerationContext`, `ContextItem`, relationship/conflict/coverage/sufficiency structures,
- validate Stage 4 completion state, evidence policy, candidate provenance, and acquisition completeness,
- establish stable reason-code taxonomies.

### Milestone 2: Evidence relationship analysis

- implement same-identity/exact-duplicate handling,
- implement conservative derivative/unknown-dependence classification,
- select representative evidence while preserving alternate provenance,
- verify duplicate evidence cannot inflate independent support.

### Milestone 3: Conflict and coverage analysis

- map coverage units from resolved query/Stage 4 tasks,
- identify material factual/quantitative/temporal conflicts and interpretation divergence,
- attach supporting evidence and coverage links.

### Milestone 4: Context utility and temporal organization

- implement deterministic context-usefulness reassessment baseline,
- implement soft diversity controls,
- implement query-sensitive temporal ordering/grouping,
- preserve unresolved/approximate temporal semantics.

### Milestone 5: Budgeted selection

- implement context-budget accounting,
- implement provenance-preserving extractive selection,
- preserve required conflict sides and material coverage,
- record structured selection/drop reasons.

### Milestone 6: Sufficiency and GenerationContext

- compute coverage states and overall sufficiency,
- produce `GenerationContext`,
- propagate failures/degradation/assumptions,
- validate Stage 6 can consume context without raw Stage 4 runs.

### Milestone 7: Evaluation and observability

- implement deterministic benchmark fixtures for duplicate/conflict/temporal/partial cases,
- instrument selection/relationship/coverage/budget/sufficiency traces,
- establish latency/token/cost baselines,
- evaluate whether learned reranking or compression is actually needed before adding either.

## Open Questions

The core Stage 5 semantic architecture is resolved. Remaining implementation/evaluation questions include:

- exact deterministic/semantic mechanisms for derivative evidence detection,
- exact relevance/context-utility scoring/rules,
- exact diversity pressure configuration,
- exact context token budgets,
- exact conflict materiality thresholds/heuristics,
- exact coverage-unit derivation implementation,
- exact extractive passage-selection algorithm,
- whether evaluation later justifies learned reranking,
- whether evaluation later justifies provenance-safe generative compression.

These are tuning/implementation questions unless future evaluation exposes a need to change the accepted semantic contract.

## Decisions Requiring Orchestrator Approval

1. ADR-011 — Evidence Relationship and Corroboration Semantics.
2. ADR-012 — Conflict, Coverage, and Sufficiency Model.
3. ADR-013 — GenerationContext and Stage 5 -> Stage 6 Boundary.
4. Stage 4 / ADR-010 contract deltas listed in this document.
5. Prompt-construction ownership clarification between Stage 5 and Stage 6.
6. Corresponding `architecture.md` and `stages.md` updates after acceptance.

## Acceptance Criteria

Stage 5 may be marked Implementation Ready only when:

- ADR-011/012/013 are accepted,
- Stage 4's final accepted handoff contains required Stage 5 fields or equivalent semantics,
- the prompt-construction boundary is resolved,
- global architecture/roadmap updates are accepted where required,
- representative duplicate/derivative/conflict/coverage/temporal/failure cases are defined for evaluation,
- Stage 6 handoff contract is stable,
- no unresolved architecture question requires source-authority ranking or new retrieval ownership.

## Impact on Existing Architecture

Stage 5 does not weaken existing evidence boundaries, provenance, temporal uncertainty, deterministic local retrieval, or bounded Stage 4 orchestration.

It adds the missing final evidence-semantics layer between evidence gathering and generation:

```text
Stage 4 EvidenceGatheringResult
        ↓
Stage 5 relationship/conflict/coverage/selection/sufficiency
        ↓
GenerationContext
        ↓
Stage 6 grounded generation
```

The principal cross-stage impacts are:

- explicit Stage 4 lineage/status/completeness fields,
- a formal Stage 5 -> Stage 6 `GenerationContext`,
- global documentation of duplicate/corroboration, conflict, coverage, and sufficiency invariants,
- proposed movement of final prompt construction into Stage 6.
