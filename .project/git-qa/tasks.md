# Tasks — git-qa

Intent: feature | Size: standard
Goal: Detect and configure Git locally, then use Git worktree state for AI-Kit QA.
Out of scope: commits, staging user files, pushes, global Git configuration, hosted-provider setup
Open questions: none

## Tasks
- [x] T1 Add Git QA command and worktree hygiene mode | owner: backend | scope: M | needs: - | files: .ai/scripts/git-qa.sh,.ai/scripts/check-gates.sh
  - Accept: `status` reports Git/repository/hook state without mutation; `setup --init` initializes only the AI-Kit root and sets local hooks; `check` validates tracked and non-ignored untracked worktree files.
  - Accept: Missing Git or repository is reported as a deterministic skip for read-only QA, while invalid setup arguments and nested repository roots fail closed.
  - Evidence: Shell syntax passes; status reports Git 2.52.0 with no repository; isolated `setup --init` and `check worktree` pass with local hooks.
- [x] T2 Integrate Git QA with doctor and static kit validation | owner: backend | scope: S | needs: T1 | files: .ai/scripts/doctor.sh,.ai/scripts/validate-kit.sh,.ai/ai.yaml
  - Accept: Doctor reports Git QA status, full doctor runs Git worktree QA when available, and static validation requires executable Git QA tooling.
  - Evidence: Static validation passes and doctor reports Git 2.52.0 with a deterministic repository-unavailable skip.
- [x] T3 Add isolated Git QA mechanics tests | owner: qa | scope: M | needs: T1,T2 | files: .ai/tests/run.sh
  - Accept: Temporary-repository tests verify local hook setup, worktree checking, ignored workspace handling, conflict/secret rejection, and no global configuration mutation.
  - Evidence: Full suite passes 21 harness tests and 23 mechanics assertions, including all Git QA success and failure paths.
- [x] T4 Document Git QA workflow | owner: documenter | scope: S | needs: T2 | files: .ai/modules/git.md,.ai/modules/gates.md
  - Accept: Documentation distinguishes optional detection, explicit initialization, local hook activation, worktree QA, and prohibited commit/push/global mutations.
  - Evidence: Git and gates modules document status/setup/check, local-only mutation, worktree coverage, skip semantics, and prohibited operations; static validation passes.
- [x] T5 Configure this checkout for Git QA | owner: qa | scope: S | needs: T3,T4 | files: .git/config
  - Accept: Because Git is installed, this checkout is a Git worktree with local `core.hooksPath=.githooks`; no files are staged or committed by setup.
  - Evidence: Git 2.52.0 initialized the exact AI-Kit root; local hooks are enabled; staged count is zero and no commit was created.
- [x] T6 Remediate first worktree QA findings | owner: qa | scope: S | needs: T5 | files: .ai/tests/run.sh,.project/ai-kit-agent-harness/architecture.md,.project/ai-kit-agent-harness/tasks.md,.project/multi-service-contracts/tasks.md,.project/git-qa/tasks.md
  - Accept: Project execution records no longer reference ephemeral workspace paths, and the secret-scanner fixture still creates a matching runtime token without embedding it in source.
  - Evidence: Project scan has zero ephemeral workspace path references; source scan has zero credential-shaped literals; Git worktree QA passes without weakening G4.

## Standard/Large Tail
- [x] T96 Run full QA and doctor | owner: qa | scope: S | needs: T6 | files: .project/git-qa/tasks.md,.project/git-qa/progress.md
  - Accept: Static validation, mechanics tests, Git QA check, and doctor full all exit zero.
  - Attempt 1: Harness and mechanics passed, then Git worktree QA correctly rejected legacy project records containing ephemeral workspace paths and a credential-shaped literal in the secret-scanner test.
  - Evidence: Attempt 2 passes 21 harness tests, 23 mechanics assertions, static validation, Git worktree QA, and doctor full.
- [x] T7 Prevent Git QA from reading symlink targets | owner: backend | scope: S | needs: T96 | files: .ai/scripts/check-gates.sh,.ai/tests/run.sh
  - Accept: Content hygiene scans never dereference symlinks, and a worktree symlink to an external credential-shaped fixture neither leaks target content nor causes a false secret finding.
  - Evidence: Symlink paths are skipped before text scans; 24 mechanics assertions include an external credential-shaped target with no dereference or output leak.
- [x] T8 Re-run QA after symlink remediation | owner: qa | scope: S | needs: T7 | files: .project/git-qa/tasks.md,.project/git-qa/progress.md
  - Accept: Harness, mechanics, Git worktree QA, and doctor full pass after remediation.
  - Evidence: Doctor full exits zero with 21 harness tests, 24 mechanics assertions, Git worktree QA, hooks enabled, and staged=0.
- [x] T97 Review G3 | owner: reviewer | scope: M | needs: T8 | files: .project/git-qa/tasks.md,.project/git-qa/progress.md
  - Accept: Contract, security, correctness, consistency, and test review has zero major/blocker findings.
  - Review attempt 1: request changes.
  - Major: `.ai/scripts/check-gates.sh:42` and `:51` pass symlink paths to `grep`, which can dereference an external target and print its secret-bearing line; skip symlink content or scan only the stored link target without dereferencing.
  - Review attempt 2: same-session five-pass review confirms the major finding is fixed and finds no remaining major/blocker; it is not represented as independent review.
  - Policy transition: `.ai/config.json` disables independent review; attempt 2 is accepted as the required labeled active-agent five-pass review with zero major/blocker findings.
- [x] T98 Complete release state | owner: release | scope: S | needs: T97 | files: .project/git-qa/plan.md,.project/git-qa/tasks.md,.project/git-qa/progress.md,.project/INDEX.md
  - Accept: Feature and project index are marked done only after G2 and G3 pass.
  - Evidence: All implementation and QA tasks pass; configured active-agent G3 approves; plan, progress, and index are done.
