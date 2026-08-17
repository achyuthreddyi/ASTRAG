# ADR-015: Structured Generation, Validation, and Bounded Repair

## Status

Accepted

## Context

ASTRAG Stage 6 must generate natural-language answers while preserving the evidence constraints established by Stage 5. Raw free-form completion followed directly by rendering would make claim binding, conflict preservation, sufficiency monotonicity, citation integrity, temporal precision, and provider failures difficult to validate consistently.

The generation layer also needs a provider-neutral execution model that remains bounded, observable, and reproducible without becoming an open-ended writer/verifier agent loop.

## Decision

ASTRAG adopts a structured, bounded Stage 6 execution model with deterministic control and validation.

### GenerationRequest

Stage 6 consumes one explicit request envelope conceptually equivalent to:

```text
GenerationRequest
- generation_context
- generation_control
- presentation_request
```

`generation_context` is the authoritative Stage 5 evidence-semantic contract.

`generation_control` contains trusted request/runtime constraints such as:

```text
GenerationControl
- query_reference_time
- query_timezone?
- generation_policy_version
- prompt_version
- output_constraints
- provider_config_ref
```

`presentation_request` contains only normalized user-facing presentation preferences that are compatible with grounding and safety invariants.

### Trust and instruction hierarchy

Stage 6 distinguishes conceptually:

```text
TRUSTED_CONTROL
TRUSTED_UPSTREAM_SEMANTICS
USER_REQUEST
UNTRUSTED_EVIDENCE_DATA
```

The authority hierarchy is deterministic. Retrieved evidence remains inert data and cannot mutate generation policy, retry budgets, citation rules, schema behavior, provider/tool permissions, or other control-plane state.

User preferences may affect presentation only when compatible with grounding, citation, conflict, sufficiency, temporal, and safety invariants.

### Prompt construction

Stage 6 owns prompt construction and assembles typed, versioned sections deterministically rather than relying on one unstructured template blob.

Logical sections include system policy, grounding contract, sufficiency/disclosure requirements, output schema, question semantics, evidence envelopes, and presentation constraints.

Both `original_question` and `resolved_query` are available with explicit roles. Conversation context is limited to approved current-query interpretive/presentation state; raw conversation history is not injected as factual evidence.

Evidence text is faithfully preserved and structurally delimited/escaped as untrusted data. Prompt-like source text is not stripped merely because it resembles an instruction.

### Provider-neutral boundary

ASTRAG defines one provider-neutral generation contract. Provider adapters translate API/message format, structured-output mechanisms, token accounting, transport behavior, and provider-native errors without changing ASTRAG grounding semantics.

Adapters should use native schema-constrained structured output when available. A bounded validated fallback may support providers without native schema enforcement, but prose-only JSON hope is not the architecture contract.

Provider fallback is permitted only when explicitly configured as compatible with the same generation contract, policy/schema requirements, and evaluation profile. Provider transitions are observable.

### Structured GenerationResult

The model does not directly own final user-facing Markdown/HTML. It returns a structured result conceptually equivalent to:

```text
GenerationResult
- generation_status_proposal
- claims[]
- disclosures[]
- answer_blocks[]
```

Claims contain natural-language text plus support/inference bindings. Ordered answer blocks reference claims/disclosures and provide bounded presentation structure. Final target-channel markup is owned by deterministic rendering.

### Validation layers

Stage 6 validates model output in explicit layers:

1. **Schema validation** — required fields, enum values, size limits, structured-output integrity.
2. **Referential validation** — context/evidence/conflict/coverage references exist and are legal.
3. **Grounding/semantic-invariant validation** — material claims have valid support bindings, sufficiency is not upgraded, required conflicts/disclosures survive, temporal precision is not strengthened, and known structured invariants are respected.
4. **Presentation/citation validation** — required disclosures/citations are rendered safely and target-channel structure is valid.

Model-declared support/status fields are proposals. The deterministic validator is authoritative.

Deterministic validation does not pretend to prove arbitrary natural-language entailment. Deeper semantic support quality is exposed to Stage 7 evaluation and may use bounded semantic checking only if explicitly added later.

### Bounded repair

When validation fails, Stage 6 follows a bounded repair sequence:

```text
initial generation
→ validation
→ safe deterministic repair when possible
→ otherwise at most one constrained repair generation
→ revalidation
→ success or fail closed
```

Deterministic repair may normalize structure, resolve IDs, deduplicate bindings, insert machine-known required disclosures, or remove an unsupported optional claim when coherence remains intact. It may not invent or substantively rewrite factual content.

Repair generation receives the original `GenerationRequest`, the previous structured result, and sanitized machine-produced validation reason codes. Retrieved source text is never promoted into repair-control instructions.

Repair operates over the same `GenerationContext` and immutable evidence boundary. It cannot initiate retrieval or widen source scope.

V1 permits one initial semantic generation attempt plus at most one repair-generation attempt.

### Transport retry is distinct from semantic retry

Provider transport attempts and semantic generation attempts are separate bounded counters.

Transient provider failures may use bounded provider-aware retry/backoff without consuming a semantic repair attempt when no completed model result was produced.

Stable provider-neutral failures include categories such as:

```text
INVALID_GENERATION_REQUEST
PROMPT_BUDGET_EXCEEDED
PROVIDER_UNAVAILABLE
PROVIDER_TIMEOUT
PROVIDER_RATE_LIMITED
PROVIDER_AUTH_FAILURE
PROVIDER_REJECTED_REQUEST
MALFORMED_PROVIDER_RESPONSE
STRUCTURED_OUTPUT_INVALID
REFERENTIAL_VALIDATION_FAILED
GROUNDING_VALIDATION_FAILED
REQUIRED_DISCLOSURE_MISSING
CITATION_RESOLUTION_FAILED
REPAIR_EXHAUSTED
INTERNAL_GENERATION_ERROR
```

Provider-native codes/details remain diagnostic metadata.

Failure records carry explicit retryability semantics rather than requiring call sites to parse exception strings.

### Token and output budgets

Stage 6 owns complete model-request budget validation while Stage 5 owns evidence-context selection/budgeting.

Generation budget accounting distinguishes at least:

```text
model_context_limit
generation_context_tokens
instruction_tokens
question_control_tokens
schema_overhead_tokens
repair_reserve_tokens
max_output_tokens
safety_margin_tokens
```

Stage 6 may not silently drop Stage 5-selected material evidence to fit provider limits. It requires a configured output reserve sufficient for expected answer/citation/disclosure content. If the complete request cannot fit safely, it fails structurally before invocation.

User verbosity/length requests are subordinate to mandatory grounding/disclosure requirements.

Provider truncation is an execution failure unless a complete valid structured result is independently established.

### Validate before release

V1 does not stream unvalidated semantic model output to the user.

Provider-internal streaming may be used as an implementation detail, but the user-facing grounded response is released only after complete structured validation and rendering.

### Execution result

Stage 6 returns an explicit wrapper conceptually equivalent to:

```text
GenerationExecutionResult
- generation_status
- generated_response?
- failure?
- trace_ref
- generation_metadata
```

Execution status is distinct from Stage 5 evidence sufficiency and from semantic response type.

High-level execution states include:

```text
GENERATED
GENERATED_DEGRADED
FAILED
NOT_APPLICABLE
```

`NOT_APPLICABLE` means normal generation should not have run because the upstream workflow ended in a terminal non-generation state. `FAILED` means generation was applicable but Stage 6 could not safely complete.

After repair exhaustion, Stage 6 fails closed and may return only a deterministic system-owned failure response describing known execution state, never unsupported answer content.

### Versioning and reproducibility

Every execution records at least:

```text
prompt_version
generation_policy_version
generation_schema_version
renderer_version
provider_adapter_version
model_id
model_config_ref
```

Sampling/randomness parameters are explicit versioned configuration rather than provider defaults.

`GenerationRequest`, `GenerationResult`, and downstream response schemas are explicitly versioned. Additive compatible evolution is preferred; incompatible changes require coordinated contract updates.

Byte-identical generated prose is not guaranteed for probabilistic models. Deterministic components such as prompt assembly, budget validation, ID resolution, structural validation, deterministic repair, citation resolution, rendering, and sanitization must be reproducible for identical input/version.

## Consequences

### Positive

- Generation behavior is bounded and auditable.
- Provider failures are separated from semantic model-output failures.
- Invalid structured or unsupported outputs cannot be released merely because they are fluent.
- Provider/model choice can evolve behind a stable semantic contract.
- Stage 7/8 receive explicit validation, repair, version, and attempt data.

### Negative

- Stage 6 implementation is more involved than a direct LLM call.
- Schema and provider adapters require compatibility testing.
- V1 deliberately sacrifices token-by-token answer streaming for validate-before-release correctness.

## Alternatives Considered

### Free-form final-text completion

Rejected because claim/citation/support validation would depend on post-hoc extraction and fragile parsing.

### Planner/drafter/verifier multi-call pipeline

Rejected for V1 because it adds latency, cost, nondeterministic control complexity, and an unnecessary pseudo-agent loop before benchmarks justify it.

### Unlimited generation retries

Rejected because execution must remain bounded and observable.

### Always-on second-model verifier

Rejected for the normal V1 path. Evaluation may use semantic judges offline, and future benchmarks may justify an explicit live verifier architecture.

## Revisit Triggers

Revisit this ADR if:

- user-visible semantic streaming is introduced,
- live multi-model verification becomes mandatory,
- more than one semantic repair-generation attempt is justified,
- provider fallback changes grounding semantics,
- Stage 6 becomes distributed/long-running or gains durable resume semantics,
- a provider cannot meet the required structured-output contract without material architecture change.

## Affected Stages

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
