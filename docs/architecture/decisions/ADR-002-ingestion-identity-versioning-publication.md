# ADR-002: Ingestion Identity, Versioning, and Publication Model

## Status

Proposed — requires orchestrator approval.

## Context

Stage 2 must support document updates, reprocessing, embedding-model replacement, retries, partial failures, and deletion without losing evidence provenance or exposing partially built data to retrieval.

A single mutable document record is insufficient because source-content changes, parser/chunker changes, and search-representation changes have different meanings and different reprocessing costs.

Stage 1 and the global architecture require corpus isolation, provenance preservation, temporal traceability, and predictable evidence boundaries.

## Decision

ASTRAG separates four identities:

1. **LogicalDocument** — stable logical source identity.
2. **DocumentVersion** — immutable source-content version.
3. **ProcessingGeneration** — immutable parser/normalizer/chunker/temporal-processing configuration.
4. **SearchRepresentationGeneration** — immutable dense/lexical search-representation configuration.

The lifecycle rules are:

- Explicit **Create Document** creates a new logical document and initial version.
- Explicit **Update Document** creates a new immutable version under the existing logical document.
- The system does not infer create-versus-update from filename or content similarity.
- `source_hash` is SHA-256 over exact uploaded bytes and supports idempotency/duplicate detection; it is not logical document identity.
- Uploading bytes identical to the active version during an explicit update is idempotent and does not create a fake new version.
- Only one replacement version may process at a time for a logical document in V1.
- Parser, normalizer, or chunker changes create or select a new ProcessingGeneration rather than a fake DocumentVersion.
- Embedding/lexical representation changes create a new SearchRepresentationGeneration rather than new chunks.
- ProcessingGenerations may differ across active documents; a global preferred ProcessingGeneration controls new processing but does not force immediate corpus-wide migration.
- Active retrieval uses one globally active SearchRepresentationGeneration in V1.

### Publication model

A new version or representation is built privately, validated, then atomically published. Partially indexed versions are never query-visible.

A replacement version becomes active only after it reaches `READY` or an explicitly permitted `READY_DEGRADED` state. If replacement processing fails, the previous active version remains searchable.

Publication validation requires, as applicable:

- valid document/version/generation lineage,
- complete required chunk set,
- complete dense and lexical representations,
- correct active search generation,
- valid corpus association,
- valid provenance spans,
- valid temporal annotations when temporal extraction succeeded,
- index visibility matching the expected searchable chunk set.

### Canonical and derived state

Canonical evidence and lineage are authoritative. Search indexes are derived/rebuildable projections.

Artifacts are immutable and generation-addressed. Successful intermediate artifacts may be reused only when generation compatibility proves their upstream inputs remain valid.

## Consequences

### Positive

- Source history is distinct from processing history.
- Re-chunking does not invent source versions.
- Re-embedding does not mutate chunk identity.
- Retries and recovery can be idempotent.
- Failed replacements do not remove working evidence.
- Search-generation migrations can use safe cutover semantics.
- Historical provenance remains reproducible.

### Negative

- More lifecycle entities and generation metadata must be persisted.
- Reprocessing compatibility must be explicit.
- Publication requires validation and activation logic rather than simple inserts.

## Alternatives Considered

### Mutable document-in-place model

Rejected because source updates, parser changes, chunk changes, and embedding changes would overwrite lineage and make reproducibility weak.

### New logical document for every upload

Rejected because corrections and replacements would lose stable source identity.

### Partial search visibility during ingestion

Rejected because missing chunks or incomplete representations would silently remove evidence from retrieval.

### Per-document active search representation generation

Deferred for V1 because mixing incompatible embedding/search generations makes retrieval correctness and migration substantially harder.

## Revisit Triggers

Revisit if:

- V1 needs concurrent replacement versions for one document,
- multiple active embedding spaces are required,
- processing-generation heterogeneity causes retrieval-quality problems,
- or storage/retention pressure requires a different historical-artifact policy.

## Affected Stages

- Stage 2 — Data Ingestion Pipeline
- Stage 3 — Retrieval Pipeline
- Stage 5 — Context Assembly
- Stage 6 — Generation Layer
- Stage 7 — Evaluation Framework
- Stage 8 — Observability & Debugging
- Stage 10 — Production / Serving

## Related Documents

- `NORTHSTAR.md`
- `docs/architecture/architecture.md`
- `docs/stages/01-problem-definition.md`
- `docs/stages/02-ingestion.md`
