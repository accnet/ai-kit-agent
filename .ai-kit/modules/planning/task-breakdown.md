---
name: task-breakdown
description: Split planned work into atomic tasks with explicit ownership and dependencies.
---

# Task Breakdown

## Purpose
Split planned work into atomic, independently verifiable tasks.

## Atomic Task Definition
A task is atomic when it: fits one work session, touches one concern, can be verified alone, and can be rolled back alone.

## Process
1. Walk the design top-down: contracts → data → logic → UI → tests
2. Cut at natural seams (one endpoint, one migration, one component)
3. Mark dependencies between tasks; order them
4. Tag each task: owner agent + scope (S/M/L)

## Rules
- L-sized task → split again; L is a smell, not a size
- A task named "and" (do X and Y) → two tasks
- Cross-cutting tasks (logging, auth) come before the tasks that need them
- Test tasks are not optional appendixes — they pair with implementation tasks
- Every task declares `files:` — the paths it owns; two tasks writing the same file are sequential or merged, never parallel

## Parallelization Safety Checks
Two tasks may run in parallel ONLY if all checks pass:
1. **File exclusivity** — their `files:` scopes are disjoint
2. **Interface stability** — neither changes a signature/schema/contract the other depends on
3. **Independence** — neither `needs:` the other (directly or transitively)
4. **Contract exclusivity** — they do not write the same versioned contract;
   readers depend on the single writer and wait for explicit source approval
5. **Ownership** — each implementation task has one service/layer and mutates
   only its owned paths/data; cross-service verification is a separate task
Any check fails → serialize (or restructure the split so they pass).

For programs larger than 24 tasks, create bounded feature/workstream plans and
connect them with `program_id`, `workstream_id`, `parent_feature`, and versioned
contract references. Do not raise the cap to create a context-heavy flat plan.

### Cross-workstream dependencies are not machine-readable

`needs:` is resolved by `.ai-kit/scripts/next-task.sh` **within a single tasks.md only**. A task that
depends on another workstream cannot express it in `needs:`, and `next-task.sh` will happily offer
that task as claimable before its real prerequisite exists.

Until the harness models this, state such a dependency **explicitly in the task's acceptance
criteria** — name the blocking workstream and say the task does not start before it closes — and
repeat it in the plan's Approach section. Treat it as a review item, because nothing mechanical
enforces it.

Known limitation, recorded so it is not rediscovered: an agent following `next-task.sh` alone will
start cross-workstream work too early.

## Output
Ordered task list for tasks.md (IDs unique per file; `.ai-kit/scripts/next-task.sh` parses this):
```
- [ ] T<n> <verb + object> | owner: <agent> | scope: S/M/L | needs: T<i>,T<j> or - | files: <owned paths>
```
