# Progress — controlled-orchestrator-v1

status: done
updated: 2026-08-22

## Implemented

- Optional requirement registry with mechanical task coverage enforcement.
- Durable run IDs and start/pause/resume/needs-input/cancel lifecycle states.
- Exact plan-revision and risky-task action digests on new approvals.
- Independent task verification using accepted argv commands, no shell, timeout,
  repository mutation detection, and durable evidence metadata.
- Verification preflight rejects inline interpreters, unknown executables, and
  unsafe package actions.
- Raw verifier stdout/stderr are excluded from canonical state; only byte count
  and SHA-256 output digest are retained.

## Validation

- 41 offline harness tests pass, including coverage gaps, unknown requirement
  references, approval invalidation, verification pass/fail/timeout, safe command
  forms, and lifecycle recovery through a fresh engine instance.
- No Codex or Claude provider was invoked.

## G3 review — request changes

Policy: active-agent (`review.independent_enabled=false`, quality Review route
disabled). Contract, security, correctness, consistency, and test passes ran.

- Major: executable basename matching accepts path-qualified aliases and
  interpreter scripts can traverse repository symlinks (T7).
- Major: the paused/cancelled execution guard is attached to contract approval,
  not task execution; direct running cancellation is unavailable (T8).
- Major: canonical state validation accepts malformed requirement IDs (T9).

No provider review was invoked. G3 remains open until the findings are fixed and
the full five-pass review is repeated.

## Post-finding QA

- T7 rejects executable aliases and linked interpreter scripts before spawn.
- T8 blocks execution in paused/needs-input/cancelled states, keeps contract
  approval available, and supports direct running cancellation.
- T9 rejects malformed requirement identifiers in canonical state and store.
- Full QA now passes 41 harness tests and 24 mechanics assertions plus doctor,
  static/projection, and Git worktree checks; no provider was invoked.

## G3 review — approve

Policy: active-agent. The repeated contract, security, correctness, consistency,
and test passes find zero remaining blocker or major issues. T7-T9 close all
initial findings. Minor release-only notes are the stale plan task count and the
earlier 38-test summary; T98 owns both files and will synchronize them.

## Full QA

- `bash .ai/tests/run.sh`: 41 harness tests and 24 mechanics assertions pass.
- `bash .ai/scripts/doctor.sh --full`: static, projections, harness, mechanics,
  and Git worktree checks pass.
- `bash .ai/scripts/git-qa.sh check worktree`: passes with staged=0.
- Provider routes remained disabled and no Codex/Claude executable was invoked.

## Deferred

Provider SDK/event adapters, pre-tool provider interception, per-task isolated
worktrees and patch promotion, signed identities/audit chains, semantic API diff,
deployment/database adapters, and multi-workstream scheduling.

## Release

- Version: 0.13.0.
- Verdict: go for local kit use; G2 and active-agent G3 pass.
- Deployment: none performed; provider routes remain disabled by default.
- Rollback trigger: any lifecycle scheduling, verifier provenance, or state-load
  regression. Restore the v0.12 harness files and version metadata together;
  existing feature intent and application data require no migration or rollback.
