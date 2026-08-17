# Stage 5: Context Assembly

## Status

**Implementation Ready.**

Orchestrator review is complete. ADR-011, ADR-012, and ADR-013 are accepted. Stage 5 is reconciled against the accepted Stage 4 contract in ADR-010 and the global Stage 5 invariants are recorded in `docs/architecture/architecture.md`.

## Objective

Transform a completed Stage 4 `EvidenceGatheringResult` into the smallest safe, provenance-complete, temporally coherent, conflict-preserving, duplicate-aware structured `GenerationContext` required for Stage 6 grounded generation.

Stage 5 is the final evidence-preparation boundary before generation. It determines what gathered evidence is usable, how evidence relationships affect corroboration, how conflicts and coverage are represented, which evidence fits the context budget, and whether the permitted evidence is sufficient for a full or partial answer.

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
- revalidation of the immutable evidence boundary,
- evidence normalization for context assembly,
- exact/semantic/derivative evidence relationship analysis,
- independent corroboration semantics,
- conflict detection and grouping,
- semantic question/subquestion coverage tracking,
- final evidence relevance/usefulness reassessment,
- source/document/domain/task diversity control,
- temporal grouping and ordering,
- context token budgeting,
- context selection,
- provenance-preserving extractive trimming,
- final evidence sufficiency assessment,
- unsupported/partial-answer state,
- structured Stage 5 → Stage 6 `GenerationContext`,
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
- system/generation prompt construction,
- final citation rendering,
- final response formatting,
- user-facing conflict/uncertainty prose,
- long-running/distributed context-assembly infrastructure.

Stage 6 owns generation prompt/instruction construction, grounded prose synthesis, user-facing uncertainty/conflict/partial-answer wording, response formatting, and final citation rendering.

## Requirements

### Evidence boundary

Only evidence permitted by the current immutable `EvidencePolicy` may enter `GenerationContext`.

Stage 5 revalidates source legality as defense in depth. Any candidate outside selected corpora or violating the current web policy is unusable and is rejected with a structured contract/policy trace. Stage 5 never expands the legal source set.

Target source-boundary violation rate: **0**.

### Provenance

Every selected context item must remain traceable to authoritative evidence provenance and stable Stage 4 run/task/transform lineage references.

Stage 5 must not fabricate missing local IDs, web identities, citation targets, temporal values, acquisition state, or lineage.

### Temporal semantics

Temporal origin, semantic role, precision, certainty, BCE/CE semantics, source wording, multiple mentions, and unresolved temporal state survive context assembly.

Source/publication time is not event/content time. Approximate or uncertain dates must not become falsely exact during ordering or extraction.

### Conflict preservation

Materially incompatible factual claims and supported interpretation divergences remain visible as structured competing claims.

Stage 5 does not silently reconcile, suppress, majority-vote, or nominate a factual winner in V1.

### Duplicate/corroboration safety

Repeated, copied, syndicated, mirrored, or derivative evidence must not count as independent corroboration merely because it appears in multiple documents, URLs, domains, corpora, or retrieval runs.

### Partial answers

Supported portions of compound/timeline questions remain usable even when other portions are unsupported. Stage 5 explicitly represents supported and unsupported aspects for Stage 6.

## Assumptions

- ADR-001 through ADR-010 are accepted and authoritative upstream architecture.
- ADR-011 through ADR-013 are accepted Stage 5 architecture.
- V1 is single-tenant, low concurrency, bounded-candidate, interactive.
- Exact context token budgets, ranking weights, and classifier/model choices are versioned implementation/evaluation configuration.
- Stage 6 consumes structured `GenerationContext` and owns final generation instructions, answer synthesis, formatting, and citation rendering.

## Inputs

Stage 5 consumes the accepted ADR-010 contract:

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

Required-source execution status is first-class:

```text
RequiredSourceStatus
- source_type
- required
- attempted
- completed
- outcome
- terminal_failure?
```

Stage 5 must distinguish:

- source not required,
- required and succeeded with candidates,
- required and completed with no candidates,
- required and degraded,
- required and persistently failed.

It must not infer required-source execution state merely from candidate presence.

Every Stage 4 retrieval run preserves causal lineage:

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

Evidence candidates use the accepted common envelope:

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

For web evidence, `content_acquisition` preserves completeness semantics such as `FULL`, `PARTIAL`, or `UNKNOWN` where applicable.

## Input Validation

### Completion-state behavior

- `COMPLETED` is eligible for normal assembly.
- `COMPLETED_DEGRADED` is eligible for normal assembly and degradation propagates.
- `CLARIFICATION_REQUIRED` does not enter normal evidence assembly and produces a non-applicable assembly result.
- `REJECTED` does not enter normal evidence assembly and produces a non-applicable assembly result.

Stage 5 may assemble when one required source succeeded and another failed, provided Stage 4 completed its bounded execution obligations and preserved the failure/degradation state.

### Candidate validity

A candidate is unusable when contract-critical provenance, legal source identity, authoritative evidence text, or other required grounding fields are missing or malformed.

Missing optional metadata may degrade a candidate without invalidating it. Examples include unknown publication time or absent optional temporal annotations.

Invalid candidates may be dropped individually when safe evidence remains. If corruption is widespread enough that Stage 5 cannot safely construct provenance-complete context, assembly fails rather than inventing missing fields.

### Empty evidence

A structurally valid completed gathering result containing no usable evidence is not a Stage 5 internal error. Stage 5 returns an assembled context with `INSUFFICIENT` evidence.

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

Local provenance retains corpus/document/version/generation/chunk identities. Web provenance retains URL/source/domain identity. Normalization is for analysis, not identity replacement.

## Evidence Relationship and Duplicate Semantics

Under ADR-011, Stage 5 distinguishes:

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

V1 is conservative: suspected derivation prevents counting family members as independent corroboration unless independence is reasonably established.

### Independent

Different URL, domain, document, corpus, or retrieval run does not by itself prove independence. Independence requires adequate basis to treat the supporting information as not known to derive from the same underlying information source.

### Unknown dependence

When Stage 5 cannot safely establish whether evidence is independent, it records `UNKNOWN_DEPENDENCE`. This is not proof of derivation, but it is also not counted as established independent corroboration.

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

Stage 5 normally selects one textual representative from exact/derivative families while retaining alternate provenance and retrieval lineage. Additional family members are selected only when they contribute materially distinct useful context or provenance.

V1 introduces no numeric corroboration-confidence score.

## Corroboration Semantics

Corroboration is descriptive and structural, not a calibrated truth probability.

Stage 5 may expose:

```text
supporting_evidence_ids[]
independent_support_units[]
dependency_groups[]
dependence_uncertain
```

Raw evidence/source count is never treated as independent-support count. Stage 5 does not introduce source-authority ranking, domain trust scoring, or majority-vote factual selection.

## Conflict Handling

Under ADR-012, Stage 5 classifies material evidence relationships using:

```text
FACTUAL_CONFLICT
QUANTITATIVE_CONFLICT
TEMPORAL_CONFLICT
INTERPRETATION_DIVERGENCE
NOT_A_CONFLICT
```

Textual differences are not automatically conflicts. A discrepancy becomes a conflict only when claims are materially incompatible for the user's question or coverage unit.

Interpretation divergence preserves supported competing explanations without requiring one side to be factually false.

Stage 5 does not nominate a preferred or winning claim in V1, even when one side has more independent support. Evidence-support structure may be exposed descriptively, but truth selection is not inferred from count alone.

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

Conflict is orthogonal to sufficiency. Evidence may be `SUFFICIENT` while `conflicts_present = true` when the disagreement itself can be accurately answered.

## Coverage Model

Stage 5 explicitly tracks semantic coverage units for material parts of the question.

Coverage units originate from the original/resolved question and Stage 4 decomposition. Stage 5 may consolidate overlapping Stage 4 tasks into the same coverage unit but must not invent unrelated answer requirements.

Conceptually:

```text
CoverageUnit
- coverage_id
- description
- support_status
- conflicts_present
- supporting_evidence_ids[]
- missing_aspects[]
- source_task_lineage[]
```

Support states:

```text
SUPPORTED
PARTIALLY_SUPPORTED
UNSUPPORTED
```

Timeline/range questions may contain multiple temporal coverage segments. Meaningful missing requested periods may make the overall result partially sufficient.

## Relevance / Context Utility Reassessment

Stage 5 performs a final context-usefulness reassessment because gathered evidence may combine multiple retrieval runs, decomposition tasks, reformulations, source classes, conflicts, and incomparable upstream ranks.

V1 does not require an LLM judge or learned reranker.

Initial structured signals may include:

- upstream retrieval rank/signals,
- coverage-unit match,
- temporal relevance,
- duplicate/dependency status,
- conflict participation,
- acquisition completeness,
- degradation state,
- provenance completeness.

Exact weighting/rules are versioned implementation/evaluation configuration. Learned or model-based reranking is a benchmark-triggered future option, not a V1 architectural dependency.

## Diversity

Diversity is a soft context-quality control, not a quota system.

Stage 5 should avoid pathological domination by one document, corpus, web domain, duplicate/dependency family, or retrieval task when useful alternatives exist.

Soft diversity pressure must not displace clearly stronger or uniquely necessary evidence solely to create cosmetic variety.

V1 has no fixed local/web split and no mandatory per-corpus/per-document token quota.

A required source may contribute zero selected context items when its evidence is weak/redundant, while its execution/failure/degradation status still propagates to Stage 6.

## Temporal Organization

Context ordering is query-sensitive rather than universally chronological.

- Timeline/date-range queries emphasize chronological organization while preserving approximate/uncertain placement.
- Exact fact lookups emphasize relevance/support.
- Before/after queries organize around the anchor and requested relation.
- Conflict-focused queries may group competing claims ahead of strict chronology.
- Compound queries may group by coverage/subquestion.

Approximate or uncertain dates retain their precision/certainty. Stage 5 does not assign fake exact ordering when evidence only supports coarse or unresolved placement.

For timeline-like questions Stage 5 may produce structured timeline entries, but it does not generate narrative timeline prose.

## Token Budgeting

Context token budget is versioned configuration.

Stage 5 owns allocation within the generation-context budget. Allocation prioritizes:

1. material question coverage,
2. preservation of material conflict sides,
3. established independent evidence,
4. temporal completeness when relevant,
5. provenance metadata necessary for grounding/citations.

Exact token values, reserve sizes, tuning weights, and profile-specific allocations are implementation/evaluation configuration.

## Context Selection

Every candidate considered for final context receives a structured decision such as:

```text
ContextSelectionDecision
- evidence_id
- selected
- reasons[]
```

Reason concepts include:

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

Stage 5 may perform provenance-preserving extractive trimming or passage selection. Selected text exposes extent semantics such as:

```text
FULL
EXTRACTED
```

Extracted passages retain exact lineage to original evidence spans and never masquerade as complete/full source content.

Generated summaries require a future architecture decision that explicitly separates derived summary text from source evidence and preserves compression lineage.

## Neighboring Context / Retrieval Boundary

Stage 5 performs no new datastore retrieval or adjacent-chunk fetch in V1.

Already-gathered parent/neighbor text or metadata may be used only when it is already part of the Stage 4 evidence contract. New evidence acquisition after Stage 4 completion requires an explicit future cross-stage architecture change.

## Sufficiency Assessment

Overall states are:

```text
SUFFICIENT
PARTIALLY_SUFFICIENT
INSUFFICIENT
```

Sufficiency is semantic, not count-based. It considers material requested aspects, provenance completeness, temporal support where relevant, unresolved conflict, degradation/failure context, and explicit coverage.

A required-source failure does not automatically force `INSUFFICIENT` if remaining permitted evidence still supports the material requested aspects. The failure remains visible downstream.

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

Stage 6 receives supported and unsupported aspects directly and must not have to rediscover them from raw passages.

## Assembly Outcome Model

Assembly execution status is distinct from evidence sufficiency:

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

- valid empty evidence → `ASSEMBLED + INSUFFICIENT`,
- all required sources failed but Stage 4 result is structurally valid → `ASSEMBLED + INSUFFICIENT`,
- `CLARIFICATION_REQUIRED` → `NOT_APPLICABLE`,
- `REJECTED` → `NOT_APPLICABLE`,
- malformed Stage 4 contract → `FAILED`,
- provenance corruption preventing safe packaging → `FAILED`,
- internal Stage 5 processing failure → `FAILED`.

If the configured context budget is too small to represent minimum material supported evidence safely, including necessary conflict sides and coverage, Stage 5 returns `FAILED` with a specific context-budget reason instead of silently dropping critical evidence.

## Stage 6 Handoff Contract

Under ADR-013, Stage 5 returns a formal structured `GenerationContext`:

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

Concrete schemas may evolve while preserving these semantics. Stage 6 must not depend on Stage 5-internal ranking formulas or arbitrary trace details.

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
- retrieval_lineage_refs[]
```

Selection/ordering rationale may be retained in assembly trace/metadata but is not required to be prompt-visible unless Stage 6 needs it for a defined generation behavior.

Stage 6 does not require raw Stage 4 retrieval runs for normal generation. Full run graphs remain available to evaluation/observability; selected items preserve stable lineage references.

Stage 6 receives enough structured metadata to:

- ground material claims,
- produce supported partial answers,
- disclose conflicts,
- avoid false independent-corroboration statements,
- disclose source failures/degradation,
- render citations from real source provenance,
- abstain where coverage is unsupported.

Stage 5 never fabricates citation targets.

## Prompt Construction Boundary

The accepted boundary is:

```text
Stage 5
EvidenceGatheringResult → structured GenerationContext

Stage 6
System/generation instructions + GenerationContext → grounded answer
```

Stage 6 owns:

- system/generation prompt construction,
- grounding instructions,
- response-format instructions,
- citation-rendering instructions,
- natural-language answer generation,
- user-facing conflict/uncertainty/partial-answer wording.

Retrieved evidence remains data. Stage 5 must not convert retrieved text into control-plane instructions.

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

May be usable when selected text itself supports the required claim and provenance is valid. Acquisition completeness remains visible; `PARTIAL` never becomes `FULL` implicitly.

### Required-source terminal failure

The failure remains explicit in `required_source_statuses[]` and downstream failure/degradation metadata. It does not force weak evidence from that source into final context.

### Duplicate-only apparent corroboration

Duplicates do not increase independence. Sufficiency depends on semantic support needs rather than duplicate count.

### Unresolved material conflict

Conflict is preserved and does not automatically imply insufficiency.

### Context budget too small

`FAILED` with a specific budget/assembly reason when critical supported evidence cannot be represented safely.

## Evaluation Criteria

Stage 5 evaluation must include at least:

- provenance retention rate,
- source-boundary violation rate,
- false independent-corroboration rate,
- evidence-relationship classification quality,
- conflict preservation rate,
- coverage classification accuracy,
- sufficiency classification accuracy,
- context precision,
- context coverage/recall,
- evidence omission / critical-evidence-drop rate,
- duplicate-token reduction without loss of unique provenance,
- temporal organization correctness,
- unsupported/policy-violating evidence inclusion rate,
- context-budget efficiency,
- degraded-source handling correctness,
- assembly latency,
- assembly cost where applicable.

Benchmark cases include at least:

- single factual query,
- compound/decomposed question,
- timeline/date range,
- BCE/CE,
- approximate period,
- exact duplicate content,
- semantic/derivative duplicate content,
- syndicated web content,
- established independent corroboration,
- unknown dependence,
- conflicting dates,
- conflicting quantities,
- conflicting interpretations,
- local + web,
- one required source failure,
- partial web evidence,
- no usable evidence,
- unsupported subquestion,
- malformed provenance,
- context-budget exhaustion.

Target invariants include effectively 100% provenance retention for selected context, zero known source-boundary violations, and zero false independent corroboration on deterministic duplicate/derivative benchmark cases.

## Observability

Structured traces should include at least:

```text
input_candidate_count
valid_candidate_count
invalid_candidate_count
rejected_candidates_with_reason
relationship_groups[]
corroboration_decisions[]
conflict_groups[]
coverage_units[]
relevance_reassessment
selection_decisions[]
drop_reasons[]
ordering_strategy
token_budget
token_allocation
selected_token_count
extraction_trimming[]
final_context_order
sufficiency_assessment
assembly_status
source_failures[]
degraded_sources[]
configuration_version
assembly_latency
```

Stage 5 traces structured decisions and reasons. It does not require or persist arbitrary hidden model chain-of-thought.

## Scalability

V1 assumes bounded candidate sets from Stage 4, one primary user, low concurrency, and interactive use.

Stage 5 should initially be implemented as an application-layer component boundary rather than distributed context-assembly infrastructure.

Revisit scaling architecture if candidate volume, concurrency, semantic relationship analysis, or learned reranking/compression becomes a measured bottleneck.

## Latency / Throughput Requirements

Stage 5 should remain a bounded fraction of interactive request latency. Exact latency targets require benchmark data and are configuration/evaluation concerns rather than architecture constants.

Costly model-based reranking or summarization is not part of the V1 baseline.

## Alternatives Considered

### Trust upstream retrieval ordering entirely

Rejected because Stage 5 receives heterogeneous evidence across runs, tasks, source classes, conflict states, and duplicate families whose upstream ranks are not globally comparable.

### LLM judge for all evidence selection

Deferred because it adds cost, latency, nondeterminism, and another evidence-suppression surface before deterministic/structured signals are benchmarked.

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
2. Repeated retrieval and copied/derivative evidence do not inflate independent corroboration.
3. Unknown dependence is not counted as established independence.
4. Duplicate/derivative families normally use one representative text plus alternate provenance.
5. V1 uses no numeric corroboration-confidence score.
6. Material factual, quantitative, temporal, and interpretation conflicts are represented explicitly.
7. Conflict is orthogonal to sufficiency.
8. Stage 5 does not nominate a preferred conflict claim or introduce source authority in V1.
9. Stage 5 explicitly tracks semantic coverage units and supported/partial/unsupported aspects.
10. Overall sufficiency is `SUFFICIENT`, `PARTIALLY_SUFFICIENT`, or `INSUFFICIENT` and is semantic rather than count-based.
11. Required-source failure does not automatically force insufficiency.
12. Stage 5 performs final context-usefulness reassessment using structured signals; learned/LLM reranking is not required in V1.
13. Diversity is soft and quota-free; no fixed local/web split exists.
14. Context ordering is query-sensitive and preserves temporal uncertainty.
15. Context budget values and selection weights are versioned configuration.
16. V1 allows provenance-preserving extractive trimming and no generative evidence summarization.
17. Stage 5 performs no new retrieval or adjacent-chunk fetch in V1.
18. `COMPLETED` and `COMPLETED_DEGRADED` are assembly-eligible; `CLARIFICATION_REQUIRED` and `REJECTED` are not.
19. Empty valid evidence produces assembled insufficiency rather than internal failure.
20. Missing required provenance invalidates evidence; Stage 5 never fabricates it.
21. Assembly execution status is separate from evidence sufficiency.
22. Stage 5 emits structured `GenerationContext`; Stage 6 does not require raw Stage 4 run graphs for normal generation.
23. Stage 6 owns generation/system prompt construction, final answer synthesis, formatting, and citation rendering.
24. Retrieved evidence remains data, not control.

## Accepted Stage 4 Contract Reconciliation

The Stage 5 design is fully reconciled against accepted ADR-010.

The items originally identified during Stage 5 exploration as possible Stage 4 deltas are already present in the accepted upstream contract:

1. `required_source_statuses[]` is explicit in `EvidenceGatheringResult`.
2. Every `RetrievalRun` carries `task_id` and optional `parent_task_id`.
3. `run_kind` explicitly distinguishes mandatory initial, operational retry, and bounded evidence-seeking executions.
4. `parent_run_id`, `trigger_reason`, and `query_transform_id` preserve causal transformation lineage where applicable.
5. Web evidence exposes acquisition/completeness state such as `FULL`, `PARTIAL`, or `UNKNOWN`.
6. Evidence retrieval lineage references stable run/task/transform identities rather than relying on execution order or query-text inference.
7. Contract-invalid executor responses, including missing required provenance, fail explicitly; Stage 5 does not invent missing provenance.

No additional Stage 4 contract change is required for Stage 5 implementation.

## Dependencies

- Stage 1 behavioral contract and global evidence invariants.
- Stage 2 canonical evidence/provenance/temporal representations.
- Stage 3 deterministic local retrieval and candidate metadata.
- Stage 4 accepted `EvidenceGatheringResult` / ADR-010 contract.
- ADR-011 evidence relationship and corroboration semantics.
- ADR-012 conflict, coverage, and sufficiency model.
- ADR-013 `GenerationContext` and Stage 5 → Stage 6 boundary.

## Implementation Plan

1. Define concrete typed Stage 5 input/output schemas from ADR-010 and ADR-013.
2. Implement deterministic contract/policy/provenance validation.
3. Implement identity/exact-duplicate grouping from authoritative hashes/IDs.
4. Implement conservative derivative/independence analysis with explicit `UNKNOWN_DEPENDENCE`.
5. Implement conflict grouping and coverage-unit mapping.
6. Implement structured final utility reassessment, diversity, temporal ordering, and selection.
7. Implement provenance-preserving extraction and token budgeting.
8. Implement semantic sufficiency assessment and `ContextAssemblyResult`.
9. Add structured tracing and benchmark fixtures for all required Stage 5 evaluation cases.
10. Validate the concrete `GenerationContext` consumer contract with Stage 6 implementation without moving generation semantics into Stage 5.

## Open Questions

No unresolved architecture blocker remains for Stage 5 implementation.

Implementation/evaluation may still choose concrete:

- derivative-detection mechanisms,
- utility/ranking weights,
- token budgets,
- relationship/conflict/coverage classifiers,
- deterministic versus bounded model assistance for difficult semantic classification,
- concrete schema/enum names consistent with the accepted semantics.

Any future change that introduces source authority, generative evidence compression, Stage 5 retrieval, or a materially different Stage 5 → Stage 6 contract requires orchestrator review and an ADR update/new ADR as appropriate.

## Decisions Requiring Orchestrator Approval

None. Orchestrator review is complete.

## Acceptance Criteria

Stage 5 implementation is acceptable when it demonstrates:

- zero evidence-policy/source-boundary violations,
- provenance-safe selected context and citations inputs,
- no repeated/duplicate/derivative evidence inflation of independent corroboration,
- correct explicit unknown-dependence handling,
- material conflict preservation without winner selection,
- accurate compound/timeline coverage mapping,
- semantic sufficiency/partial-sufficiency behavior,
- preservation of required-source failure/degradation state,
- temporal ordering without false precision,
- deterministic/traceable context selection decisions under fixed configuration where applicable,
- extractive trimming with source-span lineage,
- safe behavior for empty/degraded/malformed/budget-exhausted inputs,
- a `GenerationContext` sufficient for Stage 6 grounded generation and citation rendering,
- structured observability without hidden chain-of-thought requirements.

## Impact on Existing Architecture

Stage 5 accepts and extends the end-to-end architecture by establishing:

- final evidence relationship/dependence and corroboration semantics,
- material conflict grouping,
- semantic coverage and final evidence sufficiency ownership,
- the structured `GenerationContext` contract,
- no-new-retrieval and extractive-only compression boundaries for V1,
- query-sensitive temporal context ordering,
- explicit propagation of source failures/degradation into generation context,
- Stage 6 ownership of generation/system prompt construction.

These accepted project-wide invariants are recorded in `docs/architecture/architecture.md` and ADR-011 through ADR-013.