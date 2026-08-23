# Tasks — portable-installer

Intent: feature | Size: standard
Goal: Bootstrap AI-Kit from a copied `.ai/` directory without uncontrolled writes.
Out of scope: baseline commits, provider calls, dependency installation, forced overwrite, PowerShell
Open questions: none

## Tasks

- [x] T1 Define installer architecture and mutation boundaries | owner: architect | scope: S | needs: - | files: .project/portable-installer/architecture.md,.project/portable-installer/decisions.md
  - Accept: Design defines root discovery, managed assets, preflight/apply/check flow, Git behavior, repeat-run semantics, failure recovery, and rejected alternatives without changing runtime code.
  - Evidence: Architecture records self-location root discovery, template ownership, preflight-before-apply, exact-project Git QA setup, repeatability/conflict rules, recovery, rollback, and rejected alternatives.
- [x] T2 Implement self-contained portable installer and templates | owner: backend | scope: M | needs: T1 | files: .ai/install/,.ai/scripts/validate-kit.sh
  - Accept: Given a target containing only a copied `.ai/`, `bash .ai/install/install.sh` creates required root integration files/directories and synchronized Codex/Claude skill projections.
  - Accept: With Git available, install initializes only the target repository and configures local `.githooks`; `--no-git` skips Git mutation, and neither path stages or commits files.
  - Accept: A second unchanged install succeeds, while a conflicting managed file or symlink fails during preflight before any other managed destination is written.
  - Evidence: Focused Bash syntax/static validation and three disposable manual fixtures pass; copied-only installation creates root assets and synchronized projections, no-Git and Git-local modes remain unstaged/uncommitted, repeat check succeeds, and a differing AGENTS.md stops before CLAUDE.md is written.
- [x] T3 Add disposable-project installer regression coverage | owner: qa | scope: M | needs: T2 | files: .ai/tests/test_install.sh,.ai/tests/run.sh
  - Accept: Tests copy only `.ai/` into temporary empty targets and prove first install, repeat install, `--check`, no-Git mode, local Git setup, no commit, conflict preflight, and path-location safeguards.
  - Accept: Tests leave the source repository, global Git configuration, and paths outside each fixture unchanged.
  - Evidence: `bash .ai/tests/test_install.sh` passes 8 acceptance-derived groups covering copied-only bootstrap, read-only check/repeatability, missing state, differing file, destination symlink, manifest escape, invalid location, and Git-local setup. Fixtures are temporary, the external symlink target and global hooks value remain unchanged, and Git creates no HEAD or staged files.
- [x] T4 Document bootstrap and post-install lifecycle | owner: documenter | scope: S | needs: T2 | files: .ai/install/README.md,README.md,.project/portable-installer/progress.md
  - Accept: Documentation gives copy/run/check commands, created assets, supported shell, conflict behavior, Git/no-Git behavior, and explicitly assigns baseline review/commit to the user.
  - Evidence: Root and installer READMEs document copy/install/check/no-Git commands, exact asset classes, Bash environments, no-force conflict handling, dependency/provider exclusions, repository-local Git behavior, and the explicit user review/baseline-commit step; progress records delivered behavior and remaining gates.
- [x] T5 Resolve G3 read-only check and ignore-merge findings | owner: backend | scope: S | needs: T96 | files: .ai/install/install.sh,.ai/scripts/validate-kit.sh,.ai/tests/test_install.sh,.project/portable-installer/progress.md
  - Accept: `install.sh --check` leaves a byte-for-byte/path-for-path snapshot of the installed project unchanged, including no Python bytecode or cache directories.
  - Accept: Installing into a project whose non-empty `.gitignore` lacks a trailing newline preserves its existing bytes as a complete line and adds every required entry exactly once.
  - Accept: Focused regressions fail on the pre-remediation behavior and pass after correction without weakening static Python syntax validation.
  - Evidence: Validator now compiles Python source in memory instead of emitting bytecode; ignore merge inserts a separator only before the first missing entry when needed; no-Git and committed-Git before/after tree snapshots remain identical across `--check`. Focused 8-group installer tests and the post-remediation full suite pass with no `__pycache__` left behind.

## Standard Tail

- [x] T96 Validate full offline QA and Git checks | owner: qa | scope: S | needs: T3,T4 | files: .project/portable-installer/tasks.md,.project/portable-installer/progress.md
  - Accept: Installer regressions, complete mechanics tests, doctor, and Git worktree checks pass without invoking Codex or Claude CLI.
  - Evidence: `bash .ai/tests/run.sh` passed 52 harness tests, 8 installer groups, and 25 mechanics assertions; `bash .ai/scripts/doctor.sh --full` repeated the complete suite and ended with Git QA OK; explicit `bash .ai/scripts/git-qa.sh check worktree` and `git diff --check` pass. QA routing was disabled and no external provider was invoked.
- [x] T97 Review G3 under configured active-agent policy | owner: reviewer | scope: M | needs: T96,T5 | files: .project/portable-installer/tasks.md,.project/portable-installer/progress.md
  - Accept: Contract, security, correctness, consistency, and test passes find zero remaining blocker or major issues.
  - Evidence: G3 pass 1 verdict `request changes (active-agent)`: major correctness finding at `.ai/install/install.sh:171` because `--check` invokes a validator that writes Python bytecode caches, and major correctness finding at `.ai/install/install.sh:192-198` because appending to a non-newline-terminated `.gitignore` merges the first required entry into the prior line. T5 owns both corrections and missing regressions.
  - Evidence: G3 pass 2 verdict `approve (active-agent)` under `independent_enabled=false`; contract, security, correctness, consistency, and test passes found zero remaining blocker, major, or minor findings. Post-remediation evidence is 52 harness tests, 8 installer groups, 25 mechanics assertions, static no-bytecode validation, and explicit Git worktree QA.
- [x] T98 Complete installer release state | owner: release | scope: S | needs: T97 | files: .ai/ai.yaml,.project/portable-installer/plan.md,.project/portable-installer/tasks.md,.project/portable-installer/progress.md,.project/INDEX.md
  - Accept: Version, plan, progress, tasks, session, and project index report done only after G2/G3 pass.
  - Evidence: After post-remediation G2 and active-agent G3 approval, kit version is 0.15.0 and plan, task ledger, progress, session, and project index are synchronized to complete/done; no deploy, stage, commit, push, or data migration was performed.
