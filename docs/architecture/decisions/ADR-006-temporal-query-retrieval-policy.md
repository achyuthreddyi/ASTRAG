# ADR-006: Temporal Query and Retrieval Policy

## Status

Accepted

## Context

Historical and temporal QA are ASTRAG's primary specialization. Stage 2 already persists structured temporal evidence with multiple mentions, source/content origin, semantic role, precision, certainty, ranges, BCE/CE semantics, and unresolved relative expressions.

Stage 3 must decide how query-time temporal intent interacts with that persisted metadata without destroying semantic recall or inventing false precision.

A naive design that converts every temporal query into a hard SQL date filter would incorrectly exclude:

- relevant chunks whose temporal extraction is degraded,
- relevant chunks that describe a period without explicitly naming the queried date,
- approximate or uncertain historical evidence,
- evidence with multiple temporal mentions,
- unresolved relative expressions that remain semantically useful.

Conversely, treating temporal metadata as merely decorative would fail ASTRAG's core historical retrieval goal.

## Decision

ASTRAG uses a **structured, uncertainty-preserving temporal query and retrieval policy** in which temporal intent may drive candidate generation and ranking, but is not a hard cross-route filter by default.

### Structured multi-intent temporal input

Stage 3 receives zero or more structured `TemporalIntent` values from upstream query/temporal understanding.

A request may contain multiple independent temporal intents rather than one global `date_from/date_to` pair.

Each intent conceptually preserves:

- temporal relation/type,
- original user expression,
- normalized start/end/anchor where safely resolvable,
- precision,
- certainty,
- era/calendar semantics,
- query semantic role,
- resolution status.

The original wording remains available so normalized search bounds never upgrade uncertain evidence into false exactness.

### Supported V1 temporal shapes

Stage 3 supports at least:

- exact point/date,
- year/period point,
- date/period range overlap,
- before,
- after,
- approximate/proximity (`AROUND`),
- recurring month/day semantics such as `on this day`,
- BCE/CE machine-comparable values while preserving source-era wording.

Relative expressions based on the user's current date, such as `100 years ago today`, are resolved upstream before retrieval.

### Temporal route predicates versus global candidate exclusion

The dedicated temporal candidate route may use strict temporal predicates to generate candidates matching the structured temporal intent. Those route-local predicates do **not** automatically become global evidence-eligibility rules for dense/lexical candidates.

Dense/lexical candidates remain eligible when temporal metadata is absent, has zero mentions, is degraded, or is semantically useful but does not itself contain a safely normalized matching mention.

Cross-route hard temporal exclusion is permitted only when an explicit typed query constraint has semantics that genuinely require exclusion, for example a request explicitly constrained to source/publication metadata time. Such constraints must be represented explicitly in the structured request, traced, and evaluated independently from ordinary temporal question interpretation.

This distinction prevents an exact-date or range question from accidentally converting optional temporal enrichment into mandatory evidence eligibility.

### Dedicated temporal candidate route

Strongly temporal retrieval profiles may execute an additional structured temporal candidate route alongside dense and lexical retrieval.

Stage 3 decides route activation from the structured TemporalIntent and retrieval profile.

The temporal route searches TemporalMentions attached to otherwise query-visible chunks and obeys the same selected-corpus/publication/generation/deletion eligibility requirements as other routes.

### Multiple temporal mentions

All applicable mentions on a chunk are considered.

If multiple mentions match, the strongest match may drive ranking while all matching mentions remain attached to the returned candidate for downstream explanation and reasoning.

Temporal evidence is never collapsed into one synthetic canonical date per chunk.

### Temporal origin and semantic role

Stage 3 preserves Stage 2's distinction between temporal origin and semantic role.

For ordinary event-oriented questions, event-time-like mentions may receive a configurable ranking preference over relevant unknown-role mentions and source/document metadata.

For queries explicitly about publication/source time, that preference may reverse.

These preferences affect ranking, not evidence eligibility.

### Approximate and uncertain periods

Approximate historical expressions use interval overlap/proximity and precision/certainty compatibility rather than binary exact matching.

Examples such as `circa 1200 BCE` or `early 5th century` must not be silently treated as exact dates.

Normalized search bounds are search aids only; the original expression, precision, and certainty remain authoritative interpretation metadata.

### Unresolved temporal evidence

Stage 2 TemporalMentions that cannot be safely normalized, such as an unresolved `three years later`, do not participate in structured date filtering/ranking as if they had invented normalized values.

Their source text remains available through dense/lexical retrieval.

If the query itself contains an unresolved temporal anchor, Stage 3 degrades to semantic/lexical retrieval when meaningful. If the unresolved anchor makes the query semantically unusable, retrieval may fail rather than inventing an anchor. Stage 4 may resolve the anchor through a separate evidence-seeking step and issue a new explicit retrieval request.

### Temporal capability degradation

`TEMPORAL_READY` with zero mentions and `TEMPORAL_DEGRADED` are distinct states.

If temporal extraction failed for an otherwise query-visible document, Stage 3 must not make optional temporal enrichment a mandatory eligibility requirement. The document remains retrievable through dense/lexical routes with degradation metadata.

A temporal-route failure may likewise degrade to dense/lexical results when they remain usable.

### Temporal ranking signals

Returned candidates expose explainable temporal match information rather than a fictitious calibrated probability.

Conceptual fields include:

- matched TemporalMentions,
- relation/overlap type,
- precision compatibility,
- certainty,
- origin,
- semantic role,
- temporal distance/proximity,
- temporal route rank when applicable.

### Temporal fusion behavior

When the temporal candidate route executes, it participates in RRF as a ranked route.

Strong temporal profiles may additionally apply a bounded deterministic post-RRF temporal adjustment. The adjustment must remain bounded to avoid uncontrolled double-counting.

## Consequences

### Positive

- Temporal retrieval becomes a real retrieval capability rather than metadata decoration.
- Missing/degraded temporal metadata does not automatically destroy semantic recall.
- Temporal-route precision can be strict without turning optional metadata into a global eligibility gate.
- Approximate and uncertain historical evidence remains faithful to source precision.
- Multiple dates per chunk remain independently matchable and explainable.
- Source/publication dates cannot silently masquerade as event dates.
- BCE/CE and range semantics remain machine-queryable without losing original wording.
- Temporal retrieval behavior can be directly evaluated and traced.

### Negative

- Temporal query and ranking logic is more complex than one date filter.
- Soft cross-route behavior may retain semantically relevant but temporally weak candidates, requiring good ranking/evaluation.
- Explicit metadata constraints require careful distinction from ordinary temporal intents.
- Configurable temporal-role preferences and bounded post-fusion adjustment require tuning.
- Some relative/ambiguous expressions remain unresolved and cannot receive structured temporal matching.

## Alternatives Considered

### Hard temporal filtering for every temporal query

Rejected because it can remove relevant evidence when temporal extraction is degraded/missing or when relevant prose does not explicitly contain the target date.

### Temporal route-local predicates plus dense/lexical recall

Accepted because it allows precise temporal candidate generation while preserving semantic/lexical evidence that lacks safe temporal metadata.

### Temporal metadata only as a post-retrieval boost

Rejected as the complete policy because exact-date/timeline queries benefit from a dedicated temporal candidate route that can recover evidence semantic/lexical search may rank too weakly.

### One canonical date per query and one canonical date per chunk

Rejected because ASTRAG must support multiple temporal constraints and multiple temporal mentions with distinct roles/origins.

### Convert approximation into exact dates

Rejected because it violates the accepted temporal uncertainty model in ADR-003.

### Discard unresolved temporal mentions

Rejected because unresolved source wording remains valid evidence for semantic/lexical retrieval and downstream reasoning.

## Revisit Triggers

Revisit this ADR if:

- temporal evaluation demonstrates that more hard cross-route filtering is safe and materially improves precision,
- richer event-relation extraction becomes available,
- historical calendar conversion enters scope,
- multilingual temporal support enters scope,
- temporal ranking requires learned calibration,
- or evaluation shows the dedicated temporal route/adjustment harms rather than improves retrieval quality.

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
- `docs/architecture/architecture.md`
- `docs/stages/01-problem-definition.md`
- `docs/stages/02-ingestion.md`
- `docs/stages/03-retrieval.md`
- `docs/architecture/decisions/ADR-003-temporal-evidence-representation.md`
- `docs/architecture/decisions/ADR-005-v1-local-hybrid-retrieval-fusion-policy.md`
