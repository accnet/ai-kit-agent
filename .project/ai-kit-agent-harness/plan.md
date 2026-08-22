# Plan — ai-kit-agent-harness

status: done
source: features/ai-kit-agent-harness/

## Goal

Build a provider-neutral, LLM-first runtime harness that gives Codex and Claude
durable state, selective context memory, policy-controlled scheduling,
replanning, evidence, and independent review.

## Approach

Implement a dependency-free Python runtime under `.ai/harness/`. Store canonical
state and append-only events under `.project/<feature>/`, then render the
existing plan/task Markdown for humans. Models own reasoning; the harness owns
validation, persistence, scheduling, retry limits, approvals, and auditability.

## Risks

- Invalid LLM output → JSON Schema plus deterministic internal validation.
- Excessive provider authority → read-only planning/review and no bypass flags.
- State/Markdown drift → atomic state writes and generated projections.
- Large or stale context → bounded ranking with provenance and source hashes.
- Concurrent corruption → exclusive per-feature transition locks.

## Task Summary

14 tasks after four first-review corrections. T2 defined durable state; T10-T13
added large-plan approval, independent-review evidence, actual mutation
verification, stale-lock recovery, artifact reconciliation, and regressions.
Execution remained sequential because the user did not request parallel agents.
