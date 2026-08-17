# Stage 6: Generation Layer

## Status

**Implementation Ready pending orchestrator reconciliation of this branch against latest `main`.**

The Stage 6 architecture review is complete. ADR-014, ADR-015, and ADR-016 define the accepted generation invariants. This stage document consolidates the accepted design and identifies the required global architecture/roadmap deltas.

Stage 6 does not require a semantic change to ADR-013 or the Stage 5 `GenerationContext` contract for V1. Stage 6 wraps `GenerationContext` with trusted runtime control and normalized presentation state; it does not require Stage 5 to precompute proposition-level answer claims.

## Goal

Transform an assembled Stage 5 `GenerationContext` into a validated, evidence-grounded, provenance-backed canonical `GeneratedResponse` while preserving sufficiency, conflict, temporal uncertainty, evidence-policy boundaries, and source provenance.

The Stage 6 V1 path is intentionally bounded and deterministic at the control plane:

```text
GenerationContext
+ trusted GenerationControl
+ normalized PresentationRequest
        ↓
GenerationRequest
        ↓
Request / budget validation
        ↓
Deterministic versioned prompt construction
        ↓
Provider-neutral generation adapter
        ↓
Structured GenerationResult
        ↓
Schema + referential + grounding validation
        ↓
Safe deterministic repair when possible
        ↓
At most one constrained repair generation
        ↓
Revalidation
        ↓
Deterministic citation resolution
        ↓
Canonical GeneratedResponse
        ↓
Presentation/citation validation + sanitization
        ↓
GenerationExecutionResult
```

No user-visible semantic model output is released before validation completes.

## Requirements

### Evidence grounding

- Every material factual proposition must be supported by evidence permitted by the immutable `EvidencePolicy`.
- Model pretraining may assist language, interpretation, and bounded reasoning but cannot independently add material factual content.
- Stage 6 may never expand the legal evidence set.
- Stage 6 does not initiate retrieval or adjacent-context fetching.
- Conversation history is not factual evidence.

### Stage 5 semantic authority

`GenerationContext` is authoritative for:

- evidence identity/provenance,
- evidence relationship/dependence semantics,
- material conflict groups,
- semantic coverage,
- final evidence sufficiency,
- supported/unsupported aspects,
- required-source statuses,
- source failures/degradation,
- temporal role/precision/certainty,
- interpretation assumptions.

Stage 6 may organize and phrase these semantics but may not recompute or override them.

### Sufficiency monotonicity

Stage 6 may become more conservative than Stage 5 but never more confident.

```text
SUFFICIENT
→ full grounded answer or more conservative

PARTIALLY_SUFFICIENT
→ partial answer or more conservative

INSUFFICIENT
→ evidence-status / insufficient-evidence response
```

### Conflict preservation

Material conflicts must remain visible when relevant to answer content.

Stage 6 does not:

- majority-vote truth,
- choose a winner because one side has more retrieved sources,
- invent source authority,
- merge conflicting exact dates into an artificial range,
- suppress a conflict for cleaner prose.

Interpretation divergence is rendered as competing supported interpretations rather than mislabeled factual contradiction.

### Temporal fidelity

Temporal generation must preserve:

- event/content time vs source/publication time,
- exact vs approximate/range/uncertain values,
- BCE/CE semantics,
- unresolved relative expressions,
- calendar ambiguity where normalization is not authoritative.

Temporal derivations may preserve or reduce input precision, never increase it.

### Citation integrity

- Citation binding is claim-level internally.
- Model output may reference only enumerated prompt-visible context IDs.
- The model never invents final citation IDs, URLs, document identities, pages, or source locations.
- Deterministic code resolves validated claim bindings to authoritative evidence/provenance and creates citation identities.
- Derived claims cite all material premises.
- Competing conflict claims retain distinct citations.
- Duplicate/derivative/unknown-dependence provenance cannot be presented as independent confirmation.

### Bounded execution

- One normal semantic generation call.
- At most one constrained repair-generation call.
- Transport retries are separately bounded and do not become an open-ended semantic loop.
- Generation fails closed after exhaustion.

### Validate before release

V1 does not stream unvalidated semantic answer content to the user.

Provider-internal streaming is permitted only as an implementation detail if the complete structured response remains withheld until validation succeeds.

## Inputs

### Stage 5 input

Stage 6 consumes the accepted ADR-013 `GenerationContext`:

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

Each selected `ContextItem` retains prompt-visible identity and authoritative evidence/provenance mapping:

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

### GenerationRequest

Stage 6 wraps `GenerationContext` with trusted control and presentation state:

```text
GenerationRequest
- generation_context
- generation_control
- presentation_request
```

### GenerationControl

Conceptually:

```text
GenerationControl
- generation_request_id
- query_reference_time
- query_timezone?
- generation_policy_version
- prompt_version
- generation_schema_version
- renderer_version
- provider_config_ref
- provider_adapter_version
- model_id
- model_config_ref
- output_constraints
- generation_budget
```

`query_reference_time` is authoritative for query-relative terms such as `today`, `currently`, and `recent`. It is trusted runtime/control data, not Stage 5 evidence semantics.

Sampling/randomness parameters belong to explicit versioned model configuration rather than provider defaults.

### PresentationRequest

User presentation requests are normalized into bounded structured preferences. Conceptually:

```text
PresentationRequest
- response_format
- verbosity?
- tone?
- organization_preferences[]
- requested_fields[]
- citation_style_preference?
```

Normalization records accepted, relaxed, and rejected constraints. User preferences cannot override grounding/citation/conflict/sufficiency/safety invariants.

## Prompt Authority and Construction

### Trust classes

Stage 6 distinguishes these conceptual trust classes:

```text
TRUSTED_CONTROL
TRUSTED_UPSTREAM_SEMANTICS
USER_REQUEST
UNTRUSTED_EVIDENCE_DATA
```

Retrieved content remains data only. A document that contains `ignore previous instructions` may be analyzed or cited if relevant, but that text has no authority to mutate generation behavior.

### Authority hierarchy

Prompt construction preserves a deterministic hierarchy:

1. system/generation policy,
2. trusted `GenerationControl`,
3. grounding/schema/safety instructions,
4. normalized presentation constraints,
5. original/resolved question semantics,
6. retrieved evidence data.

Provider message-role mechanics implement this hierarchy; they do not define ASTRAG semantics.

### Typed prompt sections

The prompt is assembled deterministically from typed/versioned sections, for example:

```text
GenerationPrompt
- system_policy_section
- grounding_contract_section
- sufficiency_section
- disclosure_requirements_section
- output_schema_section
- question_section
- evidence_section
- presentation_section
```

Evidence is inserted into clearly delimited typed envelopes containing context ID, provenance metadata, temporal metadata, and selected source text. Prompt-like evidence content is preserved faithfully rather than removed or rewritten.

Both `original_question` and `resolved_query` are available with distinct roles:

- original question preserves user wording/presentation intent,
- resolved query provides authoritative upstream semantic interpretation.

## Generation Model

### Provider-neutral interface

Stage 6 uses a provider-neutral logical generation interface. Provider adapters may vary in:

- API message format,
- schema-constrained output mechanism,
- token counting,
- stop/truncation behavior,
- transport errors,
- authentication/rate limits,
- provider-native diagnostics.

Adapters may not redefine evidence legality, conflict behavior, sufficiency monotonicity, citation semantics, or grounding requirements.

Native schema-constrained structured output is preferred. A bounded validated fallback is permitted for providers lacking native schema enforcement if it still satisfies the Stage 6 structured-result contract.

### Structured GenerationResult

The model returns structured semantic output rather than final target-channel Markdown/HTML.

Conceptually:

```text
GenerationResult
- generation_status_proposal
- claims[]
- disclosures[]
- answer_blocks[]
```

### AnswerClaim

Conceptually:

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

Claim granularity is atomic proposition / materially separable clause level.

Initial support concepts:

```text
SUPPORTED
SUPPORTED_DERIVED
UNSUPPORTED
```

Conflict is represented independently from support status.

Inference classification is structured and extensible. V1 includes concepts such as:

```text
DIRECT
MULTI_EVIDENCE_SYNTHESIS
TEMPORAL_DERIVATION
COMPARATIVE_DERIVATION
```

Exact enum names are implementation/schema details as long as these semantics remain available.

### Answer organization

The model emits ordered structured answer blocks that reference claims/disclosures. Conceptually:

```text
AnswerBlock
- block_id
- block_type
- claim_ids[]
- disclosure_ids[]
- heading?
```

The model may write natural-language claim text but does not own arbitrary final markup.

## Claim-Support Semantics

### Material claims

A proposition requires explicit evidence support when falsifying it would materially change the user's understanding of the answer. This includes factual dates, identities, quantities, events, source-reporting statements, causal assertions presented as facts, and other material world claims.

Pure presentation/transition language does not require an evidence binding.

### Support binding

The model binds claims only to enumerated `context_item_id` values. Deterministic code resolves those IDs to authoritative evidence/provenance.

One claim may bind multiple evidence items. One evidence item may support multiple claims.

No minimum-two-source rule exists. Stage 5 already owns dependence/corroboration semantics.

### Derived claims

A derived claim is allowed only when the conclusion follows from supplied evidence without unsupported premises.

For example:

```text
Evidence A: event X occurred in 1914
Evidence B: event Y occurred in 1918
Derived: X occurred before Y
```

The derived claim binds both necessary premises and is classified as a derivation rather than a direct source statement.

### Unsupported claims

An unsupported material claim is a validation failure. Uncertainty wording does not convert an unsupported proposition into a grounded one.

A deterministic repair may remove an unsupported optional claim only when the response remains coherent and substantively unchanged.

## Conflict, Uncertainty, and Sufficiency

### Material conflict

Each material conflict used in answer content must be disclosed. Each materially supported side retains its own claim/citation support.

Stage 6 can phrase the disagreement naturally but cannot nominate a winner unless a future accepted upstream authority/truth policy provides one.

### Unknown dependence

`UNKNOWN_DEPENDENCE` is surfaced when Stage 6 would otherwise imply independent corroboration or when the uncertainty materially affects confidence/interpretation. It need not produce repetitive boilerplate when irrelevant to the answer.

### Required-source failure

Failure of a required source is user-visible even when remaining evidence is sufficient. Sufficiency means answerable from the available permitted evidence; it does not mean all required retrieval obligations succeeded perfectly.

### Partial sufficiency

For `PARTIALLY_SUFFICIENT`, Stage 6 must:

1. answer supported aspects,
2. identify unsupported/partially supported aspects,
3. avoid completion from model memory,
4. disclose relevant required-source failures/degradation,
5. preserve material conflicts.

### Insufficient evidence

`INSUFFICIENT` produces a precise evidence-state response rather than a generic claim that the model itself lacks knowledge.

The response may explain which requested aspect lacks support and known retrieval limitations. It may include clearly separable supported contextual facts when that helps explain insufficiency without implying that the unsupported requested proposition was answered.

## Temporal Answer Semantics

### Typed temporal role

Stage 6 uses the temporal semantic role appropriate to each claim. Publication/source date supports claims about publication/source time; event/content date supports claims about the event/content.

### TemporalClaimSemantics

Material temporal claims may carry structured metadata conceptually equivalent to:

```text
TemporalClaimSemantics
- temporal_role
- value_or_range
- precision
- certainty
- calendar_era?
- source_context_item_ids[]
```

### Relative expressions

Relative expressions are resolved only when the anchor and arithmetic are unambiguous. Otherwise the relative form/uncertainty is preserved.

Resolved relative dates are `TEMPORAL_DERIVATION` claims and bind the relation evidence plus anchor evidence.

### Precision monotonicity

Temporal derivation may preserve or reduce precision, never increase it.

`circa 1200 BCE` and `circa 1100 BCE` may support `roughly a century apart`; they do not support `exactly 100 years apart`.

### BCE/CE and calendar arithmetic

Comparison/arithmetic requiring BCE/CE semantics uses deterministic temporal utilities rather than unconstrained model calculation.

Ambiguous historical calendar conversion is not performed unless authoritative normalized calendar metadata exists.

### Requested temporal scope

A role/entity relationship without evidence tying it to the requested date does not satisfy a historical `who held role X in year Y` query.

## Citation Architecture

### CitationBinding

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

Citation IDs are deterministic and application-owned.

### Rendering

Human-facing citations render at natural sentence/paragraph locations while maintaining unambiguous support. Internal claim-level mappings remain available for evaluation and machine-readable response forms.

Local citations expose human-readable source identity and the most specific available stable location.

Web citations preserve URL/source identity and may display source/site/title/publication metadata where available.

### Citation degradation

If claim grounding remains authoritative but display metadata cannot be fully rendered, Stage 6 may return `GENERATED_DEGRADED` with an explicit citation degradation disclosure and structured diagnostics.

If authoritative support identity cannot be resolved, grounding fails rather than degrading to an invented citation.

## Validation

### Schema validation

Validates:

- required fields,
- schema version,
- enum values,
- structural size/budget limits,
- complete structured provider output.

Provider truncation or malformed envelopes do not become partial success.

### Referential validation

Validates that referenced:

- context items,
- evidence identities,
- conflict groups,
- coverage units,
- disclosure identifiers

exist and are legal for the current request.

### Grounding / semantic-invariant validation

Checks deterministically enforceable invariants such as:

- material factual claims have support bindings,
- model IDs resolve to real context IDs,
- sufficiency is not upgraded,
- required conflict/disclosure semantics are not omitted,
- known temporal precision is not increased,
- dependence semantics are not falsely promoted to independence,
- citation support identity is authoritative.

General natural-language entailment is not claimed to be deterministically solved in V1. Stage 7 evaluates deeper semantic support correctness and may motivate future bounded semantic-verifier architecture.

### Stable reason codes

Validation emits stable reason codes such as:

```text
UNKNOWN_CONTEXT_ITEM
UNSUPPORTED_MATERIAL_CLAIM
INVALID_DERIVATION
SUFFICIENCY_UPGRADE
MISSING_CONFLICT_DISCLOSURE
TEMPORAL_PRECISION_INCREASED
REQUIRED_SOURCE_FAILURE_OMITTED
INVALID_CITATION_BINDING
UNRESOLVABLE_CITATION
PRESENTATION_CONSTRAINT_CONFLICT
```

Exact taxonomy is versioned/extensible.

## Repair

### Safe deterministic repair

Permitted examples:

- normalize bounded output structure,
- resolve canonical IDs,
- deduplicate citation bindings,
- insert machine-known mandatory disclosures,
- repair deterministic formatting,
- remove an unsupported optional claim when coherence remains intact.

Deterministic repair must not rewrite substantive factual prose to invent support.

### Repair generation

If deterministic repair cannot safely fix the result, Stage 6 may run one constrained repair generation using:

- original `GenerationRequest`,
- previous structured result,
- sanitized machine-produced validation failures.

Repair cannot retrieve new evidence or change `EvidencePolicy`.

### Exhaustion

After the bounded repair-generation attempt, invalid output fails closed.

## Token / Output Budgeting

Stage 5 owns evidence-context selection and budgeting. Stage 6 owns the complete provider-request budget.

Conceptually:

```text
GenerationBudget
- model_context_limit
- generation_context_tokens
- instruction_tokens
- question_control_tokens
- schema_overhead_tokens
- repair_reserve_tokens
- max_output_tokens
- safety_margin_tokens
```

Stage 6 cannot silently trim material Stage 5 evidence to fit provider limits. If the complete request plus configured output/disclosure reserve does not fit, Stage 6 returns a structured budget failure before provider invocation.

User length constraints are soft when they conflict with mandatory grounding/disclosure requirements.

## Provider Failure Handling

### Provider-neutral taxonomy

Stable Stage 6 failures include concepts such as:

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

Provider-native details remain attached diagnostically.

### Retryability

Failures carry explicit retry semantics such as retryable same request, retry after backoff, repairable model output, or non-retryable request/policy failures.

### Transport vs semantic attempts

Transport attempts and semantic generation attempts are independently bounded.

A timeout before a completed provider result is not the same as a completed but grounding-invalid model answer.

### Provider fallback

A fallback provider/model is allowed only when configured as compatible with the current generation policy/schema contract. Provider transitions are traced explicitly.

Repair attempts normally remain on the same configured model unless fallback policy explicitly permits semantic-attempt migration.

## Outputs

### Canonical GeneratedResponse

Conceptually:

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

The canonical response is independent of Markdown/HTML/API/CLI transport representation.

Semantic response states include concepts such as:

```text
FULL_ANSWER
PARTIAL_ANSWER
INSUFFICIENT_EVIDENCE
```

### GenerationExecutionResult

Conceptually:

```text
GenerationExecutionResult
- generation_status
- generated_response?
- failure?
- trace_ref
- generation_metadata
```

High-level execution states:

```text
GENERATED
GENERATED_DEGRADED
FAILED
NOT_APPLICABLE
```

Evidence sufficiency, semantic response status, and generation execution status are separate dimensions.

### Downstream immutability

Once validated, canonical `GeneratedResponse` semantics are immutable downstream. Later stages may render, redact observability views, block delivery, or choose a compatible transport representation. They may not silently change factual claims, citations, conflict semantics, or sufficiency.

## Evaluation Hooks

Stage 6 must expose enough structured data for Stage 7 to evaluate at least:

- claim-grounding precision,
- unsupported-claim rate,
- claim-support correctness,
- citation-binding accuracy,
- citation-rendering accuracy,
- required-disclosure recall,
- conflict-preservation rate,
- temporal-precision preservation,
- sufficiency compliance,
- schema validity,
- deterministic/semantic repair rates,
- generation failure rate,
- provider/fallback behavior,
- latency/token/cost metrics.

Stage 6 exposes the artifacts/events required for these measurements. Stage 7 owns dataset design, scoring methodology, benchmark thresholds, and pass/fail policy.

No always-on second-LLM evaluator/verifier is required on the Stage 6 V1 live path.

## Observability

### GenerationTrace

Each Stage 6 execution produces a structured internal trace conceptually equivalent to:

```text
GenerationTrace
- query_id
- generation_request_id
- generation_attempts[]
- provider_attempts[]
- prompt_version
- generation_policy_version
- generation_schema_version
- renderer_version
- provider_adapter_version
- model_id
- validation_results[]
- repair_actions[]
- citation_resolution_results[]
- final_status
- timing_metrics
- token_metrics
```

Repair attempts reference parent attempt IDs and repair reason codes. Provider fallback records source/destination provider, fallback reason, and compatibility profile.

### Retention/privacy boundary

Exact rendered prompts, evidence text, and raw provider request/response payloads are optional policy-controlled diagnostics.

The mandatory trace favors stable evidence/context references, hashes/metadata, version IDs, validation outcomes, and attempt lineage. Full source text need not be duplicated into every Stage 6 trace.

Observability redaction is a storage/view transformation and cannot mutate canonical grounding semantics.

Hidden model chain-of-thought is neither required nor a Stage 6 observability dependency.

## Security / Control Boundary

- Retrieved content is always untrusted data.
- Evidence cannot mutate control state or provider/tool permissions.
- Stage 6 performs no arbitrary tool execution or side effects in V1 beyond configured model-provider calls.
- User requests cannot disable mandatory grounding/citations/conflict disclosure.
- Renderer sanitization owns target-channel safety such as unsupported markup/HTML escaping.
- Raw user executable markup requests are constrained to approved renderer behavior.

Stage 9 may later add cross-cutting guardrails/reliability controls. It may block or become more conservative but must not weaken Stage 6 grounding invariants.

## Proposed Architecture

Logical components:

1. **Generation Request Builder**
   - wraps `GenerationContext` with trusted control and normalized presentation state,
   - establishes version/config identity.

2. **Presentation Normalizer**
   - classifies user output instructions,
   - accepts/relaxes/rejects incompatible presentation constraints.

3. **Prompt Builder**
   - assembles typed/versioned prompt sections,
   - isolates untrusted evidence data.

4. **Provider Adapter**
   - implements provider-neutral structured generation,
   - normalizes provider transport errors/truncation.

5. **Generation Validator**
   - schema validation,
   - referential validation,
   - structured grounding-invariant validation,
   - stable reason codes.

6. **Repair Controller**
   - applies safe deterministic repair,
   - permits at most one constrained semantic repair generation.

7. **Citation Resolver**
   - maps validated claim support to authoritative provenance,
   - constructs deterministic citation bindings.

8. **Canonical Response Builder**
   - builds immutable `GeneratedResponse` semantics.

9. **Renderer / Sanitizer**
   - creates approved target-channel representations,
   - validates citation placement/presentation.

10. **Trace Emitter**
    - produces structured generation lifecycle/attempt/validation/version events.

These are logical components. V1 does not require separate services/processes for them.

## Data Flow

```text
ContextAssemblyResult
        ↓
ASSEMBLED?
        ├── no → NOT_APPLICABLE / upstream terminal flow
        └── yes
              ↓
      GenerationContext
              +
      GenerationControl
              +
      PresentationRequest
              ↓
      GenerationRequest
              ↓
      request/schema/budget validation
              ↓
      deterministic prompt assembly
              ↓
      configured ProviderAdapter
              ↓
      bounded transport attempts
              ↓
      GenerationResult
              ↓
      schema validation
              ↓
      referential validation
              ↓
      grounding-invariant validation
              ↓
      deterministic repair if safe
              ↓
      optional repair generation
              ↓
      revalidation
              ↓
      citation resolution
              ↓
      GeneratedResponse
              ↓
      renderer + presentation validation
              ↓
      GenerationExecutionResult
```

## Failure Handling

### Invalid request/configuration

Invalid schema, incompatible provider/schema/renderer configuration, or impossible token budget fails before model invocation when detectable.

Deployment/startup should validate configured provider adapter, structured-output mechanism, prompt/schema versions, token limits, renderers, and fallback compatibility where practical.

### Provider failure

Provider-specific errors normalize into stable Stage 6 failures and structured retryability. Transient transport failures may retry boundedly without changing evidence/prompt semantics.

### Invalid model result

Invalid schema/references/grounding semantics use deterministic repair when safe, otherwise one bounded repair generation, then fail closed.

### Citation degradation

Valid grounding with incomplete display metadata may produce `GENERATED_DEGRADED`. Missing authoritative support identity is a grounding failure.

### Safe failure response

When Stage 6 fails after generation was applicable, any user-visible failure message is deterministic/system-owned and only states known execution status. It does not perform another unrestricted model call.

## Scalability

V1 remains single-tenant, low-concurrency, interactive, and bounded.

Stage 6 does not require:

- distributed generation orchestration,
- queues,
- durable workflow resume,
- multi-provider fan-out,
- multi-agent writer/verifier pools.

Provider/model invocation is the dominant external dependency. Stage 10 may later alter deployment/process topology while preserving the accepted semantic contracts.

## Latency / Throughput

The normal path uses one semantic generation call. A second call occurs only after validation failure requiring semantic repair.

Transport retries are separately bounded.

Evaluation should measure:

- prompt construction/token-count latency,
- provider latency,
- validation latency,
- repair incidence and additional latency,
- citation resolution/render latency,
- end-to-end generation latency,
- token/cost impact of structured output and repair.

V1 deliberately trades user-visible token streaming for validate-before-release correctness.

## Alternatives Considered

### Direct free-form LLM answer

Rejected because grounding/citation/conflict semantics would be difficult to validate reliably and downstream consumers would need to reconstruct semantics from prose.

### Separate generative evidence summarization before answer

Rejected for V1. Stage 5 already produces bounded evidence context using provenance-preserving extractive selection.

### Planner → drafter → verifier pipeline

Rejected for V1 because bounded structured single-generation plus validation provides a simpler baseline for evaluation.

### Stage 6 reranks or retrieves more evidence

Rejected because evidence selection and retrieval belong upstream. Stage 6 operates only over accepted `GenerationContext`.

### Mandatory online semantic judge

Rejected for the normal V1 path. Stage 7 may evaluate deeper claim support offline and future benchmarks may justify a reviewed live verifier.

## Decisions

Accepted architecture is recorded in:

- ADR-014 — grounded generation and claim-support contract,
- ADR-015 — structured generation, validation, and bounded repair,
- ADR-016 — citation binding and canonical response contract.

ADR-013 remains accepted without amendment in V1 because `GenerationContext` still exposes the evidence/provenance semantics required for Stage 6 claim binding.

## Assumptions

- ADR-001 through ADR-013 remain accepted upstream architecture.
- ADR-014 through ADR-016 define Stage 6.
- Stage 5 returns provenance-complete selected `ContextItem` values sufficient for claim-level binding.
- V1 is single-tenant, low-concurrency, bounded, and interactive.
- Exact prompt wording, model/provider, sampling values, token margins, transport retry counts, timeouts, and renderer style are versioned implementation/evaluation configuration as long as they preserve accepted invariants.

## Dependencies

- Stage 5 `ContextAssemblyResult` / `GenerationContext`,
- ADR-011/012 relationship/conflict/sufficiency semantics,
- ADR-013 Stage 5 → Stage 6 boundary,
- a provider adapter capable of reliable structured result delivery,
- deterministic schema/reference/temporal/citation utilities,
- Stage 7 evaluation datasets/metrics for deeper semantic quality,
- Stage 8 trace backend/retention decisions later.

## Out of Scope

V1 explicitly excludes:

- new retrieval from generation,
- adjacent datastore/context fetch,
- open-ended agentic generation loops,
- mandatory multi-agent writer/verifier workflows,
- generative evidence compression,
- source-authority/trust ranking,
- model-memory factual augmentation,
- user-visible semantic token streaming before validation,
- arbitrary tool execution from Stage 6,
- long-running/asynchronous generation workflows,
- self-modifying prompt policy,
- hidden chain-of-thought persistence,
- Stage 7 runtime rewriting/judging of live responses,
- Stage 8 trace data as factual evidence authority.

## Open Questions

No unresolved architecture blocker remains for Stage 6 V1.

Implementation/evaluation configuration still needs selection during implementation, including:

- concrete generation provider/model,
- concrete structured-output SDK/API mechanism,
- exact prompt wording and prompt versioning storage,
- exact token reserve/safety margins,
- exact bounded transport retry counts/backoff,
- exact rendering styles,
- concrete schema serialization/types,
- trace retention/redaction policy.

These do not require a new ADR unless they change accepted semantic contracts.

## Acceptance Criteria

Stage 6 implementation is not complete until representative tests/benchmarks demonstrate at least:

- **0** illegal evidence-source expansion,
- model-generated context/citation identities cannot escape deterministic referential validation,
- unsupported material claims are rejected when structurally detectable,
- Stage 5 sufficiency is never upgraded,
- material conflict disclosure is not silently suppressed,
- required-source failures are surfaced according to policy,
- temporal precision/certainty is not strengthened downstream,
- conflicting exact dates are not silently converted into synthetic ranges,
- derived claims bind material premises,
- duplicate/derivative/unknown-dependence evidence is not falsely labeled independent,
- citation IDs resolve only to authoritative provenance,
- no user-visible semantic output is released before validation,
- semantic generation attempts are bounded,
- transport retries are bounded independently,
- repair exhaustion deterministically fails closed,
- provider/model/prompt/schema/renderer versions are traceable,
- deterministic components reproduce identical outputs for identical input/version,
- provider fallback transitions are explicit and traceable,
- target-channel rendering is sanitized,
- evaluation/observability artifacts are emitted without requiring hidden chain-of-thought.

Deeper claim-support correctness, citation correctness, temporal answer quality, partial/insufficient-answer quality, and repair effectiveness are benchmarked by Stage 7.

## Impact

### Stage 5

No V1 semantic contract delta is required.

`GenerationContext` remains the authoritative evidence handoff. Stage 6 consumes existing `ContextItem` IDs/provenance and binds its generated propositions downstream. ADR-013 is therefore not amended merely to introduce `GenerationRequest` or claim structures owned by Stage 6.

ADR-013 must be revisited if evaluation proves Stage 6 requires proposition-level source-span mappings that Stage 5 cannot provide through current `ContextItem`/conflict/coverage semantics.

### Stage 7 handoff

Stage 7 should consume an evaluation-facing record conceptually including:

```text
GenerationEvaluationRecord
- generation_request_summary
- generation_result
- generated_response
- claim_support_bindings
- citation_bindings
- validation_results
- repair_history
- generation_trace_ref
- version_refs
```

Stage 7 owns benchmark datasets, judging/scoring methodology, thresholds, regressions, and end-to-end quality gates. It does not become an always-on V1 runtime judge.

### Stage 8 handoff

Stage 8 should formalize structured generation lifecycle events such as:

```text
GENERATION_REQUEST_VALIDATED
PROVIDER_ATTEMPT_STARTED
PROVIDER_ATTEMPT_FAILED
GENERATION_RESULT_RECEIVED
VALIDATION_FAILED
DETERMINISTIC_REPAIR_APPLIED
REPAIR_GENERATION_STARTED
CITATIONS_RESOLVED
GENERATION_COMPLETED
GENERATION_FAILED
```

Exact event names may evolve, but attempt lineage, version identity, validation outcomes, repair actions, citation-resolution status, latency, and token metrics must remain observable.

### Stage 9 handoff

Stage 9 may add cross-cutting safety/reliability/prompt-injection controls but cannot weaken evidence grounding, evidence-as-data separation, citation integrity, sufficiency monotonicity, or fail-closed behavior.

### Stage 10 handoff

Stage 10 owns protocol/session/transport/deployment behavior and chooses compatible approved renderings. It cannot silently alter canonical `GeneratedResponse` factual/citation semantics.

## Orchestrator Handoff

Before Stage 6 is marked fully reconciled/merged, the orchestrator should verify:

1. ADR-014/015/016 are consistent with `NORTHSTAR.md`, ADR-001 through ADR-013, and Stage 5.
2. ADR-013 remains valid without amendment; no hidden Stage 5 proposition-level requirement was introduced.
3. `docs/architecture/architecture.md` includes accepted Stage 6 global invariants.
4. `stages.md` reflects structured generation, validation, canonical response, and downstream boundaries.
5. Stage 7/8 ownership remains evaluative/observational rather than live response authority.
6. Stage 9/10 may tighten/block/deliver but cannot mutate grounding semantics.
7. No Stage 6 implementation code has been introduced by the architecture-only branch.
8. Commit history follows repository commit conventions.
9. The branch is reconciled with latest `main` before merge if `main` moved during the review.

After those checks, Stage 6 is **Implementation Ready** and Stage 7 detailed architecture work can begin.
