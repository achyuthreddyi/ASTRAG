# Stage 1: Problem Definition & System Behaviour

## Objective

Define the high-level behavioral contract for ASTRAG before implementation.

ASTRAG is a generic retrieval-augmented generation system optimized primarily for historical and temporal question answering. It should combine user-selected document corpora, temporal and semantic retrieval, optional web evidence, short-term conversational context, and grounded generation.

Historical QA remains the primary optimization target.

---

## Scope

Stage 1 defines:

- supported query classes,
- corpus-selection semantics,
- web-search semantics,
- grounding requirements,
- evidence and conflict behavior,
- citation expectations,
- temporal-query behavior,
- conversational-context boundaries,
- failure and degradation behavior,
- V1 quality targets,
- scale assumptions,
- V1 non-goals.

This stage defines **what the system must do**, not how retrieval, ingestion, orchestration, ranking, or generation are implemented.

---

## Non-Goals

The following are outside V1 scope:

- personalized long-term memory,
- conversational long-term memory,
- OCR,
- scanned/image-only document understanding,
- multimodal historical documents,
- non-English query support,
- user-authored knowledge editing,
- autonomous long-running research,
- definitive subjective historical judgments,
- production-scale multi-user concurrency,
- sophisticated historical-calendar conversion.

General-purpose QA and current-news queries are supported but are not the primary optimization or evaluation target.

---

## Requirements

### 1. Supported Query Classes

V1 must strongly support:

1. Exact-date historical questions  
   Example: “What happened on August 15, 1947?”

2. Event-date lookup  
   Example: “When did the Berlin Wall fall?”

3. Date-range and timeline questions  
   Example: “What major events happened between 1939 and 1945?”

4. Temporal relationship questions  
   Example: “What happened before or after event X?”

5. General historical entity questions  
   Example: “Who was Napoleon?”

ASTRAG may support comparative, causal, and analytical historical questions on a best-effort basis during V1, but these are secondary optimization targets.

Examples:

- “How did US policy toward Vietnam change between 1964 and 1968?”
- “Why did the Soviet Union collapse?”

### 2. General-Purpose Queries

ASTRAG may answer non-historical questions using the same RAG/web infrastructure.

Historical and temporal QA remains the primary product specialization.

Current-news questions may also be answered when web search is enabled, but they are outside the primary V1 evaluation benchmark.

### 3. Tenant and Corpus Model

V1 assumes a single-tenant system.

The user may:

- upload multiple documents,
- organize documents into corpora,
- create multiple corpora,
- select one or more corpora for each query.

The user is assumed to have access to all corpora in V1.

Each query defines its allowed local evidence boundary through its selected corpora.

Documents from unselected corpora must not be used as factual evidence for the query.

### 4. Supported V1 Document Types

V1 supports text-extractable documents including:

- text-based PDF,
- TXT,
- Markdown,
- DOCX.

OCR is outside scope.

Image-only or scanned PDFs requiring OCR are not supported in V1.

### 5. Query Source Configuration

Every query has:

- zero or more selected corpora,
- a web-search toggle.

Valid configurations:

#### Corpus selected + Web OFF

Search only the selected corpora.

All factual claims must be grounded in those corpora.

#### Corpus selected + Web ON

Search both:

- selected corpora,
- web sources.

Both evidence sets are supplied for answer generation.

#### No corpus selected + Web ON

Operate as a web-only grounded query.

#### No corpus selected + Web OFF

Reject the query before retrieval.

The user should be instructed to select at least one corpus or enable web search.

### 6. Web Search Semantics

When web search is ON, web retrieval is mandatory for V1.

If corpora are selected, ASTRAG performs hybrid evidence gathering from:

- selected corpora,
- the web.

The user query cannot override this retrieval configuration.

For example, if web is enabled and the user says:

> “Use only my documents.”

ASTRAG still follows the configured source policy.

Likewise, with selected corpora and web enabled:

> “Ignore my documents and search only the web.”

does not bypass corpus retrieval.

A separate source-mode selector may be introduced in a future version if such behavior becomes necessary.

Web search is a product requirement.

Tavily is the current intended V1 provider, but it is an implementation choice rather than part of the Stage 1 product contract.

### 7. Multi-Corpus Retrieval Semantics

When multiple corpora are selected, they use **union semantics**.

The retrieval system should search across all selected corpora and choose the most relevant evidence globally.

V1 does not require per-corpus balancing or independent retrieval quotas.

### 8. Grounding Policy

When web search is OFF, factual claims must be supported by evidence from the selected corpora.

Pretrained LLM knowledge may assist with:

- understanding the query,
- reasoning about retrieved evidence,
- language generation.

It must not substitute for missing factual evidence.

If sufficient evidence is unavailable, the system must acknowledge this rather than answering from model memory.

Example:

> “The selected corpora do not contain sufficient evidence to answer this reliably.”

When web search is ON, factual answers should be grounded in retrieved corpus and/or web evidence.

### 9. Insufficient Evidence

ASTRAG should prefer supported partial answers over unsupported complete answers.

When only part of the requested information is supported:

1. provide the supported facts,
2. clearly identify uncertainty or incompleteness,
3. avoid inventing missing facts.

For timeline queries, if retrieved evidence cannot establish a complete timeline, the system should explicitly state that limitation.

When no usable evidence can be retrieved:

> “I couldn't retrieve sufficient evidence to answer reliably.”

### 10. Source Authority

V1 does not introduce explicit source-authority ranking.

Sources may include authoritative or unknown sources.

ASTRAG should expose source identity whenever possible.

Unknown sources may still be used, but must be clearly identified as such.

More sophisticated trust scoring, source-quality ranking, or domain weighting is deferred beyond V1.

### 11. Evidence Conflicts

Conflicting evidence must not be silently reconciled.

Conflict handling applies to:

- corpus vs web,
- corpus vs corpus,
- document vs document,
- web source vs web source.

When conflicting claims exist, ASTRAG must:

1. preserve both claims,
2. cite the supporting source for each,
3. explicitly state that the sources conflict,
4. avoid silently choosing a winner.

For legitimately disputed historical interpretations, ASTRAG may present major supported viewpoints and cite each.

It should avoid declaring one interpretation correct unless the evidence clearly and overwhelmingly supports that conclusion.

V1 should keep such interpretation handling simple.

### 12. Duplicate Evidence

Duplicate or substantially identical evidence must not be represented as independent corroboration.

For example, a local document containing a copied web article and that same original article returned through web search should not create the appearance of two independent sources.

The implementation mechanism belongs to later stages.

### 13. Citation Behaviour

V1 uses answer- or paragraph-level citations.

Claim-level citation granularity is not required initially.

Local-source citations should ideally identify:

- corpus,
- document/source,
- page, section, or chunk metadata when available.

Web citations should identify the external source.

If evidence is usable but source metadata is incomplete, the evidence may still be used with a degraded citation such as an unknown source identifier.

If an answer is supported but citations cannot be rendered correctly:

1. return the supported answer,
2. explicitly disclose citation degradation,
3. record the incident as a quality failure.

### 14. Temporal Query Behaviour

ASTRAG must understand common temporal forms including:

- exact dates,
- year ranges,
- before,
- after,
- relative ordering,
- “on this day,”
- approximate dates and periods,
- BCE/CE.

For ambiguous temporal language, ASTRAG should:

1. infer the likely interpretation when reasonably clear,
2. disclose important interpretation assumptions when useful,
3. ask for clarification only when different interpretations would materially alter the answer.

Example:

> “What happened before the French Revolution?”

ASTRAG may return relevant immediate precursors while making its interpretation clear rather than always forcing clarification.

### 15. Relative Dates

Relative-date expressions are resolved using the current date.

Examples:

> “What happened on this day?”

means historical events occurring on the current calendar month/day across different years.

> “What happened 100 years ago today?”

resolves to the exact date 100 years before the current date.

### 16. Historical Date Precision

ASTRAG should preserve uncertainty in historical dates.

Examples:

- “circa 1200 BCE”
- “early 5th century”
- “spring 1917”

Approximate dates must not be silently converted into falsely precise exact dates.

V1 supports Gregorian-style date reasoning, BCE/CE, and approximate natural-language periods.

Sophisticated Julian/Gregorian or other historical calendar conversion is outside V1 scope.

### 17. Timeline Behaviour

Timeline queries should aim to produce a coherent set of significant relevant events.

The system is not required to enumerate every event matching a date range.

The desired behavior is:

> enough well-supported events to form a meaningful historical timeline.

Completeness must not be fabricated when evidence is incomplete.

### 18. Subjective Historical Questions

ASTRAG should not provide unsupported definitive judgments for inherently subjective questions.

Example:

> “Was Napoleon a good leader?”

should not produce an absolute factual verdict.

Evidence-grounded comparative framing is allowed.

Example:

> “What arguments do historians make for and against Napoleon's leadership?”

may be answered when sufficient evidence exists.

### 19. Short-Term Conversational Context

V1 supports short-term conversational context sufficient to resolve follow-up references.

Example:

> User: “When did Napoleon invade Russia?”  
> User: “What happened immediately after that?”

ASTRAG should understand what “that” refers to.

This does not imply long-term conversational memory.

The system only promises enough recent context to resolve relevant references.

### 20. Conversation vs Evidence Boundaries

Conversation history may help interpret the current query but must not bypass current retrieval constraints.

Example:

1. Query 1 uses Corpus A.
2. Query 2 switches to Corpus B.
3. User asks, “What happened next?”

Conversation context may establish what “next” refers to.

However, factual evidence for Query 2 must come only from Corpus B and/or web according to Query 2's configured retrieval settings.

---

## Assumptions

### V1 Embeddings

V1 assumes a single embedding model.

This is an implementation assumption, not a permanent product constraint.

Later architecture should allow the embedding model to be replaced without redefining the Stage 1 behavioral contract.

### Deployment Scale

V1 targets a medium-scale design envelope:

- hundreds to thousands of documents,
- potentially up to approximately 1 million chunks.

Initial evaluation datasets may be considerably smaller.

### Concurrency

V1 assumes:

- one primary user,
- low request concurrency.

Architecture should avoid unnecessarily preventing future scaling, but production-scale concurrency is not a V1 requirement.

---

## Key Design Decisions

1. Historical QA is the primary optimization target, not the exclusive query domain.
2. Per-query corpus selection determines the local evidence boundary.
3. Web search is explicitly user controlled.
4. Web ON means mandatory web retrieval for V1.
5. When corpora are selected and web is ON, both local and web evidence are retrieved.
6. Web OFF enforces strict corpus grounding.
7. Pretrained model knowledge is not a valid substitute for missing factual evidence.
8. Multi-corpus search uses union semantics.
9. Source-authority ranking is deferred.
10. Conflicts are surfaced rather than silently resolved.
11. Unsupported partial answers are preferred over fabricated completeness.
12. Short-term conversation context is supported without long-term memory.
13. Paragraph/answer-level citations are sufficient for V1.

---

## Proposed Architecture

Stage 1 does not prescribe implementation architecture.

The required behavioral flow is conceptually:

```text
User Query
    +
Selected Corpora
    +
Web Toggle
    +
Relevant Short-Term Conversation Context
        ↓
Understand Query + Temporal Intent
        ↓
Determine Allowed Evidence Sources
        ↓
Retrieve Selected Corpora
        ↓
Retrieve Web Evidence if Web = ON
        ↓
Assess Evidence
        ↓
Identify Conflicts / Missing Evidence
        ↓
Generate Grounded Answer
        ↓
Return Answer + Citations + Uncertainty / Conflict Disclosure
```

Detailed implementation belongs to later stages.

---

## Components

Stage 1 establishes conceptual responsibilities only:

- Query interface
- Corpus-selection boundary
- Web-search configuration
- Query/temporal understanding
- Evidence retrieval
- Evidence assessment
- Conflict detection
- Grounded generation
- Citation/provenance presentation
- Short-term conversational context

Concrete component boundaries will be defined in later stage documents.

---

## Data Flow

### Local-only query

```text
Query
 + Selected Corpora
 + Web OFF
       ↓
Retrieve Only Selected Corpora
       ↓
Evidence Assessment
       ↓
Grounded Answer
       ↓
Local Citations
```

### Hybrid query

```text
Query
 + Selected Corpora
 + Web ON
       ↓
Local Retrieval + Web Retrieval
       ↓
Combined Evidence
       ↓
Conflict / Sufficiency Assessment
       ↓
Grounded Answer
       ↓
Local + Web Citations
```

### Web-only query

```text
Query
 + No Corpus
 + Web ON
       ↓
Web Retrieval
       ↓
Evidence Assessment
       ↓
Grounded Answer
       ↓
Web Citations
```

---

## Interfaces / Contracts

### Query Input Contract

Conceptually, every query contains:

```text
question
selected_corpora[]
web_enabled
conversation_context
```

Exact API schemas belong to later stages.

### Evidence Boundary Contract

Only evidence allowed by the current query configuration may support factual claims.

### Retrieval Outcome Contract

The system must distinguish:

- successful retrieval with relevant evidence,
- successful retrieval with no relevant evidence,
- retrieval subsystem failure.

These states must not be conflated.

---

## Failure Cases

### No Relevant Local Evidence

With web OFF:

> indicate that selected corpora contain insufficient evidence.

### Web Search Failure

If local retrieval succeeds:

- answer using supported local evidence,
- state that web retrieval failed.

### Local Retrieval Failure

If web retrieval succeeds:

- answer using supported web evidence,
- disclose local retrieval failure.

### Partial Corpus Failure

If some selected corpora fail:

- use evidence from successful corpora,
- disclose which retrieval scope failed.

### Both Local and Web Retrieval Fail

Do not improvise using pretrained model knowledge.

Return an insufficient-evidence response.

### Unknown Citation Source

Evidence may be used with explicit degraded provenance.

### Citation Rendering Failure

Return the supported answer with a citation warning and record a quality failure.

---

## Evaluation Criteria

V1 evaluation should include:

- exact-date questions,
- event-date lookup,
- date ranges,
- timelines,
- before/after queries,
- historical entity queries,
- insufficient-evidence scenarios,
- conflicting evidence,
- multi-corpus retrieval,
- web-only queries,
- corpus + web hybrid queries,
- conversational follow-ups.

### Initial Quality Targets

#### Answer Correctness

Target:

**≥ 90%**

on a curated V1 historical QA evaluation dataset.

#### Citation Support Correctness

Target:

**≥ 95%**

of presented citations should genuinely support the associated answer content.

#### Temporal Correctness

Target:

**approximately ≥ 90%**

for:

- date interpretation,
- range handling,
- temporal ordering,
- before/after relationships,
- relative-date resolution.

#### Unsupported Claims

Target:

**< 2% unsupported material factual claims**

on the curated evaluation dataset.

These are initial Stage 1 targets and may be refined by Stage 7 as the evaluation framework matures.

---

## Latency / Throughput Requirements

Latency is not a primary V1 optimization target.

No hard latency acceptance gate is defined in Stage 1.

Latency should still be measured so later optimization decisions are evidence based.

V1 assumes low concurrency.

---

## Cost Requirements

V1 does not define a hard per-query monetary ceiling.

The system must make it possible to observe per-query costs associated with:

- LLM calls,
- embeddings where applicable,
- retrieval infrastructure,
- web-search calls.

Cost optimization may occur after baseline quality is established.

---

## Dependencies

Stage 1 establishes requirements consumed by:

- Stage 2: Data Ingestion
- Stage 3: Retrieval
- Stage 4: Agent / Orchestration
- Stage 5: Context Assembly
- Stage 6: Generation
- Stage 7: Evaluation
- Stage 8: Observability
- Stage 9: Guardrails & Reliability
- Stage 10: Production / Serving

Major downstream dependencies include:

- corpus identity and metadata,
- document provenance,
- temporal metadata,
- web retrieval,
- evidence-source tracking,
- query-level retrieval configuration,
- conversational-context propagation.

---

## Implementation Plan

Stage 1 contains no implementation work.

After Stage 1 receives orchestrator approval:

1. update accepted product-level documentation,
2. create required ADRs if architectural alternatives warrant them,
3. propagate the Stage 1 behavioral contract into later stage designs,
4. begin Stage 2 ingestion design,
5. introduce evaluation examples early rather than waiting until Stage 7.

---

## Open Questions

The following are intentionally deferred:

- detailed source-quality ranking,
- trusted-domain policies,
- claim-level citation granularity,
- sophisticated calendar conversion,
- comparative/causal historical reasoning quality requirements,
- source-mode configuration beyond the simple web toggle,
- exact conversation-context window,
- exact API schemas,
- exact embedding model,
- retrieval algorithms,
- ranking/reranking strategies,
- latency optimization,
- hard cost ceilings,
- production concurrency.

---

## Decisions Requiring Orchestrator Approval

### 1. Product Scope Expansion

Current North Star framing emphasizes an historical RAG system.

Stage 1 proposes clarifying the product as:

> A generic evidence-grounded RAG system with historical and temporal QA as its primary optimization target.

This allows general-purpose and current-news questions while preserving historical QA as the primary benchmark and product specialization.

This change affects the project-wide product definition and therefore requires orchestrator approval.

### 2. Query-Controlled Mandatory Hybrid Retrieval

The current North Star describes web retrieval as something the system performs when additional evidence is required.

Stage 1 instead proposes explicit user-controlled source semantics:

- Web OFF → selected corpora only.
- Web ON + selected corpora → selected corpora **and web are both searched**.
- Web ON + no corpora → web-only.
- Web OFF + no corpora → invalid query.

This changes global retrieval behavior and therefore requires orchestrator approval and, if accepted, an update to the North Star and potentially the global architecture.

---

## Acceptance Criteria

Stage 1 is complete when:

- supported query classes are documented,
- V1 scope and non-goals are documented,
- corpus-selection semantics are explicit,
- web-search semantics are explicit,
- grounding constraints are explicit,
- pretrained model knowledge boundaries are explicit,
- conflict behavior is explicit,
- citation behavior is explicit,
- insufficient-evidence behavior is explicit,
- temporal ambiguity behavior is explicit,
- conversational-context behavior is explicit,
- retrieval failure and degradation behavior is explicit,
- initial quality targets are defined,
- scale and concurrency assumptions are documented,
- product-level changes are surfaced to the orchestrator,
- unresolved implementation details are correctly deferred to later stages.

Stage 1 does **not** require selection of:

- vector database,
- embedding provider,
- chunking strategy,
- reranker,
- agent framework,
- prompt architecture,
- database schema,
- API framework.

---

## Impact on Existing Architecture

No accepted global architecture currently exists to modify.

However, the Stage 1 requirements impose future architectural constraints around:

- explicit corpus boundaries,
- query-level source configuration,
- provenance preservation,
- hybrid local/web retrieval,
- conflict preservation,
- temporal reasoning,
- short-term conversational context,
- retrieval failure isolation,
- evaluation and traceability.

These should be incorporated into `docs/architecture/architecture.md` only after orchestrator approval.

---

## Orchestrator Handoff

### Stage

Stage 1: Problem Definition & System Behaviour

### Status

**Reviewed / awaiting orchestrator approval**

### Major Decisions

- Historical QA is the primary optimization target.
- General-purpose RAG queries remain supported.
- Users organize uploaded documents into selectable corpora.
- Each query defines its permitted corpora.
- Web search is controlled per query.
- Web ON means mandatory web retrieval in V1.
- Web OFF enforces strict selected-corpus grounding.
- Model memory cannot replace missing factual evidence.
- Conflicts are explicitly disclosed without silently choosing a winner.
- Short-term conversational context is supported.
- V1 uses paragraph/answer-level citations.
- Initial quality targets are defined.

### Architecture Changes Proposed

- Introduce query-scoped corpus boundaries.
- Introduce explicit query-level web configuration.
- Require hybrid local + web evidence gathering when web is enabled.
- Preserve provenance and conflicts through the end-to-end system.

### Dependencies

Stages 2–10 consume this contract.

### ADRs Required

None identified yet from Stage 1 alone.

Specific technology choices may generate ADRs during later stages.

### New Specs Required

None at this stage.

### Open Questions

Implementation-level retrieval, ranking, source authority, model selection, and API schemas remain deferred.

### Risks

- Mandatory web retrieval may increase cost.
- Lack of source-quality ranking may reduce research reliability.
- Conflict disclosure without authority ranking can leave users with unresolved competing claims.
- Medium-scale corpus targets may influence ingestion and retrieval architecture substantially.
- General-purpose QA capability could gradually dilute historical specialization if later stages are not kept aligned.

### Files Created or Updated

Proposed:

- `docs/stages/01-problem-definition.md`

Pending orchestrator approval:

- `NORTHSTAR.md`
- future `docs/architecture/architecture.md`, if required by accepted architectural changes.
