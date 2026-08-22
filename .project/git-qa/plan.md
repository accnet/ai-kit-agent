# Plan — git-qa

status: done
source: user conversation, 2026-08-22

## Goal
Make AI-Kit detect Git, configure repository-local QA hooks when authorized, and use Git worktree/staging information in deterministic QA without requiring Git on every machine.

## Approach
Add a dependency-free `git-qa.sh` command with status, setup, and check actions. Setup may initialize only the AI-Kit root when explicitly passed `--init`, then configures only local `core.hooksPath`. Checks reuse G4 hygiene across tracked and untracked worktree files, detect conflict markers/whitespace errors, and expose concise repository state. Doctor reports availability; full QA exercises the behavior in an isolated temporary Git repository. Finally, initialize this checkout because the user explicitly requested Git setup.

## Risks
- Accidentally mutating global Git config -> use `git config --local` only and assert repository root.
- Making AI-Kit unusable without Git -> status/check skip cleanly when Git or a repository is absent.
- Hygiene gaps on a freshly initialized all-untracked repository -> add `worktree` mode using tracked plus non-ignored untracked files.
- Touching user staging/commits -> setup never stages, commits, pushes, or changes identity.

## Task Summary
8 tasks including QA, review, documentation, and release state. Riskiest: T1 command semantics and repository boundary validation.
