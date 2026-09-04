---
name: orchestration
description: Coordinator protocol for Codex IDE native workers.
---

# Native Worker Orchestration

The `ide-native-workers` mode is declarative. Codex IDE owns scheduling, worker creation, cancellation,
and worktree provisioning. AI-Kit owns validation and task-state transitions only.

## Coordinator checklist

1. Read and validate `.ai-kit/config.json` orchestration policy.
2. Run `python3 .ai-kit/scripts/dag.py <feature> --json` and require `valid=true`.
3. Reject missing dependencies, cycles, ambiguous/overlapping `files:` scopes, and a ready set larger
   than `max_workers` for one dispatch batch.
4. Allocate one IDE worker and isolated worktree per selected task.
5. Validate the worker manifest with `worker_manifest.py` before accepting a result.
6. Use `orchestrate.py` for coordinator-owned claim/completion transitions under its feature lock.
7. Start QA/G3 only after all implementation dependencies in the barrier are terminal.

## Worker prohibitions

Workers receive one task and declared paths. They do not edit `tasks.md`, claim or complete tasks,
modify coordinator leases, commit, push, create workers, or call providers/APIs. A worker reports
evidence and leaves its patch in the IDE-supplied worktree for coordinator validation.

## Failure behavior

Validation is fail-closed. The coordinator must stop dispatch and surface a typed error for an invalid
contract, malformed DAG, scope overlap, stale lease, shared/dirty worktree, undeclared file change,
or barrier violation. No automatic worker replacement or provider fallback is attempted.
