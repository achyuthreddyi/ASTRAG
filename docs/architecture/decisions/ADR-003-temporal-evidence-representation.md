# ADR-003: Temporal Evidence Representation

## Status

Accepted

## Context

ASTRAG is primarily optimized for historical and temporal QA. The global architecture requires temporal metadata and temporal uncertainty to remain first-class across ingestion, retrieval, context assembly, generation, and evaluation.

A single date field per chunk cannot represent multiple dates, ranges, approximate historical periods, BCE/CE, relative expressions, uncertainty, source/document dates, or different semantic roles.

## Decision

Stage 2 models temporal evidence as zero or more structured `TemporalMention` records associated with normalized source spans and then with chunks where applicable.

Each temporal mention preserves both the source expression and normalized structure where safe.

Conceptual fields include:

- original text,
- temporal origin/scope,
- semantic role,
- normalized start,
- normalized end,
- precision,
- certainty,
- era/calendar semantics,
- source block/span lineage where applicable.

### Temporal origin: source/document time versus content time

ASTRAG must explicitly distinguish **source/document metadata time** from **time mentioned in document content**. This distinction is persisted rather than inferred later from nullable fields.

At minimum, a temporal record identifies an origin conceptually equivalent to:

- `SOURCE_METADATA` — a date attributable to the document/source itself, such as creation, publication, issue, or other source metadata time;
- `CONTENT_MENTION` — a temporal expression occurring in the document's evidence text.

Source/document time is not automatically event time. A publication date, for example, must not be silently treated as the date of an event described by the document.

### Semantic role

Stage 2 may assign a conservative semantic role when reliably determinable. Roles may distinguish concepts such as event time, publication/source time, or other useful temporal semantics, but `UNKNOWN` is always valid and preferable to an invented classification.

The origin/scope discriminator and semantic role are separate: origin says **where the temporal value came from**; role says **what it appears to mean**.

Stage 3 may use these persisted distinctions for filtering or ranking, but Stage 3 owns query-time temporal interpretation and retrieval policy.

### Multiple mentions

A chunk may contain multiple TemporalMentions. Document-level dates and dates mentioned in content remain independently representable and queryable.

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

Normalized bounds used for search must remain interpretable together with the persisted precision/certainty/original-expression fields; a coarse search bound does not upgrade the source claim to exactness.

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
- Source/document dates cannot silently masquerade as event dates.
- Historical expressions are not forced into false precision.
- Stage 3 receives structured temporal fields without Stage 2 owning query-time retrieval policy.
- Temporal-quality evaluation has an explicit persisted target.

### Negative

- Temporal schema and validation are more complex than a single date field.
- Relative expressions may remain unresolved.
- Conservative semantic-role assignment means some useful relations remain `UNKNOWN` until later reasoning.
- Extraction quality becomes an important Stage 2 evaluation surface.

## Alternatives Considered

### One canonical date per chunk

Rejected because it loses multiple events, ranges, document-vs-event distinctions, and uncertainty.

### Raw temporal text only

Rejected because Stage 3 would lack structured fields for reliable temporal filtering and ordering.

### Infer document-time versus event-time only at retrieval

Rejected because origin is durable evidence metadata and should not be reconstructed heuristically for every query.

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
