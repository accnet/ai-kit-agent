---
name: ai-kit-status
description: Report AI-Kit feature, task, retry, and session state without changing files. Use for progress or next-task questions, not planning or implementation.
---

# AI-Kit Status

Report machine-derived execution state and make no changes.

## Workflow

1. Read `.project/INDEX.md`. If a feature is specified, limit the report to it.
2. For each relevant feature, run `.ai-kit/scripts/state.sh <feature>` and `.ai-kit/scripts/next-task.sh <feature>`. Treat “no claimable tasks” as state, not a fatal reporting error.
3. Inspect recent retry, gate-fail, and escalation events in `.project/log.jsonl` when present.
4. Compare `.workspace/session.md` with task state and report stale pointers.
5. Read the latest progress entry when present.

## Output

For each feature report state, completed/total tasks, in-progress ownership, next claimable task, blockers, and open questions. End with the single most useful next action. Do not repair stale state during a status request.
