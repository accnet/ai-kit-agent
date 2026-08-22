# Brief — AI-Kit Agent Harness v0.6

status: approved
approved-by: user directive, 2026-08-22

## Problem

AI-Kit v0.5 gives Codex and Claude a shared operating protocol, skills, gates,
and human-readable task state, but it does not provide a runtime harness.
Planning and routing remain advisory, context is reconstructed manually, and
there is no durable machine state that can safely resume an LLM-driven loop.

## Required outcome

- Codex or Claude owns reasoning, plan generation, task decomposition,
  replanning, execution strategy, and evidence synthesis.
- A provider-neutral harness validates and persists plans, schedules bounded
  tasks, applies policy and approvals, records events, and resumes safely.
- Machine state is canonical; Markdown plan/task files are generated views.
- Context retrieval is selective and provenance-aware, with durable working,
  episodic, and semantic memories.
- Codex and Claude CLI adapters support structured planner, implementer, and
  reviewer calls without bypassing sandbox or approval controls.
- A scripted provider makes the loop testable without network or model spend.

## Constraints

- Use only Python 3.9 standard library and existing shell tooling.
- Provider calls are opt-in; tests never invoke Codex, Claude, or a network.
- Preserve `features/` as intent and `.project/` as execution state.
- Never add flags that bypass sandboxing, approvals, hooks, or permissions.
- Database, destructive, production, credential, and external-write tasks stay
  blocked until explicit per-task approval is recorded.
- Preserve v0.5 Markdown workflows; structured state is opt-in per feature.

## Acceptance

- A fixture can initialize a feature, accept an LLM plan, schedule a safe task,
  record evidence, require review, replan, and resume from disk.
- Invalid plans, cycles, scope violations, retry exhaustion, unapproved risks,
  and invalid provider output fail closed.
- Retrieval is bounded and exposes provenance, hashes, and stale sources.
- Codex/Claude commands use structured output and safe permission defaults.
- Markdown projections and append-only events are deterministic and valid.
- `bash .ai/tests/run.sh` and `.ai/scripts/doctor.sh --full` pass.
