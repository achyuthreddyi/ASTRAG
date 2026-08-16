# ASTRAG — North Star

## Agentic Semantic Temporal Retrieval-Augmented Generation

### End Goal

Build an **agentic RAG system for historical question answering** that can combine:

- Existing local/document knowledge
- Semantic retrieval
- Temporal/date-aware retrieval
- Internet search
- Agentic decision-making

to answer history-related questions with grounded, traceable evidence.

---

## Core User Experience

ASTRAG should support questions such as:

- What happened on this date?
- When did this historical event happen?
- What major events happened between two dates?
- What happened before or after a specific event?
- What do my existing documents say about this event?
- If the answer is not present locally, what reliable information can be found on the internet?

---

## Core System Behaviour

For every user query, ASTRAG should:

```text
User Question
      ↓
Understand Intent + Temporal Context
      ↓
Search Existing Knowledge
      ↓
Determine Whether More Evidence Is Needed
      ↓
Search the Internet When Required
      ↓
Retrieve + Rank Relevant Evidence
      ↓
Combine Temporal + Semantic Context
      ↓
Generate a Grounded Answer
      ↓
Return Sources / Citations
```

The system should not blindly search every source.

The agent should decide:

- whether local retrieval is sufficient,
- whether web search is required,
- which retrieval strategy to use,
- how to combine conflicting or overlapping evidence,
- and when there is not enough evidence to answer confidently.

---

## Key Principle

> **ASTRAG should answer historical questions by reasoning over both meaning and time, while dynamically choosing between internal knowledge and external web sources.**

---

## Primary Capabilities

1. **Semantic Retrieval**  
   Find relevant historical information even when the wording differs from the query.

2. **Temporal Retrieval**  
   Understand dates, ranges, ordering, "before", "after", "on this day", and related temporal relationships.

3. **Hybrid Knowledge Retrieval**  
   Search both internal documents and external internet sources.

4. **Agentic Orchestration**  
   Decide which tools and retrieval paths are required for each query.

5. **Evidence-Grounded Generation**  
   Produce answers based only on retrieved evidence and clearly identify sources.

6. **Evaluation & Traceability**  
   Measure retrieval quality, answer correctness, tool decisions, citations, latency, and cost.

---

## Success Condition

ASTRAG is successful when a user can ask a historical question in natural language and receive:

- the correct event or timeline,
- relevant context,
- evidence from internal documents and/or the web,
- clear source attribution,
- and an explicit acknowledgement when reliable evidence is insufficient.

---

## Implementation Roadmap

The detailed implementation is divided into the stages defined in [`stages.md`](./stages.md).

```text
North Star
    ↓
Stage-by-Stage Architecture
    ↓
Implementation
    ↓
Evaluation
    ↓
Production System
```
