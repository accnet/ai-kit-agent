# Plan — controlled-orchestrator-v2

status: complete
updated: 2026-08-22
source: user continuation

## Goal

Run implementation tasks in isolated Git worktrees and promote only an approved,
verified, scope-valid patch into an unchanged main worktree.

## Approach

Add a standard-library Git workspace manager that requires a repository-local
baseline commit and a clean main worktree, creates a detached per-task worktree,
captures binary patches including new files, and removes only worktrees it owns.
Pass the isolated working directory through the provider request contract. During
execution, snapshot and verify only the isolated tree; persist workspace/base/patch
metadata with the task. Review the isolated result, then require unchanged HEAD
and main-tree cleanliness before applying the reviewed patch without staging or
committing. Configure isolation as required for CLI task execution while keeping
direct unit construction backward-compatible. Cover crash/resume, dirty/baseline,
scope, review-reject, base-drift, new-file, promotion, and cleanup paths offline.

## Risks

- Git worktree/index operations could touch user state → require exact repo root,
  clean main tree, verified HEAD, owned path markers, and never use the main index.
- New files are absent from ordinary `git diff` → stage only inside the disposable
  worktree and export `git diff --cached --binary`.
- Main branch may move during model/review latency → bind patch to base HEAD and
  refuse promotion on any drift or local main-tree mutation.
- Review failure or process crash can leave worktrees → persist metadata for resume
  and provide bounded cleanup that refuses unowned paths.
- The current repository has no HEAD baseline → ship and test the mechanism, but
  actual isolated dispatch fails with guidance until the user creates a baseline
  commit; never create that commit implicitly.

## Out of scope

- Creating, staging, or committing the user's baseline repository.
- Codex App Server or Claude Agent SDK event/session adapters.
- Pre-tool hooks inside provider processes or network/database brokers.
- Parallel worktree scheduling, automatic merge commits, push, or deployment.
- Windows-native Git behavior outside the Python/Git CLI portability tests.

## Open questions

None.

## Task Summary

10 tasks including architecture, implementation, remediation, QA, review, docs, and release.
T4 engine promotion integration is riskiest. Implementation tasks are serialized
because they share the provider/engine test fixture and define one trust boundary.
