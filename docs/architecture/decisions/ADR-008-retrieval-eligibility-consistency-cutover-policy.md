# ADR-008: Retrieval Eligibility Consistency and Concurrent Cutover Policy

## Status

Accepted

## Context

ADR-002 makes active publication, deletion state, and the globally active SearchRepresentationGeneration authoritative for local evidence eligibility. Stage 3 performs multi-phase retrieval: search, candidate validation, fusion/ranking, final validation, and backfill.

Those phases can overlap concurrent lifecycle changes such as:

- document deletion or tombstoning,
- corpus movement,
- DocumentVersion publication cutover,
- ProcessingGeneration cutover,
- global SearchRepresentationGeneration cutover.

A single long-running database snapshot gives internally consistent reads, but may allow evidence that became ineligible after the snapshot began to be emitted after a deletion or cutover committed. Conversely, performing unrelated fresh reads throughout one request can mix generations/publication states and produce an incoherent candidate set.

Stage 3 therefore needs an explicit consistency contract rather than relying on incidental transaction behavior.

## Decision

Each local retrieval execution captures a **request-scoped retrieval state identity** and must not mix incompatible authoritative states within one successful result.

### Captured retrieval state

At retrieval start, Stage 3 captures enough authoritative state to identify the search space used for candidate generation, including at least:

- globally active `SearchRepresentationGeneration`,
- retrieval configuration identity,
- selected executable corpus scope,
- a database snapshot/transaction identity or equivalent eligibility epoch suitable for tracing and consistency checks.

Candidate generation uses the captured SearchRepresentationGeneration consistently. Dense, lexical, and temporal routes must not mix rows from different active search-representation generations inside one execution.

### Final authoritative validation

Immediately before candidates are emitted, Stage 3 re-validates each output candidate against current committed authoritative lifecycle state.

The final check verifies at least:

- corpus remains in the permitted selected scope,
- logical document is not deleting/deleted,
- document remains owned by the eligible corpus,
- `document_version_id` is still active,
- `processing_generation_id` is still the active processed chunk set,
- publication/readiness state still permits searchability,
- the candidate's SearchRepresentationGeneration is still valid for the request's search space.

Stale or newly ineligible candidates are rejected and traced. Lower-ranked already-generated candidates may backfill only if they pass the same final validation.

### SearchRepresentationGeneration cutover during retrieval

A global SearchRepresentationGeneration cutover changes the compatible dense/lexical search space. Stage 3 must not combine pre-cutover and post-cutover representations in one result.

If the globally active SearchRepresentationGeneration changes after candidate generation begins and before output validation completes, the request state is invalidated.

Stage 3 may perform at most a small bounded transparent restart using the new active generation when the request deadline permits. If a coherent restart cannot complete, Stage 3 fails closed with a stable reason such as `SEARCH_GENERATION_CHANGED` or `ELIGIBILITY_STATE_CHANGED` rather than returning mixed-generation evidence.

### Publication/deletion/corpus-move changes during retrieval

A document publication cutover, deletion, or corpus move does not require restarting the entire retrieval request if final validation can safely reject affected candidates and backfill from candidates that remain eligible under the captured search generation.

If lifecycle churn invalidates enough state that Stage 3 can no longer establish a coherent eligible output, the operation fails closed rather than returning stale evidence.

### No correctness dependence on physical index cleanup

As established by ADR-002, derived index cleanup may lag publication/deletion changes. This ADR does not require synchronous physical cleanup. Correctness depends on authoritative final validation and coherent search-generation handling.

### Failure and trace semantics

Stage 3 records state-change invalidations separately from ordinary database/search failures.

At minimum traces preserve:

- captured active SearchRepresentationGeneration,
- retrieval-state/snapshot or epoch identity where available,
- final-validation time/state,
- candidates rejected because authoritative state changed,
- whether a bounded restart occurred,
- final state-change reason code if the operation failed.

## Consequences

### Positive

- Deleted or superseded evidence cannot be emitted merely because a long-running query started earlier.
- One result never mixes incompatible SearchRepresentationGenerations.
- Derived-index cleanup remains asynchronous without weakening correctness.
- Concurrent publication/deletion races become testable and observable.
- Stage 3 has a deterministic fail-closed response when search-generation state changes materially during retrieval.

### Negative

- Final validation adds database work to retrieval.
- Search-generation cutovers may cause a bounded request restart or failure.
- Backfill pools must be large enough to tolerate some candidates becoming stale between search and output.
- Implementations need an explicit state/epoch concept or equivalent transaction metadata for observability.

## Alternatives Considered

### One repeatable-read snapshot for the entire request with no final current-state check

Rejected because evidence deleted or superseded after snapshot start could still be emitted after the lifecycle change committed.

### Fresh reads for every phase with no captured generation/state

Rejected because one request could combine candidates produced under incompatible publication or SearchRepresentationGeneration states.

### Global locks around every retrieval request

Rejected for V1 because it couples query latency to ingestion/deletion operations and is unnecessary when final authoritative validation and bounded restart provide the required correctness.

### Synchronous derived-index cleanup before lifecycle state changes commit

Rejected because ADR-002 deliberately makes canonical lifecycle state authoritative and allows physical/index cleanup to lag.

## Revisit Triggers

Revisit this ADR if:

- production concurrency becomes high enough that state-change restarts become common,
- search storage moves outside PostgreSQL and cross-store snapshot consistency becomes a material problem,
- multi-tenant authorization introduces stronger transaction/isolation requirements,
- or a future retrieval architecture supports multiple simultaneously active search representation spaces.

## Affected Stages

- Stage 2 — Data Ingestion Pipeline
- Stage 3 — Retrieval Pipeline
- Stage 7 — Evaluation Framework
- Stage 8 — Observability & Debugging
- Stage 9 — Guardrails & Reliability
- Stage 10 — Production / Serving

## Related Documents

- `docs/architecture/decisions/ADR-002-ingestion-identity-versioning-publication.md`
- `docs/architecture/decisions/ADR-004-v1-persistence-search-storage.md`
- `docs/architecture/decisions/ADR-005-v1-local-hybrid-retrieval-fusion-policy.md`
- `docs/stages/02-ingestion.md`
- `docs/stages/03-retrieval.md`
- `docs/architecture/architecture.md`
