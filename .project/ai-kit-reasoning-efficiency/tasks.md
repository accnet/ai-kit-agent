# Tasks — ai-kit-reasoning-efficiency

Intent: refactor | Size: standard
Goal: Remove measurable reasoning tax while retaining deterministic harness control.
Out of scope: paid model calls, enabling routes, model identity changes, task-cap changes
Open questions: none

## Tasks

- [x] T1 Optimize harness context and provider execution profiles | owner: backend | scope: M | needs: - | files: .ai/harness/memory.py,.ai/harness/engine.py,.ai/harness/providers.py,.ai/harness/cli.py,.ai/harness/config.json
  - Accept: Native Codex and Claude requests exclude the project `AGENTS.md` copy from harness memory while scripted/custom providers retain it.
  - Accept: A pinned source that does not fit the reserved source share is deferred whole and only truncated if it cannot fit the final total budget.
  - Accept: Every execution prompt names exactly one selected AI-Kit workflow and owner-contract path derived from task ownership and contract writes.
  - Accept: Codex and Claude commands receive validated per-role reasoning effort; Claude review remains in plan mode and can run non-mutating Bash verification.
  - Evidence: Native adapters advertise project-instruction discovery; context exclusion/whole-source deferral, deterministic workflow selection, portable effort validation, and role-specific Claude tools are implemented.
- [x] T2 Add offline regression coverage | owner: backend | scope: M | needs: T1 | files: .ai/tests/test_harness.py
  - Accept: Offline tests prove native instruction de-duplication, whole-source deferral, specialist workflow routing, effort flags, and reviewer tool boundaries without invoking either CLI.
  - Accept: Existing harness failure, schema, routing, state, memory, and contract tests continue to pass.
  - Evidence: Four new offline regression tests pass alongside all prior tests; suite total is 31 and subprocess CLI invocation remains mocked/absent.
- [x] T3 Document configuration and release the optimization | owner: documenter | scope: S | needs: T1,T2 | files: .ai/harness/README.md,.ai/modules/context.md,.ai/ai.yaml,.project/ai-kit-reasoning-efficiency/plan.md,.project/ai-kit-reasoning-efficiency/progress.md
  - Accept: Documentation explains provider-aware project instructions, task-specific workflow routing, source truncation reporting, review Bash boundary, and per-role effort configuration.
  - Accept: AI-Kit version advances and progress records exact offline validation evidence.
  - Evidence: v0.12 documentation covers native de-duplication, source telemetry, owner workflow routing, Claude review Bash boundary, effort configuration, and measured before/after context.
- [x] T4 Enforce repository immutability during provider review | owner: backend | scope: S | needs: T2 | files: .ai/harness/engine.py,.ai/tests/test_harness.py
  - Accept: Any file create, modify, delete, or symlink change made during review causes a policy failure and no review verdict is recorded.
  - Accept: An immutable reviewer still completes the existing review lifecycle.
  - Finding: major — Claude review gained Bash verification but relied only on plan mode and prompt instructions, while `review_with_provider` did not mechanically attribute mutations.
  - Evidence: Review snapshots now reject all changed paths before recording a verdict; the mutation regression and existing successful review lifecycles pass.

## Standard Tail

- [x] T96 Validate full offline QA and Git checks | owner: qa | scope: S | needs: T3,T4 | files: .project/ai-kit-reasoning-efficiency/tasks.md,.project/ai-kit-reasoning-efficiency/progress.md
  - Accept: Full tests, static validation, doctor, and Git worktree QA exit zero without provider invocation.
  - Evidence: Doctor full passes 32 offline harness tests, 24 mechanics assertions, static validation, synchronized skill projections, and Git worktree QA with staged=0.
- [x] T97 Review G3 under configured active-agent policy | owner: reviewer | scope: M | needs: T96 | files: .project/ai-kit-reasoning-efficiency/tasks.md,.project/ai-kit-reasoning-efficiency/progress.md
  - Accept: Contract, security, correctness, consistency, and test passes find zero remaining blocker or major issues.
  - Evidence: Active-agent five-pass review approves with zero remaining findings after T4 mechanically closed the review-mutation gap.
- [x] T98 Complete release state | owner: release | scope: S | needs: T97 | files: .project/ai-kit-reasoning-efficiency/plan.md,.project/ai-kit-reasoning-efficiency/tasks.md,.project/ai-kit-reasoning-efficiency/progress.md,.project/INDEX.md
  - Accept: Plan, progress, tasks, session, and index report done only after G2/G3 pass.
  - Evidence: v0.12.0 feature state, index, progress, tasks, and session are synchronized after G2/G3 approval.
