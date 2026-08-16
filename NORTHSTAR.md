# ASTRAG — North Star

## Agentic Semantic Temporal Retrieval-Augmented Generation

### End Goal

Build an **evidence-grounded agentic RAG system** that supports general-purpose retrieval-augmented question answering while being specifically optimized for **historical and temporal question answering**.

ASTRAG should combine:

- User-selected document corpora
- Semantic retrieval
- Temporal/date-aware retrieval
- Internet search
- Agentic decision-making
- Short-term conversational context

Historical and temporal QA remain the primary product specialization, optimization target, and evaluation focus.

---

## Core User Experience

ASTRAG should support questions such as:

- What happened on this date?
- When did this historical event happen?
- What major events happened between two dates?
- What happened before or after a specific event?
- What do my selected documents say about this event?
- What do multiple selected corpora say about this topic?
- What evidence exists in both my documents and on the web?
- What reliable current information can be found on the internet?

Users may organize uploaded documents into corpora and select one or more corpora for each query.

General-purpose and current-information questions may be supported, but historical and temporal QA remain the primary benchmark for system quality.

---

## Core System Behaviour

Every query defines its allowed evidence sources through:

- zero or more selected corpora,
- a web-search toggle.

The V1 source policy is:

- **Web OFF + corpora selected** → retrieve only from the selected corpora.
- **Web ON + corpora selected** → retrieve from both the selected corpora and the web.
- **Web ON + no corpora selected** → retrieve from the web only.
- **Web OFF + no corpora selected** → reject the query because no evidence source is available.

The high-level flow is:

```text
User Question
+ Selected Corpora
+ Web Configuration
+ Relevant Short-Term Conversation Context
        ↓
Understand Intent + Temporal Context
        ↓
Determine Allowed Evidence Sources
        ↓
Retrieve From Configured Sources
        ↓
Rank + Combine Relevant Evidence
        ↓
Identify Missing / Conflicting Evidence
        ↓
Combine Temporal + Semantic Context
        ↓
Generate a Grounded Answer
        ↓
Return Sources / Citations
```

The user's source configuration is an evidence boundary. The agent may decide how to query, retrieve, rank, retry, and combine evidence within that boundary, but it must not silently override it.

When web search is enabled in V1, web retrieval is mandatory. When web search is disabled, web evidence must not be used.

The system should decide:

- which retrieval strategy to use within the configured sources,
- how to interpret temporal intent,
- how to combine overlapping evidence,
- how to expose conflicting evidence,
- and when there is not enough evidence to answer confidently.

Pretrained model knowledge may assist with query interpretation and reasoning, but it must not substitute for missing factual evidence.

---

## Key Principle

> **ASTRAG should produce evidence-grounded answers by reasoning over both meaning and time, while strictly respecting the evidence sources configured for each query.**

---

## Primary Capabilities

1. **Semantic Retrieval**  
   Find relevant information even when the wording differs from the query.

2. **Temporal Retrieval**  
   Understand dates, ranges, ordering, "before", "after", "on this day", approximate periods, and related temporal relationships.

3. **Corpus-Aware Retrieval**  
   Retrieve only from the document corpora selected for the current query and preserve corpus/document provenance.

4. **Hybrid Knowledge Retrieval**  
   Combine selected internal corpora with external internet sources when web search is enabled.

5. **Agentic Orchestration**  
   Decide retrieval strategies, tool execution, evidence handling, and stopping behavior without violating the query's configured evidence boundaries.

6. **Evidence-Grounded Generation**  
   Produce answers based on retrieved evidence, expose uncertainty and conflicts, and clearly identify sources.

7. **Evaluation & Traceability**  
   Measure retrieval quality, temporal correctness, answer correctness, tool decisions, citations, unsupported claims, latency, and cost.

---

## Global Evidence Invariants

ASTRAG must preserve these constraints across later implementation stages:

- Unselected corpora must not contribute factual evidence to a query.
- Web OFF forbids web evidence.
- Web ON requires web retrieval in V1.
- Evidence provenance must survive ingestion, retrieval, context assembly, and generation.
- Conflicting evidence must be exposed rather than silently reconciled.
- Duplicate evidence must not falsely appear as independent corroboration.
- Temporal metadata and temporal uncertainty are first-class information.
- Short-term conversation may help interpret a query but cannot bypass current evidence boundaries.
- Insufficient evidence is a valid system outcome.

---

## Success Condition

ASTRAG is successful when a user can ask a natural-language question, especially a historical or temporal question, and receive:

- a correct event, fact, explanation, or timeline,
- relevant temporal and semantic context,
- evidence from the sources permitted by the current query,
- clear source attribution,
- explicit disclosure of conflicting evidence,
- and an explicit acknowledgement when reliable evidence is insufficient.

Historical and temporal evaluation remains the primary measure of whether the system fulfills its North Star.

---

## Implementation Roadmap

The detailed implementation is divided into the stages defined in [`stages.md`](./stages.md).

Accepted architecture-wide decisions are recorded in [`docs/architecture/`](./docs/architecture/), including ADRs under [`docs/architecture/decisions/`](./docs/architecture/decisions/).

```text
North Star
    ↓
Stage-by-Stage Architecture
    ↓
Accepted ADRs + Global Architecture
    ↓
Implementation
    ↓
Evaluation
    ↓
Production System
```
