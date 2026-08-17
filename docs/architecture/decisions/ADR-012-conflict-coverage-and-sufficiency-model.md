# ADR-012: Conflict, Coverage, and Sufficiency Model

## Status

Accepted

## Context

ASTRAG requires conflicting evidence to be exposed rather than silently reconciled, and it prefers supported partial answers over unsupported complete answers. Stage 4 may preserve contradictory evidence and perform bounded conflict-follow-up retrieval, but it intentionally does not perform final conflict grouping or decide answerability.

Stage 5 therefore needs a semantic model that can distinguish factual contradiction from harmless variation or interpretive disagreement, track which material parts of the user's question are supported, and determine final evidence sufficiency without relying on simplistic chunk/source counts.

Several viable models exist:

1. treat any textual disagreement as conflict,
2. resolve conflict by majority/source count,
3. make `CONFLICTED` a mutually exclusive sufficiency state,
4. model material conflicts, semantic coverage, and evidence sufficiency separately but coherently.

## Decision

ASTRAG Stage 5 adopts an explicit material-conflict, semantic-coverage, and sufficiency model.

### Conflict categories

V1 uses the following conceptual conflict categories:

```text
FACTUAL_CONFLICT
QUANTITATIVE_CONFLICT
TEMPORAL_CONFLICT
INTERPRETATION_DIVERGENCE
NOT_A_CONFLICT
```

#### Factual conflict

Materially incompatible factual propositions.

#### Quantitative conflict

Materially incompatible counts, measurements, estimates, or numerical claims where the difference matters to the user's question.

#### Temporal conflict

Materially incompatible dates, ranges, ordering, duration, or before/after relationships.

#### Interpretation divergence

Different supported explanations, causal accounts, or historical interpretations that need not imply one side is factually false.

#### Not a conflict

Different but compatible details, wording differences, or immaterial discrepancies.

### Materiality

Stage 5 does not classify every textual or numeric difference as a conflict. The discrepancy must be materially incompatible for the user's requested proposition or coverage unit.

### Conflict representation

Conflict groups conceptually preserve:

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

The exact schema may evolve while preserving these semantics.

### No winning claim in V1

Stage 5 does not nominate a preferred/winning factual claim in V1, even when one side has more independent supporting evidence.

It may preserve descriptive support structure, but source/evidence count does not become factual authority.

No majority-vote or implicit source-authority policy is introduced.

### Conflict is orthogonal to sufficiency

Conflict is not a mutually exclusive top-level sufficiency state.

A context may be:

```text
sufficiency = SUFFICIENT
conflicts_present = true
```

when the available evidence is sufficient to answer by accurately presenting the material disagreement.

Likewise, a conflict may exist inside a partially supported question.

### Semantic coverage units

Stage 5 explicitly tracks material question aspects through `CoverageUnit` values derived from the original/resolved query and Stage 4 decomposition.

Stage 5 may merge overlapping tasks into the same coverage unit but does not freely invent unrelated answer requirements.

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

Per-unit support states are:

```text
SUPPORTED
PARTIALLY_SUPPORTED
UNSUPPORTED
```

Conflict remains orthogonal to these states.

### Overall sufficiency

Overall Stage 5 evidence sufficiency states are:

```text
SUFFICIENT
PARTIALLY_SUFFICIENT
INSUFFICIENT
```

`SUFFICIENT` means the material requested aspects are supported adequately for grounded Stage 6 generation under the current evidence policy.

Sufficiency is semantic. It is not defined by a minimum chunk count, URL count, document count, or fixed corroboration count.

### Partial support

When only some material aspects are supported, Stage 5 returns `PARTIALLY_SUFFICIENT` and explicitly preserves supported and unsupported aspects.

For timeline/range questions, meaningful missing requested segments may make the result partially sufficient even if other periods are well supported.

### Required-source failure

Failure of one required source does not automatically make the evidence insufficient if the remaining permitted evidence still supports the material requested aspects.

The failed/degraded required-source state remains visible to Stage 6 and evaluation.

### Empty/no usable evidence

A structurally valid evidence-gathering result with no usable evidence may produce `INSUFFICIENT`; this is not itself a Stage 5 internal failure.

### Sufficiency assessment structure

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

Stage 6 receives this structured assessment rather than being required to rediscover coverage/sufficiency from raw evidence text.

## Consequences

### Positive

- Material conflicts survive into generation without being silently reconciled.
- Interpretation disagreement is not misclassified as simple factual contradiction.
- Stage 6 can present a conflict while still producing an evidence-supported answer.
- Compound questions and timelines support explicit partial-answer behavior.
- Sufficiency becomes testable against semantic requirements rather than arbitrary evidence counts.
- Source failure/degradation remains separate from answerability.
- Stage 7 can directly evaluate coverage and sufficiency classification.

### Negative

- Stage 5 must derive and maintain semantic coverage mappings.
- Conflict materiality requires careful implementation/evaluation.
- Sufficiency classification becomes a substantive semantic subsystem rather than a simple threshold.
- Some borderline cases may remain difficult without introducing more advanced models later.

## Alternatives Considered

### Treat every disagreement as conflict

Rejected because compatible details and immaterial numerical differences would produce noisy/confusing conflict states.

### Majority/source-count winner

Rejected because duplicate/derivative sources distort counts and source count is not authority.

### Preferred claim from independent-support count

Deferred for V1 because stronger structural support does not itself establish truth or source authority.

### `CONFLICTED` as a top-level sufficiency state

Rejected because conflict and answerability are independent dimensions. A well-supported disagreement can be fully answerable as a disagreement.

### Chunk-count sufficiency threshold

Rejected because evidence quantity does not establish semantic coverage.

### Let Stage 6 infer coverage and sufficiency from context

Rejected because Stage 5 already owns final evidence preparation and should not force generation to reconstruct critical evidence semantics from prose.

## Revisit Triggers

Revisit this ADR if:

- evaluation shows current conflict categories are insufficient,
- calibrated authority/trust policy is separately accepted,
- Stage 6 requires richer proposition-level support structures,
- coverage-unit derivation proves too unstable for reliable evaluation,
- answer-quality evaluation demonstrates that a richer sufficiency model is necessary.

## Affected Stages

- Stage 4 — Agent / Orchestration Layer
- Stage 5 — Context Assembly
- Stage 6 — Generation Layer
- Stage 7 — Evaluation Framework
- Stage 8 — Observability & Debugging
- Stage 9 — Guardrails & Reliability

## Related Documents

- `NORTHSTAR.md`
- `docs/architecture/architecture.md`
- `docs/stages/01-problem-definition.md`
- `docs/stages/04-agent-orchestration.md`
- `docs/stages/05-context-assembly.md`
- `docs/architecture/decisions/ADR-001-query-source-execution-policy.md`
- `docs/architecture/decisions/ADR-003-temporal-evidence-representation.md`
- `docs/architecture/decisions/ADR-006-temporal-query-retrieval-policy.md`
- `docs/architecture/decisions/ADR-009-v1-bounded-orchestration-execution-model.md`
- `docs/architecture/decisions/ADR-010-evidence-gathering-and-web-retrieval-contract.md`
- `docs/architecture/decisions/ADR-011-evidence-relationship-and-corroboration-semantics.md`