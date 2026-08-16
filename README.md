<p align="center">
  <img src="docs/assets/banner.svg" alt="ASTRAG — Agentic Semantic Temporal RAG" width="100%">
</p>

# ASTRAG

**Agentic Semantic Temporal Retrieval-Augmented Generation**

An evidence-grounded agentic RAG system for general-purpose document QA, specifically optimized and evaluated for **historical and temporal** questions.

Most RAG systems retrieve on meaning alone. ASTRAG retrieves on **meaning and time**, and treats the user's chosen evidence sources as a hard boundary the agent cannot cross.

---

## The problem it solves

Ask a RAG system *"what happened between 1943 and 1945?"* or *"what came before this event?"* and semantic similarity alone gives you plausible, badly-ordered, often wrong answers. Dates, ranges, ordering, and temporal uncertainty are second-class citizens in a vector index.

ASTRAG makes them first-class: temporal metadata is extracted at ingestion, reasoned over at retrieval, and preserved through context assembly into the final answer.

## What a user does

1. Upload documents, organize them into **corpora**.
2. Per query, select which corpora to search and whether the **web** is allowed.
3. Ask a question in natural language.
4. Get an answer grounded in retrieved evidence, with citations — or an explicit *"insufficient evidence"*.

Questions it targets:

- What happened on this date?
- What major events happened between two dates?
- What happened before / after event X?
- What do my selected documents say about this?
- What exists in both my documents and on the web?

## The evidence contract

Query-level source configuration is authoritative. The agent decides *how* to retrieve; it never decides *what it's allowed to read*.

| Corpora selected | Web | Behaviour |
|---|---|---|
| yes | OFF | selected corpora only |
| yes | ON | selected corpora **and** web (web retrieval is mandatory) |
| no | ON | web only |
| no | OFF | query rejected — no evidence source |

Invariants that hold across every stage:

- Unselected corpora never contribute factual evidence.
- Provenance survives ingestion → retrieval → context assembly → generation.
- Conflicting evidence is exposed, not silently reconciled.
- Duplicate evidence never masquerades as independent corroboration.
- Model pretraining knowledge may aid reasoning; it may not substitute for missing evidence.
- Insufficient evidence is a valid outcome, not a failure.

## Architecture

```text
Upload / Update
   ↓
Ingestion → canonical evidence (immutable versions + generations)
   ↓
Validated search publication
   ↓
PostgreSQL search projections (dense + lexical + temporal)
   ↓
Query + selected corpora + web flag + short-term conversation context
   ↓
Query & temporal understanding
   ↓
Agent orchestration  ── enforces the configured source boundary
   ├── local corpus retrieval (dense ∥ lexical ∥ temporal routes → RRF)
   └── web retrieval (when web is ON)
   ↓
Evidence pipeline → context assembly → grounded generation
   ↓
Answer + citations + conflict / uncertainty disclosure
```

Canonical evidence is authoritative; every search index is a **rebuildable projection** of it. Retrieval verifies eligibility at query time so deleted documents and stale generations can never leak into an answer.

## Tech stack

**Decided (V1, via accepted ADRs):**

| Concern | Choice |
|---|---|
| Canonical store | PostgreSQL — corpora, document lifecycle, immutable versions, generations, chunks, temporal mentions |
| Dense retrieval | pgvector, exact search (no ANN until benchmarks demand it) |
| Lexical retrieval | PostgreSQL full-text search + a bounded literal/phrase fallback |
| Temporal retrieval | dedicated temporal candidate route participating in fusion |
| Fusion | Reciprocal Rank Fusion — dense/lexical/temporal scores aren't comparable, so rank-fuse rather than pretend |
| Reranking | none in the V1 baseline; added only when evaluation shows fusion ordering falls short |
| Large artifacts | `ArtifactStore` abstraction (local FS / object storage) for source files and normalized documents |
| Web search | Tavily is the intended provider; swappable without an ADR revisit |
| Ingest formats | text-extractable PDF / TXT / Markdown / DOCX (no OCR, no multimodal in V1) |

**Deliberately deferred** until there's evidence to decide on: embedding model/provider, generation model/provider, agent framework, parser libraries, temporal-extraction libraries, chunk sizing, RRF constant and candidate budgets, ANN index type, context token budgeting, prompt architecture, API schema, caching, production topology.

**V1 envelope:** single tenant, low concurrency, hundreds–thousands of documents, ~1M chunks, one embedding model, one globally active search generation.

## Status

Design phase — architecture is being accepted stage by stage before any code is written. Stages 1–3 (problem definition, ingestion, retrieval) are accepted; no source code yet.

## Repository

| Path | Contents |
|---|---|
| `NORTHSTAR.md` | the goal and the non-negotiable evidence invariants |
| `stages.md` | the 10-stage implementation roadmap |
| `docs/architecture/architecture.md` | current accepted end-to-end architecture |
| `docs/architecture/decisions/` | ADRs — the decisions and why they were made |
| `docs/stages/` | per-stage design documents |

Read order for a change: `NORTHSTAR.md` → relevant ADRs → `architecture.md` → the owning stage document.
