# ADR-013: GenerationContext and Stage 5 → Stage 6 Boundary

## Status

Accepted

## Context

Stage 4 returns a structured `EvidenceGatheringResult` containing retrieval-run lineage, evidence candidates, failures, degradation, interpretation assumptions, and the immutable evidence policy. Stage 5 must transform that result into final evidence context for Stage 6.

Without a formal Stage 5 → Stage 6 contract, Stage 6 would be forced to rediscover duplicate/corroboration relationships, conflicts, question coverage, source failures, and sufficiency directly from raw evidence. That would duplicate Stage 5 responsibilities and make generation behavior less reproducible.

The repository roadmap historically listed prompt construction under Stage 5, while Stage 6 is responsible for system prompts, grounding instructions, structured outputs, citation behavior, response formatting, and unsupported-answer handling. Splitting prompt ownership across the two stages creates an unnecessary and ambiguous boundary.

Several viable designs exist:

1. pass raw Stage 4 results directly to Stage 6,
2. pass only a flattened list of selected passages,
3. let Stage 5 build the final generation prompt,
4. define a structured `GenerationContext` produced by Stage 5 and let Stage 6 own generation instructions/prompt construction.

## Decision

ASTRAG adopts a formal structured `GenerationContext` as the Stage 5 → Stage 6 handoff.

Stage 5 owns final evidence assembly and evidence semantics. Stage 6 consumes that structured result for grounded natural-language generation.

### GenerationContext

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

The exact concrete schema may evolve without changing this ADR as long as these semantics remain available.

Stage 6 must not depend on Stage 5-internal scoring formulas, ranking implementation details, or arbitrary observability fields unless a future contract explicitly promotes them.

### ContextItem

Each selected context item conceptually includes:

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

`text_extent` distinguishes at least full evidence text from provenance-preserving extracted text. Extracted text must remain traceable to the source span and must not masquerade as full source content.

Selection and ordering rationale may remain in `assembly_metadata`/observability rather than becoming mandatory prompt-visible fields.

### Stage 6 does not require raw Stage 4 runs

Normal Stage 6 generation does not consume the complete raw Stage 4 retrieval-run graph.

Stage 5 preserves stable lineage references sufficient to trace each selected context item back through Stage 4 for evaluation/debugging. Full Stage 4 traces remain available to observability systems rather than being included in every generation request.

### Structured evidence semantics reach Stage 6

Stage 6 receives structured:

- duplicate/dependency/independence relationships,
- material conflict groups,
- semantic coverage units,
- sufficiency assessment,
- supported and unsupported aspects,
- required-source statuses,
- source failures/degradation,
- interpretation assumptions,
- provenance and temporal metadata.

Stage 6 should not be required to rederive these decisions from prose.

### Required source status is independent from selected context

A required local/web source may have been attempted, failed, degraded, returned no candidates, or returned weak/redundant evidence that contributes no final `ContextItem`.

Its execution/degradation state still propagates in `GenerationContext` so Stage 6 can disclose relevant retrieval limitations without forcing weak evidence into final context merely for symmetry.

### Provenance and citation support

Stage 5 preserves real source provenance and evidence-to-provenance mapping. It does not fabricate citation targets.

Stage 6 owns final citation rendering and user-facing citation granularity under the generation architecture.

### Assembly execution status is separate from sufficiency

Stage 5 returns a wrapper conceptually equivalent to:

```text
ContextAssemblyResult
- assembly_status
- generation_context?
- failure?
```

with:

```text
ASSEMBLED
NOT_APPLICABLE
FAILED
```

Evidence sufficiency exists inside an assembled `GenerationContext` and uses:

```text
SUFFICIENT
PARTIALLY_SUFFICIENT
INSUFFICIENT
```

Therefore:

- `ASSEMBLED + INSUFFICIENT` means Stage 5 safely processed the evidence but it is inadequate for the requested answer,
- `FAILED` means Stage 5 could not safely construct context,
- `NOT_APPLICABLE` covers upstream terminal states such as `REJECTED` or `CLARIFICATION_REQUIRED` that should not enter normal evidence generation.

This prevents retrieval insufficiency from being confused with context-assembly malfunction.

### Prompt-construction boundary

The accepted ownership boundary is:

```text
Stage 5
EvidenceGatheringResult → GenerationContext

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

Stage 5 owns structured evidence semantics only and must not convert retrieved evidence into control-plane instructions. Retrieved content remains data.

The roadmap and global architecture must reflect this boundary.

### V1 context transformation boundary

V1 allows provenance-preserving extractive trimming but no generative/LLM evidence summarization.

Stage 5 performs no new retrieval or adjacent-chunk datastore fetch after Stage 4 completion.

If the context budget cannot safely represent minimum material evidence, conflicts, and coverage, Stage 5 returns a structured assembly failure instead of silently discarding critical evidence.

## Consequences

### Positive

- Stage 6 receives a clean generation-focused contract rather than raw orchestration internals.
- Conflict, corroboration, coverage, and sufficiency semantics are decided once in Stage 5.
- Provenance and temporal metadata survive into generation.
- Required-source failures remain visible without forcing weak evidence into context.
- Assembly failures are distinguishable from evidence insufficiency.
- Full Stage 4 traces need not consume generation-context tokens.
- Prompt/control instructions remain structurally separate from retrieved data.
- Prompt ownership is no longer split ambiguously between Stages 5 and 6.

### Negative

- `GenerationContext` is a richer contract than a flat passage list.
- Stage 5 must maintain stable evidence-to-lineage references.
- Stage 6 depends on the semantic contract established by Stage 5.
- Future changes to citation/claim-support granularity may require extending `ContextItem` metadata.

## Alternatives Considered

### Pass EvidenceGatheringResult directly to Stage 6

Rejected because Stage 6 would duplicate Stage 5 relationship/conflict/coverage/sufficiency logic and consume unnecessary orchestration details.

### Flat selected-passage list

Rejected because it loses structured conflicts, dependency semantics, coverage, degradation, and partial-answer guidance.

### Stage 5 builds final prompt

Rejected because Stage 6 already owns system prompts, grounding instructions, response formatting, citation behavior, and generation semantics. Splitting prompt ownership across stages creates unnecessary coupling.

### Stage 6 recomputes sufficiency

Rejected because final evidence sufficiency belongs to Stage 5 and should be evaluated independently from language generation.

### Include full Stage 4 trace in every generation request

Rejected because normal generation needs selected evidence and stable lineage references, not the complete orchestration execution graph.

## Revisit Triggers

Revisit this ADR if:

- Stage 6 requires proposition-level claim/evidence structures beyond current `ContextItem`/conflict/coverage metadata,
- generated evidence compression is introduced,
- context assembly is merged with generation for measured latency reasons,
- future generation architectures require streamed/incremental context,
- prompt ownership changes because of a materially different model/runtime architecture,
- citation integrity requires a richer Stage 5 support mapping.

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
- `stages.md`
- `docs/architecture/architecture.md`
- `docs/stages/04-agent-orchestration.md`
- `docs/stages/05-context-assembly.md`
- `docs/architecture/decisions/ADR-009-v1-bounded-orchestration-execution-model.md`
- `docs/architecture/decisions/ADR-010-evidence-gathering-and-web-retrieval-contract.md`
- `docs/architecture/decisions/ADR-011-evidence-relationship-and-corroboration-semantics.md`
- `docs/architecture/decisions/ADR-012-conflict-coverage-and-sufficiency-model.md`