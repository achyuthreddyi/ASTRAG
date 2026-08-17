# Stage 3 Implementation Plan — Retrieval Pipeline

## Status

**Approved for implementation.** This is the step-by-step execution guide for the accepted Stage 3 architecture (`docs/stages/03-retrieval.md`, ADR-005/006/007/008).

`03-retrieval.md` is the *architecture*. This document is the *implementation slice*: what gets built now, what is deliberately deferred, and in what order.

## Scope of this slice

Steps 1–10 of `03-retrieval.md` §Implementation Plan: a working query path from a structured `LocalRetrievalRequest` to a ranked, eligibility-validated, provenance-complete `LocalRetrievalResult` — dense + lexical retrieval with a bounded literal fallback, a structured temporal route, RRF fusion with bounded temporal adjustment, profiles and mild document diversity, output-time revalidation with backfill, structured failure and degradation semantics, and full execution metadata.

Steps 11–13 — evaluation datasets, route ablations, representative benchmarks, budget tuning, and the ANN/reranker revisit — are Stage 7's. They are deferred, not forgotten: per-phase latency, per-route candidate counts, fallback activation, and every applied ranking adjustment are emitted from the first rung, so Stage 7 inherits a data surface rather than an instrumentation project.

The correctness properties come first. Corpus isolation, eligibility, generation coherence, and deterministic ordering are tested inside the rungs that introduce them, per `03-retrieval.md` §Implementation Plan's closing instruction.

## Settled decisions

### Package layout

`src/astrag/retrieval/`, split the way `ingest/` is:

| Module | Owns |
| --- | --- |
| `contracts.py` | request/result/candidate models, status enum, reason codes |
| `config.py` | the five profiles, candidate budgets, weights, `retrieval_config_version` |
| `eligibility.py` | the authoritative predicate, executable corpus scope resolution |
| `dense.py` | query embedding, generation compatibility, exact vector search |
| `lexical.py` | primary FTS and the bounded literal fallback |
| `temporal.py` | structured temporal candidate route and match details |
| `fusion.py` | consolidation, RRF, temporal adjustment, diversity |
| `coordinator.py` | orchestration, final validation, degradation, execution metadata |

Two Alembic migrations, both on Stage 2 tables: the `simple`-configuration lexical column, and the temporal interval bounds.

### The eligibility predicate

One join expression, applied identically at search time and at output time. That sameness *is* the defense in depth of §2 — two independent implementations of "eligible" would be two chances to disagree.

```sql
FROM chunks c
JOIN documents d          ON d.id = c.document_id
                         AND d.active_version_id = c.document_version_id
JOIN document_versions v  ON v.id = c.document_version_id
JOIN chunk_representations r ON r.chunk_id = c.id
                         AND r.search_representation_generation_id = :captured_srg
WHERE c.corpus_id = ANY(:executable_scope)
  AND v.status IN ('READY','READY_DEGRADED')
  AND v.published_processing_generation_id = c.processing_generation_id
```

Three properties worth stating explicitly:

- **Every route joins `chunk_representations` under the captured SearchRepresentationGeneration — lexical and temporal included.** The tsvector lives on `chunks` and is not SRG-scoped, and temporal mentions are not either. Without this join, a lexical or temporal hit could return a chunk that has no representation in the request's search space, and ADR-008's "one result never mixes generations" would be a convention rather than a structural guarantee.
- **"Not deleted" is "the row exists."** Stage 2 chose hard cascade delete with no tombstone (`02-ingestion-implementation-plan.md` §Deletion), so deletion needs no predicate of its own. If the tombstone state machine ever lands, this is the single place the condition is added.
- **The `documents.active_version_id` join covers stale-version and unpublished-replacement together**, and Stage 2's composite foreign key binds `d.corpus_id` to `c.corpus_id`, so a corpus move cannot leave a stale denormalized copy behind the boundary filter.

### Request state capture and cutover

Per ADR-008, each execution captures a request-scoped retrieval state identity at start: the globally active SRG from `active_generation_pointer`, `retrieval_config_version`, the executable corpus scope, and `pg_current_snapshot()::text` plus a wall clock as the traceable eligibility epoch. Candidate generation uses the captured SRG everywhere.

Final validation is a **fresh statement**, which under READ COMMITTED sees a new snapshot by construction. It re-runs the same predicate against the shortlist's chunk ids and re-reads the SRG pointer. Rejected candidates are dropped with a recorded reason and backfilled from the over-fetched pool — which is why `fusion_candidate_limit` exceeds `retrieval_output_limit`.

**A changed SRG pointer fails closed** with `SEARCH_GENERATION_CHANGED`. ADR-008 permits this explicitly; the bounded transparent restart is *may*, not *must*. V1 has no SRG cutover mechanism at all — `02-ingestion-implementation-plan.md` defers the re-embedding migration — so a restart path could only ever fire inside a test that manufactures the cutover. It is added the day a real cutover mechanism exists.

### Dense retrieval: exact, index disabled

`SET LOCAL enable_indexscan = off` for the dense query, so the eligibility-filtered vector scan is exhaustive.

This resolves a real conflict between the documents and the schema. `03-retrieval.md` §7 and §Non-Goals make exact vector search the V1 baseline with ANN benchmark-triggered, but Stage 2 rung 9 already shipped an HNSW index, so the planner would use it and dense retrieval would silently be approximate.

Beyond the contradiction, filtered ANN is the wrong default here: pgvector applies the corpus and eligibility filter *after* the index scan, so a query scoped to one small corpus can return far fewer rows than `dense_candidate_limit` — or none — purely as an artifact of the index. Corpus-scoped queries are this system's single most common shape.

The HNSW index stays in place, unused by retrieval, ready for the day benchmarks trigger ANN. Dropping it would only trade a write-time cost for a future migration.

### Query embedding and generation compatibility

The settings-driven `get_embedder()` is kept. Before vector search, its model and dimensions are asserted equal to the captured SRG's `config` JSONB; a mismatch is `FAILURE / EMBEDDING_GENERATION_INCOMPATIBLE`, which is the correctness-failure semantics §Embedding generation incompatibility asks for, distinct from ordinary degradation.

Constructing the embedder *from* SRG config was rejected for V1: the fixed-width vector column means two SRGs cannot coexist, so correct-by-construction buys nothing over correct-by-assertion, and it would duplicate configuration that already lives in `settings`.

### Lexical retrieval and the bounded fallback

Primary: `websearch_to_tsquery('english', ...)` against the existing generated `chunks.lexical`, ordered by `ts_rank_cd`.

Fallback: a second generated column, `to_tsvector('simple', contextualized_text)`, with its own GIN index. Unstemmed and unstopworded, so acronyms, codes, numbers, and quoted phrases (via `<->` phrase operators) match literally and stay indexed.

Activation is deterministic — the primary tsquery normalizes to empty, or the query carries quoted phrases or identifier-like tokens (mixed digits and letters, internal punctuation, all-caps runs). Activation is recorded per request, and the whole fallback sits behind a config flag so §Mandatory ablations has a switch to throw.

Rejected alternatives:

- **`pg_trgm` with `ILIKE`** — genuinely better for punctuation-heavy identifiers that even `simple` tokenizes apart, but it needs a new extension and a large trigram index, and its ranking is fuzzier and harder to make deterministic.
- **`websearch_to_tsquery` alone, no second column** — zero migration, and it does handle quoted phrases and malformed input inside the existing index. Rejected because it cannot recover the empty-tsquery case, so §8's contract would be only partly met and the required ablation would have nothing to toggle.

The `simple` column inherits the existing column's best property: a generated column cannot drift from the text it derives from.

### Temporal interval bounds

Two generated integer columns on `temporal_mentions`, btree-indexed:

```text
key(y, m, d) = y*372 + (m-1)*31 + (d-1)

bound_low  = key(start_year, coalesce(start_month, 1),  coalesce(start_day, 1))
bound_high = key(coalesce(end_year, start_year),
                 coalesce(end_month, 12), coalesce(end_day, 31))

both NULL when start_year IS NULL
```

Deliberately arithmetic rather than `make_date`, for three reasons. It is monotonic, so overlap, ordering, before, and after are correct and btree-indexable. It handles signed BCE years directly without Postgres's no-year-zero convention. And — the reason that actually decides it — **it can never raise**. A generated column built on `make_date` would reject `February 30`, turning a temporal-extractor bug into a failed *ingestion* rather than a slightly wrong date.

The cost is that the key is not a true day count, so it is unusable for arithmetic distance. Human-meaningful temporal distance is therefore computed in Python from the components, on the few hundred candidate rows only — which is where explainability is needed anyway.

The precision-widening rule becomes DDL, so changing it needs a migration. This matches how `chunks.lexical` already works and is accepted for the same reason.

Route predicates:

| Intent | Predicate |
| --- | --- |
| point, range | `bound_low <= q_high AND bound_high >= q_low` |
| before | `bound_high < q_low` |
| after | `bound_low > q_high` |
| around | overlap against the query interval widened by a profile-configured tolerance, ranked by proximity |
| recurring month/day | `start_month = :m AND start_day = :d` |

Unresolved mentions (`start_year IS NULL`) never participate in structured matching, per ADR-006. Their wording stays reachable through dense and lexical retrieval, and their chunks remain fully eligible.

### Fusion, adjustment, and diversity

Route hits consolidate by canonical `chunk_id`, retaining every route's rank and raw score. Then `Σ_route w_route / (k + rank)` with `k = 60` and equal initial weights, tie-broken by `(-score, chunk_id)` so the ordering is total and stable — which is what makes the determinism tests meaningful.

The temporal adjustment is **additive and capped at a configured fraction of the top RRF score**, so double-counting has a hard ceiling rather than a hopeful one. Its components — relation strength, precision compatibility, certainty, origin and semantic role preference, proximity — are individually recorded per candidate, so a surprising rank is explainable without re-running the query.

`CONTENT_MENTION` is preferred over `SOURCE_METADATA` for event-oriented queries. A `SOURCE_TIME` constraint reverses that preference and additionally applies as a hard cross-route filter — the one exclusion ADR-006 §Temporal route predicates versus global candidate exclusion permits, traced separately from ordinary temporal intent.

Diversity: after N highly ranked chunks from one document (3 by default, 6 for `TIMELINE`), a small penalty per additional chunk, then a stable re-sort. Behind an on/off flag, per §Mandatory ablations.

### Typed metadata constraints

`SOURCE_TIME` is the only constraint type implemented. It is the only one ADR-006 names and defines semantics for, and implementing it proves the hard-exclusion path exists and is distinguishable from soft temporal ranking. Every other value in `metadata_constraints[]` is `INVALID_RETRIEVAL_REQUEST`, per §Interfaces' rejection of arbitrary SQL-like filters.

### Route execution and failure semantics

Routes run **sequentially**. V1 is one user at low concurrency, and sequential execution keeps per-phase timings clean for the Stage 7 benchmarks that will consume them.

Each route is wrapped: an exception records its reason code in `degradation_details` and execution continues, yielding `SUCCESS_DEGRADED`. Dense and lexical both failing is `FAILURE`, except when the request is explicitly temporal and the temporal route produced candidates — §Dense and lexical both fail.

The request carries an optional `deadline_ms`, checked between phases and pushed down as a per-route `SET LOCAL statement_timeout`, so `REQUEST_DEADLINE_EXCEEDED` has a real trigger instead of being a decorative enum value.

### Retrieval configuration identity

`retrieval_config_version` is a content hash of the frozen configuration object, not a hand-maintained string. A hand-bumped constant can silently go stale after a tuning change, which is the one thing this identity exists to prevent. No first-class `RetrievalGeneration` lifecycle entity, per §20.

### API surface

`astrag.retrieval` is a plain callable that Stage 4 will import in-process. A thin `POST /retrieve` endpoint wraps it, taking a `LocalRetrievalRequest` as JSON and returning the full `LocalRetrievalResult` including `execution_metadata`. No auth, matching the rest of the API.

The endpoint is roughly thirty lines of pass-through and makes the slice exercisable by hand and by end-to-end tests while Stage 4 does not exist.

### Temporal intent derivation (development only)

`temporal_intents[]` is produced by Query + Temporal Understanding, which ADR-007 places upstream in Stage 4. That component does not exist, so without a stand-in the temporal route is reachable only through hand-built requests.

A dev-only helper reuses the existing deterministic extractor in `ingest/temporal.py` against the query string, living in `retrieval/devtools.py` behind an endpoint flag that **defaults off**. It is not part of the retrieval contract and no code inside `retrieval/` calls it.

The risk is named rather than hidden: a convenience stand-in for a missing component tends to become the real thing. It is deleted when Stage 4's query understanding lands.

### Tests

The existing docker-compose PostgreSQL with per-test transaction rollback, as Stage 2 established. Boundary and eligibility negative cases ride inside the rung that introduces the predicate rather than a later test rung — that predicate must not go green without them.

`FakeEmbedder` means the dense route's tests prove plumbing, filtering, and ordering, never relevance. That is expected and is exactly why relevance evaluation is Stage 7's, against real vectors.

## Implementation ladder

Each rung is one commit, committed as it goes green. A rung exceeding ~250 changed lines is split.

| # | Issue | Commit | Notes |
| --- | --- | --- | --- |
| 1 | #22 | `feat(retrieve): request and result contracts with profile derivation` | pure Python; deterministic profile derivation and invalid-profile rejection |
| 2 | #23 | `feat(retrieve): retrieval config, profiles and candidate budgets` | five profiles, budgets, weights, `retrieval_config_version` as content hash |
| 3 | #24 | `feat(retrieve): eligibility predicate and executable corpus scope` | boundary negative tests land in this rung |
| 4 | #25 | `feat(retrieve): exact dense route with search generation validation` | index disabled, SRG compatibility assertion |
| 5 | #26 | `feat(db,retrieve): simple-config lexical column and primary FTS route` | migration + `websearch_to_tsquery` route |
| 6 | #27 | `feat(retrieve): bounded literal fallback for FTS-poor queries` | deterministic activation trigger, ablation flag |
| 7 | #28 | `feat(retrieve): same-chunk consolidation and reciprocal rank fusion` | deterministic tie-breaking |
| 8 | #29 | `feat(db,temporal): generated interval bounds on temporal mentions` | migration; BCE, century, decade and range cases tested here |
| 9 | #30 | `feat(retrieve): temporal candidate route` | point/range/before/after/around/recurring |
| 10 | #31 | `feat(retrieve): bounded temporal adjustment and role preference` | capped, per-component traced |
| 11 | #32 | `feat(retrieve): source-time constraint as cross-route filter` | the one permitted hard exclusion |
| 12 | #33 | `feat(retrieve): document-level diversity penalty` | weak, configurable, on/off |
| 13 | #34 | `feat(retrieve): final current-state validation and backfill` | |
| 14 | #35 | `feat(retrieve): cutover fail-closed and deadline handling` | |
| 15 | #36 | `feat(retrieve): route degradation and structured failure semantics` | |
| 16 | #37 | `feat(retrieve): execution metadata and per-phase timings` | the Stage 7 and Stage 8 data surface |
| 17 | #38 | `feat(api): retrieve endpoint` | |
| 18 | #39 | `feat(retrieve): dev-only temporal intent derivation helper` | flag defaults off |
| 19 | #40 | `test(retrieve): eligibility, cutover and determinism race tests` | concurrent delete, publish and pointer flip |

Rung 19 is specifically the *concurrent* cases. The static boundary cases — unselected corpus, deleted document, old DocumentVersion, old ProcessingGeneration, inactive SRG, unpublished replacement, corpus move — belong to rung 3.

Rungs 5 and 8 both migrate Stage 2 tables with `ADD COLUMN ... GENERATED`, which rewrites the table: instant on an empty development database, minutes on a loaded one.

## Deferred out of this slice

| Deferred | Add when |
| --- | --- |
| Retrieval evaluation datasets and Recall@K / MRR / nDCG | Stage 7 |
| The four mandatory route ablations as a harness | Stage 7, using the flags this slice provides |
| Representative-scale latency benchmarks | Stage 7 |
| Candidate budget, RRF constant and weight tuning | after evaluation exists to tune against |
| ADR-008 bounded transparent restart | a real SRG cutover mechanism exists |
| ANN / HNSW-backed dense search | exact search misses a benchmarked latency target |
| Cross-encoder or learned reranker | evidence reliably lands in the fused pool but ranks too low for Stage 5's budget |
| Query embedding cache | query repetition is measured |
| Parallel route execution | route latency, measured, dominates total retrieval latency |
| Metadata constraint types beyond `SOURCE_TIME` | a caller needs one and its semantics are specified |
| Neighboring-chunk expansion | Stage 5, unless retrieval evaluation shows a Stage 3 need |
| Dev-only temporal intent derivation | deleted when Stage 4 query understanding lands |

## Architecture compliance

Nothing in this slice weakens a Stage 1, Stage 2, or Stage 3 invariant:

- the corpus boundary and every lifecycle constraint are one predicate, applied at search time and re-applied against fresh committed state before output,
- every route joins the captured SearchRepresentationGeneration, so one result cannot mix generations,
- SRG cutover fails closed rather than emitting mixed-generation evidence,
- temporal predicates stay route-local; the only cross-route exclusion is the explicitly typed `SOURCE_TIME` constraint ADR-006 permits,
- degraded or absent temporal metadata never removes valid dense or lexical evidence,
- unresolved temporal expressions are never assigned invented normalized values,
- `source_text` is returned as canonical evidence, never `contextualized_text`, even though lexical matching runs against the latter,
- distinct canonical chunks are never collapsed by content hash; duplicate lineage is reported and left to Stage 5,
- ranking is deterministic under a total order with stable tie-breaking,
- retrieval reports candidate and execution state and never decides answerability.

Two deviations from the literal text of `03-retrieval.md` are recorded above with their reasoning and re-add triggers: the absent bounded restart (§3, ADR-008 permits fail-closed), and the retained-but-disabled HNSW index (§7 asks for exact search, which is what executes).
