# ADR-016: Citation Binding and Canonical Response Contract

## Status

Accepted

## Context

Stage 6 needs citations that remain faithful to authoritative provenance without requiring the model to invent source IDs, citation labels, or rendering syntax. It also needs a stable canonical response that downstream evaluation, observability, rendering, and serving can consume without reparsing prose.

Stage 1 permits answer/paragraph-level user-facing citation granularity in V1, while Stage 6 now has stronger internal claim-level support bindings. Those are compatible if support identity and display rendering remain separate layers.

## Decision

ASTRAG separates claim support, citation identity, citation rendering, and canonical response semantics.

### Claim-level citation binding

Citation binding is claim-level internally even when user-facing rendering aggregates citations at natural sentence or paragraph boundaries.

A material claim may bind one or more context/evidence items. A single evidence item may support multiple claims. Derived claims bind all premises materially required for the derivation.

### Citation identity is deterministic

The model does not invent citation IDs, numeric markers, URLs, document locations, or source identities.

Citation identity is resolved deterministically from validated claim support:

```text
AnswerClaim
→ supporting_context_item_ids[]
→ authoritative evidence IDs
→ source provenance
→ CitationBinding
```

Conceptually:

```text
CitationBinding
- citation_id
- claim_ids[]
- context_item_ids[]
- evidence_ids[]
- source_provenance
- source_span?
```

The exact schema may evolve while preserving these semantics.

### Rendering granularity

User-facing citations render at natural sentence/paragraph locations when the mapping remains unambiguous. Internal claim-level bindings remain available even if several adjacent claims share one rendered citation group.

The renderer may omit redundant visible citation repetition but may not erase materially distinct support needed to understand a conflict or derivation.

### Local provenance rendering

Local citations use human-readable source identity plus the most specific available stable location, such as document title with page/section/span information where available. Corpus identity may be shown when useful for disambiguation.

Missing provenance fields are never fabricated.

### Web provenance rendering

Web citations preserve the authoritative URL/source identity and may display source/site/title plus publication metadata when available.

Publication date must not be presented as event date merely because both are temporal metadata.

### Duplicate/derivative and independent support

Representative evidence plus alternate provenance from Stage 5 does not automatically render as multiple corroborating citations.

Derivative, duplicate, or dependence-unknown sources must not be presented as independent confirmation unless Stage 5 explicitly established independence.

When multiple independent supports exist, the renderer may choose a concise visible subset while preserving full structured support bindings. Stage 6 may describe support as independent only when Stage 5 relationship semantics justify that statement.

### Conflict citations

Each materially competing claim in a conflict retains its own support and citation binding. A combined citation group must not obscure which source supports which conflicting position.

Interpretation divergence follows the same principle: each supported interpretation remains separately attributable.

### Citation degradation

Citation display failure and grounding failure are distinct.

If authoritative support identity remains valid but display metadata cannot be fully rendered, Stage 6 may emit a `GENERATED_DEGRADED` response with explicit citation degradation disclosure and structured failure diagnostics.

If authoritative support identity itself is missing or cannot be resolved, the claim is not considered grounded and generation fails according to ADR-015.

### Validation order

Citation handling has two validation layers:

1. semantic binding/resolution validation before rendering,
2. presentation/placement validation after deterministic rendering.

### Canonical GeneratedResponse

Stage 6 produces a canonical structured response conceptually equivalent to:

```text
GeneratedResponse
- response_status
- content_blocks[]
- claims[]
- citations[]
- disclosures[]
- evidence_sufficiency
- generation_status
- degradation[]
- presentation_normalization
- generation_metadata
```

The canonical response is not tied to Markdown, HTML, CLI text, or one API representation.

Approved deterministic renderers may produce human-readable or machine-readable forms while preserving identical semantics.

Machine-readable outputs expose structured citation references rather than forcing prose markers into data fields.

### Response status

Semantic response status is distinct from generation execution status.

Initial semantic states include concepts such as:

```text
FULL_ANSWER
PARTIAL_ANSWER
INSUFFICIENT_EVIDENCE
```

Clarification/rejection flows remain upstream/non-applicable for normal generation unless a later cross-stage contract explicitly routes deterministic response rendering through Stage 6.

Semantic response status is monotonic with Stage 5 sufficiency. Stage 6 may become more conservative but may never upgrade evidence sufficiency.

### Presentation normalization

User presentation/schema requests are normalized before generation. Accepted, relaxed, or rejected constraints remain structured and traceable.

A user schema is honored only if it can represent mandatory grounding semantics, including conflict, uncertainty, partiality, and citations where required. Presentation requirements cannot force the renderer to fabricate certainty or omit mandatory disclosures.

Citation presence is part of ASTRAG grounding policy rather than an optional user style preference. Citation style may be configurable within supported renderers.

### Downstream immutability

After Stage 6 validates and constructs the canonical `GeneratedResponse`, downstream stages may:

- render through approved formatters,
- redact observability/storage views,
- block/refuse delivery under later guardrails,
- choose a compatible serving representation.

They must not silently alter factual claims, evidence bindings, citation meaning, conflict semantics, or sufficiency state.

Stage 10 owns transport/delivery rather than answer semantics.

### Output sanitization

Renderers sanitize target-channel output and restrict unsupported/executable markup. Grounding correctness does not imply safe HTML or safe client rendering.

User requests for raw executable markup are treated as bounded presentation requests subject to supported renderer/schema policy.

## Consequences

### Positive

- Citation IDs cannot hallucinate independently from evidence provenance.
- Internal grounding can be claim-level while user-facing citation presentation remains readable.
- Conflicting and derived claims retain precise attribution.
- Evaluation/API/UI layers receive one canonical semantic response instead of reparsing rendered text.
- Serving cannot silently mutate answer truth-state.

### Negative

- Stage 6 requires deterministic citation resolution and renderer implementations.
- Multiple renderer schemas must remain compatible with one canonical response model.
- Degraded citation display requires explicit status/diagnostics rather than silent fallback.

## Alternatives Considered

### Model-emitted `[1]` / `[source]` markers

Rejected because the model would partially own citation identity and formatting, making invalid or invented targets harder to prevent.

### Paragraph-level support only

Rejected because Stage 6 already needs atomic claim-level grounding and conflict/derivation attribution.

### Final Markdown as the only Stage 6 contract

Rejected because evaluation, observability, APIs, and serving would need to reconstruct semantics from presentation text.

## Revisit Triggers

Revisit this ADR if:

- Stage 5 must emit richer proposition-to-source-span support mappings,
- inline token-level attribution is required,
- user-facing semantic streaming is introduced,
- downstream serving needs a representation that cannot preserve the canonical response semantics,
- source-authority/trust metadata becomes part of citation semantics.

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
- `docs/stages/06-generation.md`
- `docs/architecture/decisions/ADR-013-generation-context-and-stage-5-stage-6-boundary.md`
- `docs/architecture/decisions/ADR-014-grounded-generation-and-claim-support-contract.md`
- `docs/architecture/decisions/ADR-015-structured-generation-validation-and-bounded-repair.md`
