# ADR-011: Evidence Relationship and Corroboration Semantics

## Status

Accepted

## Context

ASTRAG requires duplicate or substantially copied evidence not to appear as independent corroboration. Earlier stages intentionally preserve identity and retrieval lineage but defer semantic/source-level duplicate analysis and corroboration semantics to Stage 5.

Stage 2 preserves source/chunk hashes and lineage signals. Stage 3 consolidates repeated hits for the same canonical local chunk while preserving route signals. Stage 4 may consolidate operationally identical evidence but does not decide whether different documents, URLs, domains, or rewritten passages share one information source.

Stage 5 therefore needs a durable semantic model that can represent copied/derivative evidence without destroying provenance or pretending uncertain dependence is independence.

Several designs are viable:

1. count distinct documents/URLs/domains as independent sources,
2. use exact-content hashes only,
3. collapse all semantically similar evidence into one anonymous item,
4. explicitly model evidence relationship/dependence while preserving every source identity.

## Decision

ASTRAG Stage 5 explicitly distinguishes evidence identity/content similarity from information-source independence.

The V1 evidence relationship states are:

```text
SAME_IDENTITY
EXACT_DUPLICATE
DERIVATIVE
INDEPENDENT
UNKNOWN_DEPENDENCE
```

### Same identity

Repeated retrieval of the same canonical evidence identity is one evidence item regardless of how many retrieval runs returned it.

Examples include:

- the same local canonical `chunk_id`,
- a confidently identical canonical web resource already consolidated by Stage 4.

Repeated retrieval does not increase corroboration.

### Exact duplicate

Different source identities may carry substantially identical evidence text.

Examples include:

- duplicated uploaded documents,
- a copied local article and its web original,
- mirrored web pages.

Different documents containing the same copied evidence count as one corroborative information unit for that copied content.

### Derivative evidence

Syndicated, copied, lightly rewritten, or materially derivative evidence is represented as a dependency family even when source identity and wording differ.

V1 uses a conservative policy: when derivation is reasonably suspected, the evidence does not count as independently corroborative unless independence is reasonably established.

### Independent evidence

Evidence is treated as independent only when Stage 5 has adequate basis to regard the supporting information as not known to derive from the same underlying information source.

A different URL, domain, document, corpus, or retrieval run is not by itself evidence of independence.

### Unknown dependence

If dependence cannot be safely established, Stage 5 records `UNKNOWN_DEPENDENCE` rather than assuming independence.

`UNKNOWN_DEPENDENCE` is not proof that sources are derivative. It is a conservative statement that independence has not been established. Such evidence may remain useful and separately cited, but it is not counted as established independent corroboration.

Stage 6 may refer to such evidence as multiple sources but must not claim they are multiple independent sources solely from source count.

### Relationship groups

Stage 5 may represent related evidence conceptually as:

```text
EvidenceRelationshipGroup
- group_id
- relationship_type
- member_evidence_ids[]
- representative_evidence_id?
- alternate_provenance[]
- relationship_basis[]
```

The exact schema is an implementation detail as long as the semantic distinctions survive to Stage 6/evaluation/observability.

### Representative text with alternate provenance

For exact/derivative families, Stage 5 normally retains one representative textual item in `GenerationContext` and preserves alternate provenance/retrieval-lineage references for the other members.

Additional family members may be selected when they contribute materially distinct useful context or provenance.

This reduces token duplication without erasing evidence-source history.

### Corroboration model

V1 corroboration is descriptive and structural rather than a numeric confidence/truth score.

Stage 5 may expose concepts such as:

```text
supporting_evidence_ids[]
independent_support_units[]
dependency_groups[]
dependence_uncertain
```

Raw source/evidence count must never substitute for independent-support count.

V1 does not introduce a numeric corroboration-confidence score.

### No source-authority policy

This ADR does not introduce:

- trusted-domain ranking,
- source-authority scores,
- majority-vote truth,
- preferred-source factual winner selection.

Evidence independence and factual authority are separate concepts.

## Consequences

### Positive

- Copied/syndicated material cannot masquerade as multiple independent confirmations.
- Multiple retrieval runs cannot inflate corroboration.
- Provenance remains complete even when redundant text is removed from context.
- Uncertain dependence remains explicit instead of silently becoming independence.
- Stage 6 can make careful source-count/independence statements.
- Stage 7 can directly measure false corroboration.

### Negative

- Stage 5 must analyze relationships beyond simple identity/hash equality.
- Derivative-source classification may be uncertain and implementation-sensitive.
- Conservative handling may undercount some genuinely independent sources when dependence cannot be established.
- Relationship groups add metadata to the Stage 5 → Stage 6 contract.

## Alternatives Considered

### Different document/URL/domain means independent

Rejected because syndicated/copied evidence would create false corroboration.

### Exact-hash deduplication only

Rejected because lightly rewritten and syndicated evidence can remain derivative without byte-identical content.

### Aggressive semantic collapse

Rejected because semantic similarity does not prove common lineage, and aggressive collapse could destroy genuinely independent corroboration.

### Binary independent/not-independent model

Rejected because unresolved dependence is common enough that forcing a binary choice would silently overstate certainty.

### Numeric corroboration score

Deferred because V1 has no calibrated probabilistic model supporting a meaningful confidence value.

## Revisit Triggers

Revisit this ADR if:

- evaluation shows conservative derivative detection materially undercounts useful corroboration,
- source-copy lineage becomes explicitly available from providers/metadata,
- calibrated source-independence probabilities become justified,
- future source-authority ranking is separately accepted,
- generative compression changes how representative evidence/provenance is packaged.

## Affected Stages

- Stage 2 — Data Ingestion Pipeline
- Stage 4 — Agent / Orchestration Layer
- Stage 5 — Context Assembly
- Stage 6 — Generation Layer
- Stage 7 — Evaluation Framework
- Stage 8 — Observability & Debugging
- Stage 9 — Guardrails & Reliability

## Related Documents

- `NORTHSTAR.md`
- `docs/architecture/architecture.md`
- `docs/stages/01-problem-definition.md`
- `docs/stages/02-ingestion.md`
- `docs/stages/03-retrieval.md`
- `docs/stages/04-agent-orchestration.md`
- `docs/stages/05-context-assembly.md`
- `docs/architecture/decisions/ADR-002-ingestion-identity-versioning-publication.md`
- `docs/architecture/decisions/ADR-005-v1-local-hybrid-retrieval-fusion-policy.md`
- `docs/architecture/decisions/ADR-010-evidence-gathering-and-web-retrieval-contract.md`