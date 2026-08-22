# Tasks — ai-kit-agent-harness

Intent: feature | Size: large
Goal: Build a controlled, durable, context-aware LLM harness for Codex and Claude.
Out of scope: hosted queue, GUI, vector DB, concurrent writers, automatic production/database/destructive operations
Open questions: none

## Tasks

- [x] T0 Capture approved harness requirements | owner: researcher | scope: S | needs: - | files: features/ai-kit-agent-harness/brief.md
  - Accept: The brief records LLM reasoning, harness controls, memory, provider safety, and offline-test constraints without changing the completed v0.5 brief.
  - Result: Approved intent is a separate regenerable feature source.
- [x] T1 Define harness architecture and plan | owner: architect | scope: M | needs: T0 | files: .project/ai-kit-agent-harness/architecture.md,.project/ai-kit-agent-harness/decisions.md,.project/ai-kit-agent-harness/plan.md,.project/ai-kit-agent-harness/tasks.md,.project/INDEX.md
  - Accept: Components, transitions, provider contracts, persistence, safety, risks, dependencies, and binary acceptance criteria are explicit with no blockers.
  - Result: G1 architecture and task contracts are ready.
- [x] T2 Implement state, storage, events, locks, and projections | owner: backend | scope: M | needs: T1 | files: .ai/harness/models.py,.ai/harness/store.py,.ai/harness/projection.py,.ai/harness/__init__.py
  - Accept: Valid feature state writes atomically, events append as JSONL, an exclusive lock rejects a second writer, and reload reproduces state.
  - Accept: Projections deterministically include status, dependencies, acceptance, attempts, evidence, and verdicts.
  - Accept: Invalid feature IDs and paths outside the repository fail before write.
  - Result: Python smoke verification passed atomic round-trip, JSONL event append, deterministic projection, exclusive double-lock rejection, and invalid-feature rejection.
- [x] T3 Implement memory and bounded context retrieval | owner: backend | scope: M | needs: T2 | files: .ai/harness/memory.py
  - Accept: Working, episodic, and semantic entries append and retrieve by deterministic relevance within a character budget.
  - Accept: Retrieved entries include provenance/hash and changed or missing sources report stale.
  - Result: Smoke verification passed all three memory types, relevance ranking, a 512-character hard budget, SHA-256 provenance, and changed-source staleness.
- [x] T4 Implement structured provider adapters | owner: backend | scope: M | needs: T2 | files: .ai/harness/providers.py,.ai/harness/schemas.py
  - Accept: Scripted responses validate without an external process.
  - Accept: Codex planning/review is read-only and Claude planning/review uses plan mode; neither command has a bypass flag.
  - Accept: Invalid JSON, timeout, non-zero exit, oversized output, or schema mismatch fails closed.
  - Result: Scripted schema validation and safe Codex/Claude command previews passed; typed failure paths cover malformed/schema-invalid/oversized output, timeout, missing executable, and non-zero exit.
- [x] T5 Implement policy, scheduler, and engine transitions | owner: backend | scope: M | needs: T3,T4 | files: .ai/harness/policy.py,.ai/harness/engine.py
  - Accept: Valid bounded acyclic plans are accepted and duplicate IDs, bad dependencies, absent acceptance, disallowed scopes, or cycles are rejected.
  - Accept: Only ready approved tasks schedule; risky unapproved tasks block; three failures escalate.
  - Accept: Evidence enters review, approval closes, revision retries/replans, and each transition persists an event/projection.
  - Result: End-to-end smoke passed cycle rejection, dependency scheduling, risk approval blocking, evidence-to-review, approval completion, three-attempt escalation, completed-task-preserving replan, and durable resume.
- [x] T6 Add CLI and provider configuration | owner: backend | scope: M | needs: T5 | files: .ai/harness/cli.py,.ai/harness/config.json,.ai/scripts/harness.sh,.ai/ai.yaml,.ai/models.yaml
  - Accept: init, plan, next, step, review, approve, remember, context, and status expose the engine without implicit provider calls.
  - Accept: Help/status work offline; unsafe or incomplete commands fail with actionable errors.
  - Result: CLI smoke completed init → scripted plan → next → scripted step → scripted review → complete entirely offline; missing scripted response failed with exit 2.
- [x] T7 Add offline integration and failure tests | owner: qa | scope: M | needs: T6 | files: .ai/tests/test_harness.py,.ai/tests/fixtures/harness/**,.ai/tests/run.sh,.ai/scripts/validate-kit.sh,.ai/scripts/doctor.sh,.ai/scripts/harness.sh,.gitignore
  - Accept: Tests cover lifecycle, scheduling, approval, evidence, review, replan/resume, projections, stale memory, locks, cycles, scope, retry escalation, and provider commands.
  - Accept: Tests prove no Codex/Claude subprocess executes and `bash .ai/tests/run.sh` passes.
  - Plan note: Added `.gitignore` and the harness wrapper after QA found Python bytecode would otherwise enter text-only validation scope.
  - Result: 9 offline harness integration/failure tests pass; the full legacy suite passes 14 mechanics assertions and static validation.
- [x] T10 Enforce plan and independent-review approval contracts | owner: backend | scope: M | needs: T7 | files: .ai/harness/models.py,.ai/harness/policy.py,.ai/harness/engine.py,.ai/harness/cli.py,.ai/harness/projection.py
  - Accept: A large initial plan or replan cannot schedule until an explicit plan-revision approval is recorded.
  - Accept: Independent review rejects the task's implementation provider and approval verifies every acceptance criterion was checked.
  - Finding: Major — `.ai/harness/engine.py:116-121,244-292` allowed immediate large-plan scheduling and same-provider/empty-evidence approval.
  - Result: Large revisions now require `approve-plan`; independent review rejects the implementer provider and incomplete acceptance-evidence checks.
- [x] T11 Verify actual repository mutations and scope roots | owner: backend | scope: M | needs: T10 | files: .ai/harness/policy.py,.ai/harness/engine.py
  - Accept: Files created, modified, or deleted during a provider call are derived from before/after repository snapshots and every actual path must match task scope.
  - Accept: Scope roots resolving through a symlink outside the repository and single-star patterns crossing directories are rejected.
  - Finding: Major — `.ai/harness/policy.py:180-194` trusted provider-reported changed files, permitting undeclared writes to escape validation.
  - Result: SHA-256 before/after snapshots verify actual creates/modifies/deletes; segment-aware globs and symlink/disallowed roots fail closed, and corrupted control state is restored before failure recording.
- [x] T12 Recover stale locks and reconcile transition artifacts | owner: backend | scope: M | needs: T11 | files: .ai/harness/models.py,.ai/harness/store.py,.ai/harness/engine.py,.ai/harness/cli.py
  - Accept: A dead-owner lock is recoverable without overriding a live owner, while a second live writer remains rejected.
  - Accept: State records an event sequence and loading status identifies missing event/projection artifacts for deterministic repair.
  - Finding: Major — `.ai/harness/store.py:194-215` left a crashed process's lock permanently blocking resume; transition artifacts had no reconciliation signal.
  - Result: Live PID locks remain exclusive, dead PID locks recover, canonical state validates structurally, event sequences expose gaps, and `status`/`repair` reconcile final events and projections.
- [x] T13 Add regression tests for G3 findings | owner: qa | scope: M | needs: T12 | files: .ai/tests/test_harness.py
  - Accept: Tests fail on same-provider review, unapproved large plans, incomplete review evidence, undeclared actual writes, symlink escapes, cross-directory star matches, live/stale locks, and transition reconciliation.
  - Result: 12 harness tests pass, including all first-review regressions; full suite remains 14 mechanics assertions.
- [x] T8 Review complete harness (G3) | owner: reviewer | scope: M | needs: T13 | files: -
  - Accept: Contract, security, correctness, consistency, and tests report zero blocker or major findings; findings become tasks.
  - Result: Approve with notes after T10-T13; zero blocker/major findings remain. Contract, security, correctness, consistency, 12 harness tests, 14 legacy mechanics assertions, provider command safety, and static validation passed. Review was a separate reviewer-role pass in this Codex session, not an external Claude call.
- [x] T9 Finalize docs and project state | owner: documenter | scope: S | needs: T8 | files: AGENTS.md,.ai/harness/README.md,.ai/modules/gates.md,.ai/modules/context.md,.ai/knowledge/decisions.md,.project/ai-kit-agent-harness/architecture.md,.project/ai-kit-agent-harness/plan.md,.project/ai-kit-agent-harness/progress.md,.project/ai-kit-agent-harness/tasks.md,.project/INDEX.md
  - Accept: Guidance distinguishes reasoning/control, commands are documented, evidence is recorded, INDEX is done, and session has no stale next action.
  - Result: Operator README, canonical rules/modules, architecture, progress, durable decision, INDEX, and session state match v0.6; final doctor pass includes 12 harness tests and 14 mechanics assertions.

## Review verdict

Approve with notes — zero blocker or major findings remain after T10-T13. No
live/billed provider call was made; Codex/Claude argv and schema boundaries were
verified offline. Review was a reviewer-role pass in this Codex session rather
than an external Claude review.
