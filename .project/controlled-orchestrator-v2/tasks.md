# Tasks — controlled-orchestrator-v2

Intent: feature | Size: standard
Goal: Isolate provider writes and promote only reviewed, verified patches.
Out of scope: baseline commits, SDK adapters, provider hooks, parallel scheduling, pushes/deploys
Open questions: none

## Tasks

- [x] T1 Define isolated-worktree architecture and trust boundaries | owner: architect | scope: S | needs: - | files: .project/controlled-orchestrator-v2/architecture.md,.project/controlled-orchestrator-v2/decisions.md
  - Accept: Design defines ownership, create/execute/verify/review/promote/cleanup flow, failure recovery, main-tree invariants, and rejected alternatives without changing code.
  - Evidence: Architecture fixes the detached create→execute→verify→review→promote flow, ten trust invariants, crash/base-drift failure behavior, component ownership, rejected alternatives, and rollback without application-code changes.
- [x] T2 Implement fail-closed Git workspace manager | owner: backend | scope: M | needs: T1 | files: .ai/harness/worktrees.py,.ai/tests/test_harness.py
  - Accept: A clean repository with HEAD creates an owned detached worktree and exports a deterministic binary patch containing modified and new files.
  - Accept: Missing Git/HEAD, dirty main tree, base drift, path escape, symlinked workspace root, or unowned cleanup fails without mutating the main worktree.
  - Accept: Promotion runs check-before-apply, leaves changes unstaged, and cleanup removes only the owned disposable worktree.
  - Evidence: Four focused tests pass after one recorded fixture correction; detached create, deterministic binary/new-file capture, unstaged promotion, owned cleanup, missing Git/HEAD, dirty tree, base drift, parent symlink, path escape, and marker tamper all fail or succeed as specified.
- [x] T3 Route provider requests to an explicit working directory | owner: backend | scope: S | needs: T2 | files: .ai/harness/providers.py,.ai/tests/test_harness.py
  - Accept: Codex/Claude subprocess cwd and Codex `--cd` use the request working directory while planning/review defaults remain backward-compatible.
  - Accept: A missing, non-directory, or symlinked working directory is rejected before provider subprocess execution.
  - Evidence: Four focused provider tests pass; explicit directories are normalized, missing/file/symlink paths fail before execution, Codex `--cd` and both provider subprocess cwd values use the isolated root, and default routing remains repository-root compatible.
- [x] T4 Integrate isolated execution, verification, review, and promotion | owner: backend | scope: M | needs: T3 | files: .ai/harness/engine.py,.ai/harness/models.py,.ai/harness/projection.py,.ai/tests/test_harness.py
  - Accept: With isolation required, implementation and verification mutate only the detached worktree and canonical state records base/workspace/patch digests.
  - Accept: Review observes the isolated result; approve promotes the exact reviewed patch only when main HEAD/tree remain unchanged, while revise/block leaves main untouched.
  - Accept: Resume can review an existing owned worktree, and retries discard only the previous owned workspace before creating a fresh one.
  - Evidence: The 49-test harness suite passed plus focused recovery coverage; Git-backed integration proves verification and review run in the detached root, canonical base/patch metadata survives engine restart, approve applies the exact patch unstaged, revise/block discard without main mutation, retry uses a new owner record, HEAD drift blocks promotion, and cleanup remains bounded even after a provider-local commit.
- [x] T5 Add fail-closed isolation configuration and CLI lifecycle | owner: backend | scope: S | needs: T4 | files: .ai/config.json,.ai/harness/cli.py,.ai/harness/engine.py,.ai/harness/README.md,.ai/tests/test_harness.py
  - Accept: CLI implementation uses required isolation by default and reports actionable missing-baseline/dirty-tree errors without calling a provider.
  - Accept: Status exposes workspace phase and a cleanup command refuses running/review workspaces unless explicitly abandoned.
  - Evidence: Focused config/CLI tests pass; required isolation is schema-validated and wired into the CLI engine, no-HEAD and dirty-main cases return actionable errors before a scripted provider can run, status exposes bounded workspace metadata, and cleanup requires explicit `--abandon` for running/review evidence.
- [x] T6 Complete regression coverage and operator documentation | owner: documenter | scope: S | needs: T5 | files: .ai/harness/README.md,.project/controlled-orchestrator-v2/progress.md
  - Accept: Documentation explains baseline setup, isolation guarantees, patch promotion, recovery/cleanup, limitations, and confirms provider routes remain opt-in.
  - Evidence: v0.14 operator docs now cover reviewed baseline creation, detached execution/verification/review, unstaged exact-patch promotion, status and guarded abandonment, resume/base-drift behavior, the post-apply crash limitation, OS-sandbox limits, and unchanged opt-in provider routing; progress records delivered behavior and pending gates.
- [x] T7 Resolve G3 recovery and typed-boundary findings | owner: backend | scope: S | needs: T6 | files: .ai/harness/engine.py,.ai/harness/worktrees.py,.ai/harness/README.md,.ai/tests/test_harness.py,.project/controlled-orchestrator-v2/architecture.md,.project/controlled-orchestrator-v2/progress.md
  - Accept: Idempotent cleanup of an already-missing promoted/discarded workspace durably clears cleanup state and is verified by reloading canonical state.
  - Accept: Worktree-parent filesystem conflicts return a typed `WorkspaceError`, and architecture/operator recovery claims match the implemented manual post-apply reconciliation boundary.
  - Accept: Operator docs state that promoted unstaged changes must be committed or otherwise resolved before the next isolated task can start.
  - Evidence: Two focused regression tests plus compile/diff checks pass; terminal missing-workspace cleanup now commits `workspace_reconciled` and survives reload, regular-file parent conflicts are typed, architecture and README consistently require manual post-apply reconciliation, and docs state the next task remains blocked until promoted main changes are resolved.

## Standard Tail

- [x] T96 Validate full offline QA and Git checks | owner: qa | scope: S | needs: T6 | files: .project/controlled-orchestrator-v2/tasks.md,.project/controlled-orchestrator-v2/progress.md
  - Accept: Full harness, mechanics, doctor, and Git worktree checks pass without provider invocation.
  - Evidence: `bash .ai/tests/run.sh` passed 52 harness tests and 24 mechanics assertions; `bash .ai/scripts/doctor.sh --full` passed static validation, synchronized projections, the same suites, and final Git QA; explicit `bash .ai/scripts/git-qa.sh check worktree` returned G4/GIT_QA OK. No external Codex/Claude CLI was invoked; provider behavior used offline scripted doubles. Local hooks resolve to `.githooks`; missing repository HEAD remains a visible expected dispatch blocker, not a QA failure.
- [x] T97 Review G3 under configured active-agent policy | owner: reviewer | scope: M | needs: T96,T7 | files: .project/controlled-orchestrator-v2/tasks.md,.project/controlled-orchestrator-v2/progress.md
  - Accept: Contract, security, correctness, consistency, and test passes find zero remaining blocker or major issues.
  - Evidence: G3 pass 2 verdict `approve (active-agent)` under `independent_enabled=false`; contract, security, correctness, consistency, and tests were reviewed after T7 and found zero blocker, major, or minor findings. Post-remediation validation passed 52 integration tests, 24 mechanics assertions, and explicit Git worktree QA.
- [x] T98 Complete v0.14 release state | owner: release | scope: S | needs: T97 | files: .ai/ai.yaml,.project/controlled-orchestrator-v2/plan.md,.project/controlled-orchestrator-v2/tasks.md,.project/controlled-orchestrator-v2/progress.md,.project/INDEX.md
  - Accept: Version, plan, progress, tasks, session, and index report done only after G2/G3 pass.
  - Evidence: After post-remediation G2 and active-agent G3 approval, kit version is 0.14.0 and plan, task ledger, progress, session, and project index are synchronized to complete/done.
