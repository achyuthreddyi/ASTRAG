# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

Design-only repo. No source code, dependencies, build, or test commands exist yet.
Everything here is `NORTHSTAR.md` (the goal) and `stages.md` (the 10-stage plan).
When the first code lands, replace this section with the real build/lint/test commands.

## What ASTRAG is

Agentic RAG for **historical** question answering: "what happened on this date",
"what happened between X and Y", "before/after event Z". Two retrieval axes that
must work together — **semantic** (meaning) and **temporal** (dates, ranges,
ordering) — plus an agent that decides per-query whether local documents suffice
or web search is needed.

## Constraints that shape design decisions

- The agent must *choose* retrieval paths, not fan out to every source on every query.
- Answers are grounded only in retrieved evidence, with source citations; "insufficient
  evidence" is a valid, expected output, not a failure.
- Temporal metadata is first-class through the whole pipeline — extract it at ingestion,
  filter on it at retrieval, order by it during context assembly.
- Evaluation (stage 7) and tracing (stage 8) are meant to be built early alongside the
  other stages, not bolted on at the end.

## Working with the plan

`stages.md` is the roadmap, not a schedule — stages 1–6 are the core path; 7–10 are
built incrementally against them. Before adding a component, check which stage owns it
so responsibilities stay where the plan puts them (e.g. dedup and token budgeting live
in Context Assembly, not in the retriever).
