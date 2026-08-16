# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

Design-only repo. No source code, dependencies, build, or test commands exist yet.
The governing design sources are `NORTHSTAR.md`, accepted ADRs, `docs/architecture/architecture.md`, `stages.md`, and the stage documents under `docs/stages/`.
When the first code lands, replace this section with the real build/lint/test commands.

## What ASTRAG is

ASTRAG is an evidence-grounded agentic RAG system that supports general-purpose retrieval-augmented QA while being specifically optimized for **historical and temporal** question answering: "what happened on this date", "what happened between X and Y", and "before/after event Z".

Two retrieval axes must work together:

- **semantic** — meaning and relevance,
- **temporal** — dates, ranges, ordering, and temporal relationships.

Users organize uploaded documents into corpora and configure the evidence sources allowed for each query.

## Constraints that shape design decisions

- Query-level source configuration is authoritative.
- With **Web OFF**, factual evidence must come only from the selected corpora.
- With **Web ON**, web retrieval is mandatory in V1. If corpora are also selected, both selected corpora and the web are searched.
- With no selected corpus and Web ON, the query is web-only. With no selected corpus and Web OFF, the query is invalid.
- The agent may choose **how** to retrieve, query, rank, retry, combine evidence, and stop, but it must not override the configured evidence sources.
- Answers are grounded only in retrieved evidence, with source citations; "insufficient evidence" is a valid, expected output, not a failure.
- Unselected corpora must never contribute factual evidence to the current query.
- Evidence provenance and conflicts must survive through retrieval, context assembly, and generation.
- Temporal metadata is first-class through the whole pipeline: extract it at ingestion, filter/reason over it at retrieval, and order/preserve it during context assembly.
- Short-term conversational context may resolve references such as "that event" but cannot bypass the current query's evidence boundary.
- Evaluation (stage 7) and tracing (stage 8) are meant to be built early alongside the other stages, not bolted on at the end.

The V1 query-source execution policy is recorded in `docs/architecture/decisions/ADR-001-query-source-execution-policy.md`.

## Working with the plan

`stages.md` is the roadmap, not a schedule. Stages 1–6 are the core path; 7–10 are built incrementally against them.

Before adding or changing a component:

1. Read `NORTHSTAR.md`.
2. Read accepted ADRs relevant to the change.
3. Read `docs/architecture/architecture.md`.
4. Read the owning stage document.
5. Keep the component within its stage boundary unless an architecture change is explicitly reviewed.

For example, deduplication and token budgeting belong in Context Assembly rather than being casually smuggled into the retriever because someone found a convenient function file.
