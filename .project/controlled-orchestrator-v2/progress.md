# Progress — controlled-orchestrator-v2

status: complete
updated: 2026-08-22

## Delivered

- Detached, marker-owned Git workspaces with deterministic binary/new-file patch capture.
- Explicit provider working-directory routing for Codex and Claude.
- Isolated implementation, verification, resumable review, exact-digest promotion, retry, and bounded cleanup.
- Required-by-default CLI isolation with pre-provider Git baseline/cleanliness checks.
- Workspace phase metadata in canonical state, generated task views, and compact status output.
- Guarded `cleanup`; live running/review evidence requires explicit `--abandon`.

## Evidence so far

- Full configured validation: 52 harness integration tests and 24 mechanics assertions passed.
- `doctor.sh --full` passed static structure, skill synchronization, integration/mechanics, and Git QA.
- Explicit worktree Git QA returned `G4 OK` and `GIT_QA OK`; local hooks are `.githooks`.
- Git-backed paths cover text and binary/new files, provider cwd, isolated verification, restart/resume, revise, block, retry, HEAD drift, unstaged promotion, marker tamper, symlink/path escape, missing Git/HEAD, dirty main, and provider-local commit cleanup.
- Provider calls remained offline; fail-before-provider behavior is asserted with a provider method that raises if invoked.

## Operational state

This repository currently has Git metadata but no `HEAD`; every CLI `step`
therefore fails before provider invocation with baseline guidance. The kit does
not create, stage, or commit that baseline. QA can validate mechanics without a
repository baseline because its Git integration tests use disposable fixture
repositories.

## QA result

Every T1–T6 acceptance criterion maps to reproducible unit/integration or CLI
evidence. Invalid, empty/missing, permission/ownership, drift, retry, recovery,
compatibility, and regression paths are covered. No blocker or major defect is
open. The missing root `HEAD` is an intentional, documented precondition for
real dispatch and is directly tested as fail-before-provider behavior.

## Remaining gates

- none

## G3 pass 1 — active-agent — request changes

- Major, `.ai/harness/engine.py:1048`: the already-missing terminal-workspace cleanup path mutates `cleanup_pending` only in memory and returns without `_commit`; reload retains stale canonical status. Persist the transition and add a reload assertion.
- Major, `.project/controlled-orchestrator-v2/architecture.md:91`: architecture says `repair` compares an applied patch after a crash, but runtime repair only restores events/projections and operator docs require manual reconciliation. Align the approved architecture with the implemented fail-closed manual boundary.
- Minor, `.ai/harness/worktrees.py:248`: a regular file at the deterministic worktree-parent path raises untyped `FileExistsError`. Convert parent-directory preparation failures to `WorkspaceError` and cover the conflict.

## T7 remediation

- Durable idempotent cleanup now records `workspace_reconciled`; the regression reloads `state.json` before asserting the cleared flags.
- Filesystem parent/owner preparation converts `OSError` into typed `WorkspaceError`; a regular-file parent fixture passes.
- Architecture and operator docs now agree that the post-apply/pre-state crash window requires manual reconciliation, and docs make the between-task commit/resolve requirement explicit.
- Focused result: 2 tests passed; Python compile and whitespace checks passed.

## G3 pass 2 — active-agent — approve

- Contract: all T1–T7 acceptance criteria and the revised architecture match shipped behavior.
- Security: owned path/marker checks, symlink/path rejection, exact patch digest, unchanged-main preflight, no main-index staging, and explicit abandonment remain fail-closed.
- Correctness: execute/verify/review/promote, restart, retry, drift, cleanup, and typed failure paths have reproducible coverage.
- Consistency: configuration, state validation, projections, CLI, architecture, README, and progress terminology agree.
- Tests: post-remediation `run.sh` passed 52 integration tests and 24 mechanics assertions; explicit Git worktree QA passed.
- Findings: none. Verdict: `approve (active-agent)`; reviewer separation was not claimed.

## Release

- Version: 0.14.0.
- G2: passed after T7 remediation.
- G3: approved under configured active-agent policy.
- Provider routes: remain opt-in; no external provider was called during validation.
- Repository baseline: still user-owned and intentionally absent, so real `step` dispatch remains fail-closed until `HEAD` exists.
