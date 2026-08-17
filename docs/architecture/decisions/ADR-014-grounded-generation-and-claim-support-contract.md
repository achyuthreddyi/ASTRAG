# ADR-014: Grounded Generation and Claim-Support Contract

## Status

Accepted

## Context

Stage 5 emits a structured `GenerationContext` under ADR-013 containing selected provenance-complete evidence, evidence relationship/dependence semantics, conflict groups, coverage units, final sufficiency, required-source status, failures/degradation, temporal metadata, and interpretation assumptions.

Stage 6 must turn that evidence state into a useful response without silently recomputing upstream evidence semantics, adding unsupported model-memory facts, collapsing conflict, increasing temporal certainty, or treating source count as truth. A prose-only generation contract would make those invariants difficult to enforce and evaluate.

## Decision

ASTRAG adopts an explicit grounded claim-support contract for Stage 6.

### Stage 5 semantics are authoritative

Stage 6 treats `GenerationContext` evidence semantics as authoritative. It must not recompute or override:

- final sufficiency,
- supported/partially supported/unsupported coverage,
- conflict membership or conflict type,
- evidence relationship/dependence semantics,
- provenance identity,
- required-source execution status,
- source failure/degradation,
- temporal role, value, precision, and certainty,
- interpretation assumptions.

Stage 6 may reorganize presentation and may become more conservative. It may never increase evidentiary sufficiency or certainty.

### Material factual propositions require evidence

Every material factual proposition in the generated answer must be supported by evidence permitted by the immutable `EvidencePolicy`.

Model pretraining may assist interpretation, language, bounded reasoning, and presentation, but it cannot independently supply material factual content.

Conversation history remains interpretive/presentation context and is not factual evidence unless the same fact is independently present in permitted retrieved evidence.

### Claim representation

Stage 6 uses first-class structured claims conceptually equivalent to:

```text
AnswerClaim
- claim_id
- text
- claim_type
- support_status
- inference_type
- supporting_context_item_ids[]
- resolved_supporting_evidence_ids[]
- conflict_group_ids[]
- coverage_unit_ids[]
- temporal_semantics?
```

Claim granularity is atomic proposition / materially separable clause granularity rather than whole-paragraph grounding.

The model may reference only prompt-enumerated `context_item_id` values. Deterministic code resolves those context-item bindings to authoritative evidence identities and provenance. Evidence-to-claim support is many-to-many.

### Direct and derived support

V1 permits bounded evidence-grounded derivation when the conclusion follows from supplied evidence without adding unsupported premises.

Supported claims distinguish at least:

```text
SUPPORTED
SUPPORTED_DERIVED
UNSUPPORTED
```

Conflict is orthogonal to support status and remains represented through conflict metadata.

Inference type is explicit and extensible. Initial semantic categories include direct support and bounded derivations such as multi-evidence synthesis, temporal derivation, and comparative derivation.

A derived claim must bind all evidence materially required for the derivation.

### Unsupported generated claims

A material factual claim without valid support is not salvaged by uncertainty wording. It is a generation-validation failure unless a deterministic removal can preserve answer coherence without changing substantive meaning.

Stage 6 does not perform retrieval to repair unsupported claims. New evidence requires a new upstream orchestration cycle.

### Conflict and uncertainty

Material Stage 5 conflict groups represented in the answer must remain user-visible.

Stage 6 must:

- preserve every materially supported side of a conflict,
- retain separate evidence bindings for competing claims,
- distinguish factual/quantitative/temporal conflicts from interpretation divergence,
- avoid choosing a winner when no upstream truth/authority policy establishes one,
- avoid majority-vote or source-count truth selection,
- disclose required-source failures,
- disclose other uncertainty/dependence limitations when they materially affect interpretation or corroboration.

A user request for a definitive answer cannot override an unresolved material conflict.

### Sufficiency monotonicity

Stage 6 response semantics are monotonic with Stage 5 sufficiency:

```text
SUFFICIENT
→ full grounded answer or a more conservative response

PARTIALLY_SUFFICIENT
→ partial answer or a more conservative response

INSUFFICIENT
→ evidence-status / insufficient-evidence response
```

Stage 6 may not present `PARTIALLY_SUFFICIENT` or `INSUFFICIENT` evidence as a fully supported answer.

`INSUFFICIENT` may still include supported facts that directly explain the evidence limitation or answer a clearly separable supported aspect, provided the unsupported requested proposition is not presented as answered.

### World facts and evidence-state claims

Stage 6 distinguishes real-world factual claims from evidence-state claims.

For example, `the available evidence does not establish who ordered the attack` is an evidence-state claim and may be supported by structured coverage/sufficiency metadata. It must not be rewritten as the world-fact claim `nobody ordered the attack`.

### Temporal generation semantics

Temporal answer generation preserves Stage 5 temporal role, precision, uncertainty, and BCE/CE semantics.

- publication/source time is not event/content time,
- conflicting exact dates are not merged into a range unless upstream semantics represent a range rather than a conflict,
- derived temporal precision may preserve or reduce premise precision, never increase it,
- relative dates may be resolved only when anchor and arithmetic are unambiguous,
- resolved relative dates and comparisons are explicit temporal derivations,
- BCE/CE ordering and arithmetic use deterministic temporal utilities where calculation is required,
- ambiguous historical calendar conversion is not invented,
- requested historical temporal scope is part of the grounding obligation.

If a fact is supported but its requested time relation is not, the temporal claim remains unsupported or partially supported.

### Query reference time

Query-relative terms such as `today`, `currently`, or `recent` use an authoritative request/reference timestamp supplied through Stage 6 trusted control data rather than implicit provider runtime time.

This control value does not change the Stage 5 `GenerationContext` contract.

### No source-authority policy in V1

Stage 6 does not invent source credibility, domain trust, local-over-web precedence, freshness-as-truth, or majority-vote truth rules.

When asked which source is more credible, Stage 6 may report available structured facts such as provenance, acquisition completeness, independence/dependence, conflict, or degradation, but it cannot fabricate an authority ranking.

## Consequences

### Positive

- Grounding becomes an explicit claim-level contract instead of a prompt aspiration.
- Stage 5 evidence decisions are made once and remain authoritative downstream.
- Partial/insufficient answers cannot be silently upgraded by fluent generation.
- Temporal and conflict semantics remain testable through generation.
- Stage 7 can evaluate claim-support correctness directly.

### Negative

- `GenerationResult` must carry richer claim metadata than prose-only generation.
- Claim-support validation requires careful structural validation and later evaluation of semantic support quality.
- The final answer renderer must preserve structured claim/disclosure semantics.

## Alternatives Considered

### Sentence-level grounding only

Rejected because a sentence may contain multiple materially separable factual propositions and one supported clause must not hide an unsupported one.

### Allow model memory for harmless background facts

Rejected because the evidence boundary would become subjective and difficult to evaluate. Material factual content remains evidence-grounded.

### Recompute sufficiency/conflict in Stage 6

Rejected because those are accepted Stage 5 responsibilities under ADR-012/013.

### Introduce source-authority heuristics in Stage 6

Rejected for V1 because no accepted authority/trust policy exists.

## Revisit Triggers

Revisit this ADR if:

- Stage 7 shows `ContextItem`-level support binding is insufficient and Stage 5 must emit proposition-level support mappings,
- a reviewed source-authority/trust model is introduced,
- generated evidence compression becomes evidence-bearing,
- an always-on semantic verifier becomes part of the live generation path,
- model-memory factual augmentation is intentionally introduced under a new evidence policy.

## Affected Stages

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
- `docs/stages/05-context-assembly.md`
- `docs/stages/06-generation.md`
- `docs/architecture/decisions/ADR-011-evidence-relationship-and-corroboration-semantics.md`
- `docs/architecture/decisions/ADR-012-conflict-coverage-and-sufficiency-model.md`
- `docs/architecture/decisions/ADR-013-generation-context-and-stage-5-stage-6-boundary.md`
