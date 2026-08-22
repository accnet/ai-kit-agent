# Tasks — controlled-orchestrator-v1

Intent: feature | Size: standard
Goal: Add durable, traceable, evidence-backed orchestration without enabling paid providers.
Out of scope: SDK adapters, paid calls, worktree sandboxing, multi-workstream scheduling, deployment/database adapters, signed identity
Open questions: none

## Tasks

- [x] T1 Add traceability, run-state, and approval-digest contracts | owner: backend | scope: M | needs: - | files: .ai/harness/models.py,.ai/harness/schemas.py,.ai/harness/policy.py,.ai/harness/projection.py
  - Accept: Plan normalization given requirement IDs rejects missing coverage and unknown task requirement references.
  - Accept: Canonical state validates durable run states and projects requirement coverage plus current run status.
  - Accept: Policy exposes deterministic plan-revision and risky-task action digests whose values change when their protected inputs change.
  - Evidence: Focused offline checks passed for missing/unknown/full coverage, additive state validation, projection inputs, and digest sensitivity; all four modules compile.
- [x] T2 Implement bounded independent verification and lifecycle transitions | owner: backend | scope: M | needs: T1 | files: .ai/harness/engine.py,.ai/harness/cli.py
  - Accept: The harness runs each accepted task verification command without a shell, records command, exit code, duration, and output digest, and refuses success when any command fails or times out.
  - Accept: Start, pause, resume, cancel, and needs-input transitions persist across engine instances and invalid transitions fail closed.
  - Accept: A feature initialized with requirement IDs passes them into plan coverage enforcement.
  - Accept: Newly recorded plan and risky-task approvals persist their exact revision/action digest.
  - Accept: A changed task action digest invalidates a previously recorded risky-task approval.
  - Evidence: Engine/CLI compile and all 32 pre-existing offline harness tests pass after lifecycle, digest, traceability, and verifier integration.
- [x] T3 Add offline regression and failure-path coverage | owner: qa | scope: M | needs: T2 | files: .ai/tests/test_harness.py
  - Accept: Offline tests cover full requirement coverage, unknown references, approval digest mismatch, verification pass/fail/timeout, and lifecycle resume/cancel without invoking Codex or Claude.
  - Accept: All pre-existing harness and mechanics tests continue to pass.
  - Evidence: Five offline regression tests cover traceability, action-digest invalidation, verifier success/failure/timeout, and durable run transitions; all 37 harness tests pass.
- [x] T5 Reject unsafe verification command forms before execution | owner: backend | scope: S | needs: T3 | files: .ai/harness/policy.py,.ai/tests/test_harness.py
  - Accept: Plan normalization rejects shell/eval command forms and unknown executables before a task can be scheduled.
  - Accept: Repository-relative Python/shell test scripts and explicitly supported test/build tools remain accepted.
  - Evidence: Inline Python/shell, curl, and npm publish plans fail normalization; repository scripts and bounded test/build commands pass; all 38 offline tests pass.
- [x] T6 Keep raw verification output out of canonical state | owner: backend | scope: S | needs: T5 | files: .ai/harness/engine.py,.ai/tests/test_harness.py
  - Accept: Verification evidence persists command, exit code, duration, timeout/pass flags, and output digest without persisting stdout or stderr contents.
  - Evidence: Verifier records output byte count and SHA-256 only; regression asserts stdout/stderr are absent; all 38 offline tests pass.
- [x] T4 Document the controlled-orchestrator boundary | owner: documenter | scope: S | needs: T6 | files: .ai/harness/README.md,.project/controlled-orchestrator-v1/progress.md
  - Accept: Documentation distinguishes reasoning plane from control/evidence plane and documents lifecycle, traceability, verification-command safety, and deferred SDK/sandbox work.
  - Evidence: v0.13 operator guide documents the authoritative planes, durable session commands, traceability/digests, verifier safety policy, evidence retention, and explicitly deferred SDK/sandbox boundaries.

## Standard Tail

- [x] T96 Validate full offline QA and Git checks | owner: qa | scope: S | needs: T4 | files: .project/controlled-orchestrator-v1/tasks.md,.project/controlled-orchestrator-v1/progress.md
  - Accept: Full tests, doctor, static validation, and Git worktree QA exit zero without provider invocation.
  - Evidence: 38 harness tests, 24 mechanics assertions, static/projection validation, doctor --full, and Git worktree QA pass; Git reports staged=0 and no provider was invoked.
- [x] T7 Bind verification executables and scripts to trusted paths | owner: backend | scope: S | needs: T96 | files: .ai/harness/policy.py,.ai/harness/engine.py,.ai/tests/test_harness.py
  - Accept: Verification plan normalization rejects path-qualified executable aliases except the current Python interpreter.
  - Accept: Interpreter scripts are regular repository files and any symlink or repository escape fails before subprocess execution.
  - Finding: major — `.ai/harness/policy.py:152` trusts only executable basename and `.ai/harness/engine.py` does not validate interpreter script provenance, allowing `/tmp/python` or a repository symlink to execute outside the intended boundary.
  - Evidence: Three focused tests pass; path-qualified aliases fail normalization, current Python remains accepted, and a linked interpreter script fails with durable policy evidence before subprocess invocation.
- [x] T8 Enforce lifecycle gates on execution and allow direct cancellation | owner: backend | scope: S | needs: T7 | files: .ai/harness/engine.py,.ai/tests/test_harness.py
  - Accept: Paused, needs-input, and cancelled sessions reject task execution before any provider invocation.
  - Accept: A running session can be cancelled directly, while contract approval remains available to resolve a needs-input state.
  - Finding: major — `.ai/harness/engine.py:426` places the step guard inside `approve_contract` instead of `execute_with_provider`, so paused/cancelled work can execute and needs-input contract approval can deadlock.
  - Evidence: Three focused lifecycle/contract tests pass; blocked states never invoke the provider, contract approval resolves needs-input, and running cancellation is terminal.
- [x] T9 Validate canonical requirement identifiers | owner: backend | scope: S | needs: T8 | files: .ai/harness/models.py,.ai/tests/test_harness.py
  - Accept: Canonical state validation rejects requirement IDs outside `R[1-9][0-9]*` and still accepts valid initialized traceability state.
  - Finding: major — `.ai/harness/models.py:155` checks only non-empty strings, so manually corrupted canonical state can bypass the public requirement-ID contract.
  - Evidence: Focused canonical/traceability tests pass; malformed IDs fail both validate_state and save_state while valid R1 state remains accepted.
- [x] T95 Revalidate G3 fixes with full offline QA | owner: qa | scope: S | needs: T7,T8,T9 | files: .project/controlled-orchestrator-v1/tasks.md,.project/controlled-orchestrator-v1/progress.md
  - Accept: Full harness, mechanics, doctor, and Git worktree checks pass after T7-T9 without provider invocation.
  - Evidence: 41 harness tests, 24 mechanics assertions, doctor/static/projection validation, and Git worktree QA pass after T7-T9; staged=0 and provider routes remained unused.
- [x] T97 Review G3 under configured active-agent policy | owner: reviewer | scope: M | needs: T95 | files: .project/controlled-orchestrator-v1/tasks.md,.project/controlled-orchestrator-v1/progress.md
  - Accept: Contract, security, correctness, consistency, and test passes find zero remaining blocker or major issues.
  - Review (active-agent): request changes — three major findings converted to T7-T9.
  - Review (active-agent): approve with release notes — T7-T9 close all prior major findings; contract, security, correctness, consistency, and 41-test evidence passes have zero remaining blocker/major issues. T98 will synchronize the stale plan task count and earlier 38-test progress line.
- [x] T98 Complete release state | owner: release | scope: S | needs: T97 | files: .ai/ai.yaml,.project/controlled-orchestrator-v1/plan.md,.project/controlled-orchestrator-v1/tasks.md,.project/controlled-orchestrator-v1/progress.md,.project/INDEX.md
  - Accept: Version, plan, progress, tasks, session, and index report done only after G2/G3 pass.
  - Evidence: AI-Kit v0.13.0, completed plan/progress/tasks/index/session, go verdict, and rollback trigger are synchronized after 41 tests, 24 mechanics assertions, Git QA, and active-agent G3 approval.
