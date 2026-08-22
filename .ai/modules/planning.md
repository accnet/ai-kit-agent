---
name: planning
description: Plan assembly router for non-trivial feature, bug, and refactor work.
---

# Module: Planning

## Purpose
Turn a brief into a verified, executable plan before any code is written.

## When to Load
Always, at the start of any feature/bug/refactor. Planning is mandatory (rules.yaml: planning_first).

## Submodules
Load in this order, only what the task needs:

1. `planning/intent-analysis.md` — always. Classify the request first.
2. `planning/task-breakdown.md` — when intent is feature or refactor.
3. `planning/acceptance.md` — always. Every task needs done criteria.
4. `planning/planning.md` — the plan assembly process itself.

Small bugfix with obvious scope → intent-analysis + acceptance is enough.

## Rules
- No implementation before tasks.md exists and is coherent
- A plan the user can't verify is not a plan — acceptance criteria are mandatory
- Re-plan when scope changes; don't silently extend the current plan

## Output
`.project/<feature>/tasks.md` following `templates/tasks.md`.
