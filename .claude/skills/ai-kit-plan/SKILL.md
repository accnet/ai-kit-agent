---
name: ai-kit-plan
description: Plan a non-trivial feature, bug, refactor, or database change using AI-Kit's project state and acceptance gates. Do not use for read-only analysis or a fully trivial edit.
---

# AI-Kit Plan

Produce an executable plan without implementing application code.

## Workflow

1. Read the user's request and any `features/<feature>/` requirements. Treat `features/` as read-only unless acting as Researcher.
2. Load `.ai/modules/gates.md`, `.ai/modules/planning/intent-analysis.md`, and `.ai/agents/planner.md`.
3. Classify one primary intent, size the work, state the goal, and list explicit exclusions and blocker questions.
4. If every trivial criterion passes, return the inline checklist from intent analysis and stop. Any database data/schema change requires a full plan.
5. For standard or large work, load the planning modules routed by `.ai/modules/INDEX.md`. Add architecture first when the design is non-obvious or large.
6. Write `.project/<feature>/plan.md` and `tasks.md`. Every task needs one owner, exclusive file scope, dependencies, and observable binary acceptance criteria.
7. Add or refresh `.project/INDEX.md` with state `active`.

Do not invent missing product decisions. A plan with unresolved blockers remains draft and must not authorize implementation.

## Output

Report the task count, riskiest task, parallelizable tasks, and any blockers. G1 passes only when the full plan has no unresolved blockers or the work qualifies for the documented trivial path.
