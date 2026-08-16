# ADR-005: V1 Local Hybrid Retrieval and Fusion Policy

## Status

Proposed

## Context

Stage 3 must retrieve high-quality local evidence across user-selected corpora while preserving ASTRAG's evidence-boundary, provenance, temporal, and publication invariants.

Stage 2 guarantees that query-visible chunks have both dense and lexical representations and may additionally have structured temporal metadata. The accepted V1 storage architecture uses PostgreSQL with integrated vector search and PostgreSQL full-text search.

The major V1 retrieval alternatives are:

1. dense-only retrieval,
2. lexical-only retrieval,
3. adaptive route selection through a query classifier,
4. always-on dense + lexical hybrid retrieval,
5. dense + lexical hybrid retrieval with an additional temporal route for strongly temporal queries.

The system also needs a fusion strategy. Raw dense, lexical, and temporal scores are not naturally calibrated onto one shared relevance scale.

ASTRAG's V1 workload is low concurrency and prioritizes correctness, temporal quality, determinism, and evaluability over premature optimization.

## Decision

ASTRAG V1 uses **always-on dense + lexical local retrieval**, with an additional structured temporal candidate route for strongly temporal retrieval profiles.

### Route execution

For normal V1 local retrieval requests:

- dense retrieval executes,
- lexical retrieval executes,
- temporal candidate retrieval executes when structured TemporalIntent and the selected retrieval profile require it.

Route failures may degrade independently when another route can still produce usable evidence.

### Same-chunk consolidation

If the same canonical `chunk_id` is returned by multiple routes, Stage 3 emits one candidate and preserves all route-specific ranks/signals.

Different canonical chunks are not collapsed merely because they contain identical text or share duplicate-lineage signals. Final semantic/source-level duplicate and corroboration handling belongs to Stage 5.

### Fusion

V1 uses **Reciprocal Rank Fusion (RRF)** as the baseline fusion method.

RRF is chosen because:

- dense and PostgreSQL lexical scores are not directly comparable,
- temporal route scores introduce another heterogeneous scoring domain,
- rank-based fusion is deterministic and explainable,
- it can be evaluated through route ablations,
- it avoids premature learned calibration.

Initial route contributions are equal. Exact RRF constants remain configurable and evaluation-tuned rather than architectural invariants.

The fused score is a ranking signal, not a calibrated probability of relevance.

### Temporal post-fusion adjustment

Strongly temporal retrieval profiles may apply a small bounded deterministic temporal adjustment after RRF.

This adjustment exists because exact/strong temporal relevance is central to ASTRAG and may otherwise be underweighted by rank fusion alone.

The adjustment must be bounded to prevent uncontrolled temporal double-counting. Exact weights are configuration and evaluation choices.

### Retrieval profiles and budgets

V1 uses a small deterministic profile set, including:

- `FACT_LOOKUP`,
- `TEMPORAL_POINT`,
- `TEMPORAL_RANGE`,
- `TIMELINE`,
- `BROAD`.

Profiles control internally managed candidate budgets, temporal-route activation, bounded temporal adjustment, diversity behavior, and output breadth.

Callers may select a supported profile but do not arbitrarily supply internal route weights or candidate limits.

### Document-level diversity

Stage 3 may apply a mild configurable rank penalty after too many high-ranked chunks from one document.

This is a retrieval-quality safeguard only. Stage 5 still owns final context diversity, source grouping, semantic duplicate handling, and corroboration semantics.

### Reranking

V1 does **not** include a cross-encoder, LLM, or other learned reranker initially.

Reranking should be reconsidered when evaluation shows that relevant evidence consistently appears inside the fused candidate pool but ranks too poorly to fit Stage 5's practical candidate budget.

## Consequences

### Positive

- Dense retrieval preserves semantic/paraphrase recall.
- Lexical retrieval preserves exact phrases, rare names, numbers, dates, and uncommon historical entities.
- Structured temporal retrieval improves recall for exact-date/timeline-style questions.
- RRF avoids pretending heterogeneous raw scores are directly comparable.
- Same-chunk consolidation prevents duplicate route hits from appearing as multiple evidence candidates.
- Always-on dense + lexical behavior is deterministic and easy to evaluate.
- A no-reranker baseline reduces latency, cost, complexity, and another failure mode.
- Route-specific failures can degrade gracefully rather than failing all retrieval.

### Negative

- Every normal local query pays both dense and lexical query cost.
- Temporal profiles may execute three retrieval routes.
- RRF ignores useful absolute-score information unless it is separately inspected downstream.
- Bounded temporal post-adjustment introduces additional tuning parameters.
- The baseline may eventually need reranking if fusion ordering is insufficient.
- A mild document-diversity penalty can change pure relevance ordering and must be evaluated carefully.

## Alternatives Considered

### Dense-only retrieval

Rejected as the V1 baseline because exact phrases, rare entities, dates, and unusual historical terms are important retrieval cases.

### Lexical-only retrieval

Rejected because semantic retrieval is a core product capability and paraphrase recall would suffer.

### Query-classifier route selection

Deferred. It may reduce retrieval cost later, but it introduces another classification failure mode before ASTRAG has a mature evaluation baseline.

### Dense primary with lexical fallback

Rejected for V1 because lexical signals are valuable even when dense retrieval succeeds.

### Raw-score weighted sum

Rejected initially because dense, lexical, and temporal score distributions are heterogeneous and not safely comparable without calibration.

### Learned fusion

Deferred until sufficient labeled retrieval data exists to justify the complexity.

### Cross-encoder or LLM reranking in the initial baseline

Deferred until evaluation proves ranking rather than recall is the limiting factor.

## Revisit Triggers

Revisit this ADR if:

- always-on dense + lexical execution becomes a material latency/cost problem,
- evaluation shows one route consistently harms retrieval quality,
- RRF materially underperforms a calibrated/learned fusion method,
- relevant evidence is usually retrieved but poorly ordered inside the fused pool,
- temporal post-fusion adjustment proves unnecessary or destabilizing,
- production concurrency materially exceeds V1 assumptions,
- or future search infrastructure changes make another fusion architecture preferable.

## Affected Stages

- Stage 3 — Retrieval Pipeline
- Stage 4 — Agent / Orchestration Layer
- Stage 5 — Context Assembly
- Stage 7 — Evaluation Framework
- Stage 8 — Observability & Debugging
- Stage 9 — Guardrails & Reliability
- Stage 10 — Production / Serving

## Related Documents

- `NORTHSTAR.md`
- `docs/architecture/architecture.md`
- `docs/stages/01-problem-definition.md`
- `docs/stages/02-ingestion.md`
- `docs/stages/03-retrieval.md`
- `docs/architecture/decisions/ADR-002-ingestion-identity-versioning-publication.md`
- `docs/architecture/decisions/ADR-003-temporal-evidence-representation.md`
- `docs/architecture/decisions/ADR-004-v1-persistence-search-storage.md`
