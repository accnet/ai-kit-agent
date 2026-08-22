# Plan — multi-service-contracts

status: done
source: user conversation, 2026-08-22

## Goal
Extend the AI-Kit harness with versioned multi-service contracts so Codex and Claude can plan and execute frontend, backend, API, event, and database work without crossing ownership or consuming stale interfaces.

## Approach
Keep the existing single-service plan format valid, then add an optional service and contract graph. Normalize that graph into canonical state, enforce ownership and writer/reader dependencies deterministically, block readers on draft or stale contract sources, expose explicit contract approval, and include the graph in projections and model prompts. See `architecture.md`.

## Exclusions
- No production deployment adapter, service discovery integration, or network registry.
- No automatic OpenAPI/AsyncAPI semantic compatibility diff in this iteration.
- No cross-feature distributed scheduler; hierarchy is represented as program/workstream metadata.

## Risks
- Expanding provider JSON schemas can make prompts harder to satisfy -> preserve old required fields and test legacy plans.
- Contract approval can deadlock scheduling -> return a typed blocked reason and expose an explicit CLI transition.
- Stale hashes can be mistaken for approval -> recompute hashes from repository files at scheduling and approval time.
- Multi-service ownership rules can be overly rigid -> enforce them only when a service registry is present.

## Task Summary
9 tasks including QA, review, documentation, and release-state updates. Riskiest first: T2 contract policy and scheduler enforcement.
