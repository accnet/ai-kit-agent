---
name: ai-kit-migrate-data
description: Implement and verify a planned database schema or data migration with rollback, batching, integrity, and environment safeguards. Use for migrations, DDL, backfills, seeds, or bulk data changes; not for ordinary application code or read-only query analysis.
---

# AI-Kit Migrate Data

Produce a reversible, observable migration without inferring permission to
modify real data or high-impact environments.

## Workflow

1. Verify full G1 state; database schema or data changes never use the trivial
   path. The task must be Database-owned, declare exact files and data entities,
   and carry database risk. Stop and replan if any element is missing.
2. Load `.ai/agents/database.md`, `.ai/modules/database.md`,
   `.ai/modules/gates.md`, existing migrations/schema/query patterns, and
   `.ai/modules/contracts.md` when ownership or cross-service data contracts are
   involved.
3. Identify the target environment, data owner, volume, lock and availability
   risk, compatibility window, backup or recovery point, reconciliation method,
   rollout order, and rollback trigger. Never infer credentials, environment,
   or authorization from tool availability.
4. Implement forward and rollback migrations plus deterministic tests. Use
   expand/backfill/switch/contract ordering, bounded batches, resumable progress,
   and database constraints where applicable.
5. Run static checks and migrations only against an explicitly identified local
   or disposable test database within task scope. Record row counts, checksums,
   constraint checks, or other observable evidence appropriate to the change.
6. Before any shared, staging, production, destructive, irreversible, or
   hard-to-recover operation, stop and obtain explicit user approval for that
   exact environment and operation. A migration artifact is not authorization
   to apply it.
7. Close G2 only when forward, rollback, integrity, performance-risk, and
   reconciliation criteria pass. If rollback is impossible, keep the task
   blocked until the user accepts the documented recovery plan.

## Boundaries

- Do not mix unrelated application refactors into a migration task.
- Do not run unbounded updates, silently retry partial writes, or claim remote
  success from local evidence.
- If the harness already selected this worker for one migration task, execute
  directly and do not recursively dispatch another task.

## Output

Lead with artifacts created, environments actually touched, forward/rollback
and reconciliation evidence, batching/lock impact, approvals still required,
and the next safe transition.
