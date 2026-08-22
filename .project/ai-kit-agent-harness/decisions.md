# Decisions — ai-kit-agent-harness

## LLM-first control boundary

Models generate/revise plans, infer dependencies, choose implementation
strategy, and synthesize evidence. The harness validates, authorizes, persists,
schedules, limits retries, and records events.

## Canonical structured state

Harness-managed features use `state.json` as canonical execution state and
render Markdown for humans. Legacy Markdown-only features remain supported.

## Dependency-free local runtime

Use Python 3.9 standard library, JSON/JSONL storage, and subprocess adapters.

## Safe provider defaults

Provider calls are explicit and never bypass sandbox or permission controls.
Planning and review are read-only; implementation gets bounded write access.
