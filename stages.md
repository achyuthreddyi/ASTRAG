# Agentic RAG Application — Major Implementation Stages

This document defines the major stages required to build an Agentic RAG application.

## 1. Problem Definition & System Behaviour

Define the expected behaviour of the system before implementation.

Key decisions:
- What kinds of questions should the system answer?
- What data sources will be available?
- When should the system use internal RAG retrieval?
- When should it use web search or external tools?
- What should happen when there is insufficient evidence?
- What are the latency, accuracy, and cost expectations?

This becomes the high-level system contract.

---

## 2. Data Ingestion Pipeline

Build the pipeline responsible for converting raw knowledge into searchable data.

Typical flow:

```text
Documents
   ↓
Parsing / Cleaning
   ↓
Chunking
   ↓
Metadata Extraction
   ↓
Dense / Sparse Embeddings
   ↓
Vector DB + Document Store
```

Also consider:
- Document versioning
- Incremental ingestion
- Re-indexing
- Document updates
- Deletions

---

## 3. Retrieval Pipeline

Build the system responsible for finding the most relevant information for a query.

Typical flow:

```text
User Query
   ↓
Query Understanding
   ↓
Dense Search
Sparse Search
Metadata Filtering
   ↓
Hybrid Retrieval
   ↓
Reranking
   ↓
Top-K Context
```

Major components may include:
- Dense retrieval
- Sparse retrieval
- Hybrid search
- Metadata filtering
- Query rewriting
- Reranking

---

## 4. Agent / Orchestration Layer

Build the decision-making layer that determines how the system should answer the user's request.

Typical flow:

```text
User Question
      ↓
    Agent
      ↓
 ┌────┼───────────┐
 ↓    ↓           ↓
RAG  Web Search   Other Tools
 ↓    ↓           ↓
 └────┴─────┬─────┘
            ↓
       Reason / Loop
            ↓
        Final Answer
```

Responsibilities:
- Tool selection
- Multi-step execution
- Planning
- State management
- Retry behaviour
- Memory
- Loop / stopping conditions
- Failure handling

---

## 5. Context Assembly

Transform the completed Stage 4 `EvidenceGatheringResult` into a provenance-safe, duplicate-aware, conflict-preserving, token-bounded structured `GenerationContext` for Stage 6.

Responsibilities:
- Evidence-policy and provenance revalidation
- Evidence relationship / semantic duplicate analysis
- Independent corroboration semantics
- Material conflict grouping
- Question/subquestion coverage assessment
- Final evidence relevance / utility reassessment
- Context ranking and selection
- Soft source/document/domain/task diversity control
- Token budgeting
- Context ordering
- Chronological organization when required
- Provenance-preserving extractive trimming
- Final evidence sufficiency and partial-answer support
- Structured `GenerationContext` construction

Stage 5 does **not** own system/generation prompt construction, final answer wording, final citation rendering, or user-facing response formatting.

The goal is to provide Stage 6 with the smallest useful and highest-quality evidence context while preserving source boundaries, provenance, temporal uncertainty, conflicts, unsupported aspects, and required-source failure/degradation state.

---

## 6. Generation Layer

Transform the Stage 5 `GenerationContext` into a validated, evidence-grounded canonical response without recomputing upstream evidence semantics.

Typical flow:

```text
GenerationContext
+ trusted GenerationControl
+ normalized PresentationRequest
        ↓
GenerationRequest
        ↓
Versioned Prompt Construction
        ↓
Provider-Neutral Structured Generation
        ↓
GenerationResult
        ↓
Schema / Referential / Grounding Validation
        ↓
Safe Deterministic Repair
        ↓
At Most One Bounded Repair Generation
        ↓
Citation Resolution
        ↓
Canonical GeneratedResponse
        ↓
Rendering / Presentation Validation
        ↓
GenerationExecutionResult
```

Responsibilities:
- Treat Stage 5 relationship/conflict/coverage/sufficiency semantics as authoritative
- Require material factual propositions to bind to permitted evidence
- Distinguish direct claims from bounded evidence-grounded derivations
- Preserve conflict, uncertainty, temporal precision, and required-source failures
- Construct typed/versioned generation prompts with retrieved evidence isolated as untrusted data
- Normalize compatible user presentation/schema requests without allowing them to weaken grounding
- Maintain a provider-neutral structured-output boundary
- Validate model output deterministically before release
- Apply safe deterministic repair and at most one bounded semantic repair generation
- Keep transport retries separate and bounded
- Resolve claim support to deterministic provenance-backed citation identities
- Produce a canonical structured `GeneratedResponse` independent of Markdown/API/CLI transport
- Render/sanitize approved user-facing response forms
- Emit structured generation/evaluation/observability artifacts and version lineage
- Fail closed when grounded output cannot be produced safely

Stage 6 does **not**:
- initiate retrieval or adjacent-context fetching,
- rerank/reselect Stage 5 evidence as a second context-assembly stage,
- upgrade Stage 5 evidence sufficiency,
- invent source-authority/trust rankings,
- use model memory as an independent factual evidence source,
- run open-ended agentic writer/verifier loops,
- stream unvalidated semantic answer content to the user in V1,
- execute arbitrary tools/side effects beyond the configured generation-provider call.

The Stage 6 output is a canonical structured response plus execution/trace metadata. Stage 7 evaluates it; Stage 8 observes it; Stage 9 may add stricter guardrails without weakening grounding; Stage 10 delivers compatible renderings without mutating answer semantics.

---

## 7. Evaluation Framework

Build an evaluation framework to measure the quality of the complete system and individual components.

Example evaluation dataset:

```text
Question
Expected Answer
Expected Sources
Expected Tool
Expected Behaviour
```

Evaluate:
- Retrieval quality
- Reranker quality
- Context assembly quality
- Answer correctness
- Faithfulness
- Hallucination / unsupported-claim rate
- Claim-support correctness
- Citation binding and rendering correctness
- Conflict / uncertainty preservation
- Temporal precision preservation
- Sufficiency compliance
- Generation schema/repair/failure behaviour
- Tool selection
- Agent trajectory
- Latency
- Token usage
- Cost

Stage 7 consumes structured Stage 6 artifacts such as claim-support bindings, citation bindings, validation outcomes, repair history, version references, and canonical responses. Stage 7 is evaluative in V1 and does not become an always-on live response judge or rewriting layer.

Evaluation should be introduced early and continuously expanded while the system is being built.

---

## 8. Observability & Debugging

Add end-to-end tracing so that every material system decision can be inspected.

Track:

```text
Query
 ↓
Agent Decision / Retrieval Runs
 ↓
Retrieved Evidence
 ↓
Context Assembly Decisions
 ↓
GenerationRequest + Version Refs
 ↓
Provider / Generation Attempts
 ↓
Validation + Repair Outcomes
 ↓
Claim / Citation Bindings
 ↓
Canonical GeneratedResponse
 ↓
Tokens / Latency / Cost
```

Stage 8 formalizes structured Stage 6 lifecycle events and trace retention/redaction. Observability data is not factual evidence authority, and hidden chain-of-thought persistence is not required.

Observability should make it possible to understand why a request succeeded or failed.

---

## 9. Guardrails & Reliability

Build protections around failure modes and unsafe or unreliable behaviour.

Handle:
- Hallucination
- Irrelevant retrieval
- Missing evidence
- Tool failures
- Search failures
- Timeouts
- Retries
- Infinite agent loops
- Prompt injection
- Malicious retrieved content
- Unsupported answers

Stage 9 may add stricter cross-cutting controls, blocking, and reliability policies, but it must not weaken accepted evidence grounding, citation integrity, evidence-as-data separation, sufficiency monotonicity, or fail-closed generation behaviour.

The goal is predictable system behaviour even when individual components fail.

---

## 10. Production / Serving Layer

Turn the system into a reliable production service.

High-level architecture:

```text
Client
  ↓
API Layer
  ↓
Agent Service
  ↓
Retrieval / Search Services
  ↓
Vector DB / Document Store
  ↓
LLMs / External Tools
```

Production concerns:
- Authentication
- Authorization
- Rate limiting
- Caching
- Async execution
- Queues
- Persistence
- Horizontal scaling
- Monitoring
- Logging
- Deployment
- Cost controls

Stage 10 owns transport/deployment topology and delivery of approved response renderings. It must preserve the semantic content of the validated Stage 6 canonical `GeneratedResponse`.

---

## High-Level Roadmap

```text
1. Problem Definition
        ↓
2. Data Ingestion
        ↓
3. Retrieval
        ↓
4. Agent / Orchestration
        ↓
5. Context Assembly
        ↓
6. Generation
        ↓
7. Evaluation
        ↓
8. Observability
        ↓
9. Guardrails & Reliability
        ↓
10. Production / Serving
```

> Note: Evaluation is listed as a separate architectural stage, but it should be introduced early and continuously used while building the other stages.
