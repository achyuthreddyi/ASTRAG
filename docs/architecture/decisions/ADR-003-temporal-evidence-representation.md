# ADR-003: Temporal Evidence Representation

## Status

Proposed — requires orchestrator approval.

## Context

ASTRAG is primarily optimized for historical and temporal QA. The global architecture requires temporal metadata and temporal uncertainty to remain first-class across ingestion, retrieval, context assembly, generation, and evaluation.

A single date field per chunk cannot represent multiple dates, ranges, approximate historical periods, BCE/CE, relative expressions, uncertainty, or different semantic roles.

## Decision

Stage 2 models temporal evidence as zero or more structured `TemporalMention` records associated with normalized source spans and then with chunks.

Each temporal mention preserves both the source expression and normalized structure where safe.

Conceptual fields include:

- original text,
- semantic role,
- normalized start,
- normalized end,
- precision,
- certainty,
- era/calendar semantics,
- source block/span lineage.

### Multiple mentions

A chunk may contain multiple TemporalMentions. Document-level dates and dates mentioned in content remain distinguishable.

### Semantic role

Stage 2 may assign a conservative semantic role when reliably determinable; `UNKNOWN` is valid and preferable to an invented classification.

### Precision

V1 precision categories are:

- `DAY`
- `MONTH`
- `YEAR`
- `SEASON`
- `DECADE`
- `CENTURY`
- `RANGE`
- `UNKNOWN`

### Certainty

V1 certainty categories are:

- `EXACT`
- `APPROXIMATE`
- `UNCERTAIN`

ASTRAG does not invent uncalibrated numeric confidence scores for temporal certainty.

### Ranges and approximation

Ranges are represented as one temporal mention with normalized start/end bounds when safe.

Approximate expressions retain their original wording and uncertainty. Expressions such as `circa 1200 BCE` or `early 5th century` must not be silently converted into falsely precise exact dates.

### BCE/CE and calendars

BCE/CE is represented in machine-comparable form while preserving the source era/original expression.

V1 does not implement sophisticated historical calendar conversion. Gregorian-style normalized reasoning is used where appropriate while source wording remains authoritative.

### Relative expressions

Relative expressions such as `three years later` or `the following spring` are preserved. They are normalized only when resolution is deterministic from local source context; unresolved expressions remain valid temporal evidence with no fabricated normalized value.

### Extraction boundary

Temporal extraction operates against normalized document structure before chunk association. This avoids duplicate extraction caused by chunk overlap and preserves source lineage.

A hybrid extraction architecture is used conceptually:

- deterministic extraction for explicit dates/ranges/eras and other reliably recognized forms,
- controlled semantic interpretation for harder roles and expressions,
- preservation of uncertainty whenever normalization is not reliable.

Exact libraries/models remain Stage 2 implementation choices.

### Degradation

`0 temporal mentions found` is a valid successful outcome and is distinct from temporal-extraction subsystem failure.

A temporal-extraction subsystem failure may produce `READY_DEGRADED` when semantic and lexical retrieval requirements are otherwise complete. Stage 2 exposes capability degradation; Stage 3 owns query-time behavior for degraded temporal capability.

## Consequences

### Positive

- Temporal uncertainty survives ingestion.
- Multiple dates and ranges remain queryable.
- Historical expressions are not forced into false precision.
- Stage 3 receives structured temporal fields without Stage 2 owning query-time retrieval policy.
- Temporal-quality evaluation has an explicit persisted target.

### Negative

- Temporal schema and validation are more complex than a single date field.
- Relative expressions may remain unresolved.
- Extraction quality becomes an important Stage 2 evaluation surface.

## Alternatives Considered

### One canonical date per chunk

Rejected because it loses multiple events, ranges, document-vs-event distinctions, and uncertainty.

### Raw temporal text only

Rejected because Stage 3 would lack structured fields for reliable temporal filtering and ordering.

### Fully LLM-derived temporal normalization

Rejected as the sole V1 mechanism because it would reduce determinism and make false precision harder to control.

### Rules-only temporal extraction

Rejected as the complete solution because important historical/relative expressions exceed simple deterministic parsing.

## Revisit Triggers

Revisit if:

- evaluation requires richer historical calendar handling,
- calibrated temporal confidence scores become available,
- event-relation extraction becomes a primary retrieval signal,
- or multilingual temporal support enters scope.

## Affected Stages

- Stage 2 — Data Ingestion Pipeline
- Stage 3 — Retrieval Pipeline
- Stage 5 — Context Assembly
- Stage 6 — Generation Layer
- Stage 7 — Evaluation Framework
- Stage 8 — Observability & Debugging

## Related Documents

- `NORTHSTAR.md`
- `docs/architecture/architecture.md`
- `docs/stages/01-problem-definition.md`
- `docs/stages/02-ingestion.md`
