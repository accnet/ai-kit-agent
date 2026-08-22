---
name: gates
description: Gates G1–G5, retry policy, and execution log. Load for planning, mutation, review, commit, or destructive-operation decisions.
---

# Module: Gates

## Purpose
Turn the kit's rules from honor-system into enforced checkpoints. Every gate defines: trigger, check, and failure action. A failed gate blocks progress — it is never advisory.

## When to Load
Load when planning or changing files, closing/reviewing a task, preparing a commit, or considering a destructive action. The compact always-on boundaries are already in AGENTS.md; read-only answers do not need this full module.

## Gate Definitions

### G1 — Plan Gate (enforces planning_first)
- **Trigger**: before the first code/file change of a feature
- **Check**: `.project/<feature>/tasks.md` exists, has ≥1 task with acceptance criteria, no unresolved blocker questions. Trivial-sized work (per intent-analysis Sizing Gate) satisfies G1 with the inline fast-path checklist instead — **except any database change (schema OR data), which is never trivial and always requires a full `tasks.md` or a `features/<feature>/` (rules.yaml: `db_changes_require_plan`)**
- **Failure action**: stop; run the planning module; do not touch code
- **Harness enforcement**: a `large` canonical plan enters `plan_pending_approval`; no task schedules until `approve-plan` records approval for that exact revision

### G2 — Task-Complete Gate (enforces acceptance criteria)
- **Trigger**: agent wants to mark a tasks.md task `[x]`
- **Check**: task's acceptance criteria demonstrably met; tests relevant to the task pass; lint/typecheck clean on changed files
- **Failure action**: task stays `[ ]`; failure noted under the task; fix before proceeding
- **Harness enforcement**: provider-reported evidence is schema-checked, repository files are hashed before/after execution, and every actual mutation must fit the declared task scope

### G3 — Review Gate (enforces review_required)
- **Trigger**: all implementation tasks of a feature checked
- **Check**: review verdict exists per `.ai/modules/review.md` with zero blockers; every checklist item of the owning agent's contract confirmed. QA and G3 remain mandatory. Reviewer separation follows `.ai/config.json`: `review.independent_enabled=false` permits a labeled active-agent review, while `true` makes independent review the harness default.
- **Failure action**: feature stays open; findings become tasks in tasks.md
- **Harness enforcement**: the harness rejects an `independent` policy while the kit flag is false. When enabled and selected, `independent` rejects the implementation provider as reviewer. Every selected review policy requires all acceptance criteria in `evidence_checked`.

### G4 — Commit Gate (enforces hygiene)
- **Trigger**: before any commit
- **Check**: no `.workspace/` paths referenced in committed files; no secrets/credentials; diff maps to a tasks.md task; tests pass
- **Failure action**: commit aborted; violation reported

### G5 — Destructive-Op Gate (enforces user approval)
- **Trigger**: dropping data, irreversible migration, force-push shared branch, production deploy
- **Check**: explicit user approval recorded in the conversation for THIS specific operation
- **Failure action**: operation not executed; ask the user

### C1-C6 — Multi-Service Contract Gates

When a plan declares `services` or `contracts`, load `contracts.md`. C1-C6 add
service/data ownership, explicit source approval and hashing, compatibility
metadata, database safety, integration evidence, and release metadata. They do
not replace G1-G5. The harness mechanically blocks ownership violations, draft
or stale contracts, multiple writers, missing consumer dependencies, and data
tasks outside their owner. Review and host deployment controls remain
authoritative for integration and release behavior not observable locally.

## Enforcement Mapping

| Gate | Repository-level behavior that ships | Optional tool-native early feedback |
|---|---|---|
| G1 | Skills verify plans; harness-managed large revisions mechanically require `approve-plan` | Pre-edit hook tied to a project-specific task resolver |
| G2 | CI runs `test_command`; harness records structured evidence and verifies actual mutation scope | Post-edit or Stop test hook |
| G3 | `ai-kit-review` defines five passes; harness enforces configured provider separation and evidence coverage | Active agent by default; independent reviewer when manually enabled |
| G4 | `.githooks/pre-commit` and CI run `.ai/scripts/check-gates.sh` | Pre-commit tool hook |
| G5 | explicit approval requirement; host branch/environment protection remains authoritative | Permission deny-list |

Activation (once per clone): `bash .ai/scripts/git-qa.sh setup`. When the user
explicitly wants a new repository at the AI-Kit root, use `setup --init`.

Notes:
- G4 hygiene is mechanical in a generic checkout, and CI mechanically runs the configured test command. Task-to-diff mapping, G1–G3 workflow judgment, and G5 authorization still require task-aware state or host controls. Do not describe them as hard enforcement without a project-specific adapter.
- Turning independent review off does not waive QA, acceptance evidence, the five review passes, or G3. It changes reviewer separation only.
- `quality.qa` and `quality.review` choose who performs an enabled quality route; they never waive G2/G3. Review CLI selection is separate from `review.independent_enabled` and does not by itself establish reviewer independence.
- `.ai/scripts/git-qa.sh check worktree` extends G4 to non-ignored untracked files and merge/whitespace state without staging or committing them. Git absence is an explicit skip, not a false pass claiming repository checks ran.
- Repository checks are canonical regardless of which IDE/agent produced the code. Tool-native hooks may move the same feedback earlier.
- `.ai/scripts/next-task.sh <feature>` gives any agent the claimable tasks (deps resolved) — the mechanical half of task orchestration.
- `.ai/scripts/doctor.sh --full` validates kit structure and mechanics; CI executes the same configured test command.

## Retry Policy (task fails G2)
Attempts are tracked on the task line: `| attempts: <n>` (rendered by `.ai/scripts/state.sh`). On each G2 failure the owning agent:
1. Notes the failure under the task and logs it: `.ai/scripts/log-event.sh retry <feature> T<n> <instance> "<why it failed>"`.
2. Increments `attempts`, fixes the cause, and re-runs G2 — the task never gets marked `[x]` until G2 passes.
3. After **3** failed attempts, stops and escalates: logs `escalated`, leaves the task `[ ]`, and asks the user for direction. Silent retries are a violation — every attempt stays visible in `tasks.md` and the log.

## Execution Log
Legacy workflows use `.project/log.jsonl` as derived activity history and `tasks.md` as state. Harness-managed features use `.project/<feature>/state.json` as canonical state plus sequenced `events.jsonl`; generated Markdown is never parsed back. `status` reports missing artifacts and `repair` reconstructs a missing final event or projection.

## Rules
- Gates are ordered: G1 before any code, G2 per task, G3 per feature, G4 per commit, G5 whenever triggered
- Multi-service planning applies C1-C4 before scheduling; G2/G3 reviewers verify the declared C5-C6 evidence before completion
- A gate may not be waived by an agent; only the user can waive, explicitly, per instance
- Gate failures are recorded in tasks.md — silent retries hide systemic problems

## Output
Gate results visible in tasks.md (task notes) and review verdicts; violations always surfaced to the user.
