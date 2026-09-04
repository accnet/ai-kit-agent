---
name: ai-kit-implement
description: Implement an approved application or tooling task, run focused validation, and update execution state. Use specialized AI-Kit skills for architecture assessment, public contract design, database/data migration, QA-only validation, review, or status.
---

# AI-Kit Implement

Complete one bounded task at a time and preserve task state as the execution source of truth.

## Workflow

1. If resuming, read `.workspace/session.md`. Identify the feature and task from the request or active state.
2. Verify G1. Standard, large, contract, dependency, or database work requires `.project/<feature>/tasks.md`; if absent, run the `ai-kit-plan` workflow first. A qualifying trivial change uses an inline fix + test + self-review checklist.
3. Route Architect-owned assessment to `ai-kit-assess-architecture`, Architect-owned public contract work to `ai-kit-design-contract`, Database-owned schema/data changes to `ai-kit-migrate-data`, and QA-owned validation to `ai-kit-validate-quality`. Do not continue under the generic workflow when one applies.
4. For planned work, select a claimable task with `.ai-kit/scripts/next-task.sh <feature>` and claim it only when parallel coordination requires an explicit claim.
5. Read `execution.task_cli` from `.ai-kit/config.json`. For a generic implementation task, enabled task-CLI execution authorizes `.ai-kit/scripts/harness.sh step <feature> --task <id>` with its configured provider and optional model. This policy does not route planning, QA, or review. When the route is false, do not call a provider implicitly.
6. If the current prompt already identifies this process as the harness-selected implementer of one bounded task, implement directly and never invoke another `harness step`; this is the recursion boundary.
7. Load the task's owner contract, acceptance criteria, target files, and modules routed by `.ai-kit/modules/INDEX.md`. Use `.ai-kit/scripts/context-pack.sh` as the deterministic starting pack when a task ID exists.
8. Implement only the requested behavior and declared file scope. Stop and re-plan before expanding a public contract, schema, dependency, or task ownership.
9. Run the smallest relevant tests first, then configured lint/typecheck and broader tests proportional to risk.
10. Close G2 only with observable acceptance evidence. Record the result and update `.workspace/session.md` on task switches.

On failure, record and increment `attempts`. Self-correct the first two failures; after the third failed attempt, stop, log `escalated`, and ask the user for direction.

Do not commit, push, deploy, or perform destructive actions unless the user or an explicitly invoked workflow authorizes that action.

## Output

Lead with what changed, validation results, remaining risks, and the next claimable task. Do not claim completion while required review or project-state updates remain open.
