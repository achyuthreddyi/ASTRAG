# ASTRAG — System Architecture

## Purpose

This document describes the current accepted end-to-end architecture of ASTRAG at a project-wide level.

It contains only architecture that has been accepted across stages. Stage-specific implementation details belong in `docs/stages/`, and significant architecture choices belong in `docs/architecture/decisions/`.

At the current project state, Stage 1 defines the global behavioral constraints. Concrete ingestion, retrieval, orchestration, context-assembly, generation, storage, and serving technologies remain intentionally undecided.

---

## System Goal

ASTRAG is an evidence-grounded agentic RAG system that supports general-purpose retrieval-augmented QA while being specifically optimized and evaluated for historical and temporal question answering.

The system combines:

- user-selected document corpora,
- semantic retrieval,
- temporal/date-aware retrieval,
- optional web access controlled per query,
- agentic orchestration,
- short-term conversational context,
- evidence-grounded generation,
- citations and traceability.

---

## High-Level Architecture

```text
Client / Query Interface
        │
        │ question
        │ selected_corpora[]
        │ web_enabled
        │ conversation context
        ▼
Query + Temporal Understanding
        │
        ▼
Agent / Orchestration
        │
        │ enforce query evidence boundary
        │
        ├───────────────┐
        ▼               ▼
Local Corpus         Web Retrieval
Retrieval            (when Web ON)
        │               │
        └───────┬───────┘
                ▼
         Evidence Pipeline
                │
                │ provenance
                │ temporal metadata
                │ retrieval signals
                ▼
         Context Assembly
                │
                ▼
       Grounded Generation
                │
                ▼
Answer + Citations + Conflict / Uncertainty Disclosure
```

The diagram expresses responsibilities, not implementation technology.

---

## Query Evidence Boundary

Every query defines its allowed evidence sources through:

```text
question
selected_corpora[]
web_enabled
conversation_context
```

The accepted V1 execution matrix is defined by ADR-001:

| Selected corpora | Web | Evidence sources |
| --- | --- | --- |
| One or more | OFF | Selected corpora only |
| One or more | ON | Selected corpora + web |
| None | ON | Web only |
| None | OFF | Invalid query |

The evidence boundary is authoritative.

- Unselected corpora cannot contribute factual evidence.
- Web OFF prohibits web evidence.
- Web ON requires web retrieval in V1.
- Conversation history cannot expand the current query's evidence permissions.
- Model memory cannot replace missing retrieved factual evidence.

The agent retains discretion over execution strategy within this boundary.

---

## Global Architectural Invariants

### 1. Evidence Grounding

Material factual claims must be grounded in retrieved evidence from sources allowed for the current query.

Insufficient evidence is a valid answer state.

### 2. Corpus Isolation

Corpora are first-class query boundaries.

A query may search one or more selected corpora using union semantics, but evidence from unselected corpora must remain inaccessible to that query's factual answer.

### 3. Provenance Preservation

Evidence provenance must survive the complete pipeline.

Local evidence should remain attributable to its corpus and document, with page/section/chunk metadata when available. Web evidence should retain external source identity.

Later stages must not discard provenance merely because doing so makes an intermediate interface tidier.

### 4. Temporal Information Is First-Class

ASTRAG must preserve and reason over temporal information including:

- exact dates,
- date ranges,
- before/after relationships,
- ordering,
- approximate dates,
- BCE/CE,
- temporal uncertainty.

Temporal metadata must remain available across ingestion, retrieval, context assembly, generation, and evaluation where applicable.

### 5. Conflict Preservation

Conflicting evidence must not be silently collapsed into a single claim.

The system must preserve enough provenance for generation to expose conflicting claims and cite each side.

### 6. Duplicate Evidence Must Not Inflate Corroboration

Duplicate or substantially copied evidence from multiple retrieval paths must not be represented as independent confirmation.

The concrete deduplication mechanism belongs to later stage design.

### 7. Short-Term Conversation Is Interpretive Context

Short-term conversation may resolve references such as "that event" or "what happened next".

It is not an additional factual evidence source and cannot bypass the current query's corpus/web configuration.

### 8. Graceful Evidence-Source Failure

Configured retrieval sources should fail independently where practical.

If one source fails while another returns usable evidence, ASTRAG may produce a grounded partial answer using the successful source and explicitly disclose the retrieval failure.

Successful retrieval with no relevant evidence must remain distinguishable from retrieval-system failure.

### 9. Traceability and Evaluation

The architecture must make it possible to observe at least:

- the user query,
- selected corpora,
- web setting,
- interpreted temporal constraints,
- retrieval paths executed,
- retrieved evidence and provenance,
- retrieval failures,
- context presented to generation,
- final citations,
- latency,
- token usage,
- and cost where applicable.

Evaluation and observability are cross-cutting requirements rather than end-of-project additions.

---

## Major Logical Components

The accepted architecture currently recognizes these logical responsibilities:

1. **Client / Query Interface**
   - receives the question,
   - selected corpora,
   - web configuration,
   - relevant conversational context.

2. **Query + Temporal Understanding**
   - interprets semantic intent,
   - resolves temporal language,
   - preserves temporal uncertainty.

3. **Agent / Orchestration**
   - enforces configured source boundaries,
   - coordinates retrieval/tool execution,
   - manages retries and stopping behavior,
   - does not override the source configuration.

4. **Local Corpus Retrieval**
   - searches only selected corpora,
   - preserves document/corpus provenance,
   - supports semantic and temporal retrieval requirements.

5. **Web Retrieval**
   - executes whenever Web is ON in V1,
   - preserves external-source provenance,
   - fails independently from local retrieval where practical.

6. **Evidence Pipeline / Context Assembly**
   - combines permitted evidence,
   - preserves conflicts,
   - avoids false duplicate corroboration,
   - orders and budgets context for generation.

7. **Grounded Generation**
   - answers from retrieved evidence,
   - exposes conflicts and uncertainty,
   - returns citations,
   - acknowledges insufficient evidence.

8. **Evaluation + Observability**
   - measures component and end-to-end quality,
   - traces source configuration and agent execution,
   - tracks latency and cost.

These are logical boundaries only. Service boundaries, process boundaries, frameworks, databases, and providers remain undecided.

---

## Current Data Flow

### Local-Only Query

```text
Query + Selected Corpora + Web OFF
        ↓
Query / Temporal Understanding
        ↓
Selected-Corpus Retrieval
        ↓
Evidence Assessment + Context Assembly
        ↓
Grounded Generation
        ↓
Answer + Local Citations
```

### Hybrid Query

```text
Query + Selected Corpora + Web ON
        ↓
Query / Temporal Understanding
        ↓
Local Retrieval + Web Retrieval
        ↓
Evidence Combination / Conflict Handling
        ↓
Context Assembly
        ↓
Grounded Generation
        ↓
Answer + Local/Web Citations
```

### Web-Only Query

```text
Query + Web ON + No Corpus
        ↓
Query / Temporal Understanding
        ↓
Web Retrieval
        ↓
Evidence Assessment + Context Assembly
        ↓
Grounded Generation
        ↓
Answer + Web Citations
```

---

## Scale and V1 Assumptions

Current accepted assumptions from Stage 1:

- single tenant,
- one primary user / low concurrency,
- hundreds to thousands of documents,
- design envelope up to approximately 1 million chunks,
- one embedding model initially,
- text-extractable PDF, TXT, Markdown, and DOCX inputs,
- OCR and multimodal ingestion excluded from V1.

These assumptions constrain later designs but do not yet prescribe technologies.

---

## Decisions Intentionally Deferred

The following must be resolved by their owning stages rather than being invented here prematurely:

- document parsing libraries,
- chunking strategy,
- metadata schema,
- vector/document stores,
- embedding model/provider,
- sparse vs dense vs hybrid retrieval implementation,
- reranking,
- temporal query representation,
- agent framework,
- concrete web-search provider integration,
- context token budgeting,
- prompt architecture,
- model/provider selection,
- exact API schema,
- caching,
- production topology,
- source-quality ranking.

When one of these choices materially changes global architecture, the owning stage must escalate it to the orchestrator and create an ADR when appropriate.

---

## Accepted ADRs

- `ADR-001-query-source-execution-policy.md` — V1 query source configuration is authoritative; Web ON mandates web retrieval.

---

## Stage Alignment

- **Stage 1** defines the behavioral contract and global evidence invariants.
- **Stage 2** owns ingestion, corpora, document lifecycle, provenance capture, and temporal metadata extraction.
- **Stage 3** owns query-time local retrieval and corpus-boundary enforcement.
- **Stage 4** owns orchestration within the source policy established by ADR-001.
- **Stage 5** owns evidence combination, deduplication, ordering, and context budgeting.
- **Stage 6** owns grounded response generation and citation behavior.
- **Stage 7** formalizes evaluation of the quality targets.
- **Stage 8** formalizes tracing and operational observability.
- **Stage 9** adds reliability and guardrails without weakening evidence boundaries.
- **Stage 10** defines production serving and scaling.
