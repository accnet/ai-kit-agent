# Decisions — controlled-orchestrator-v2

## 2026-08-22 Review-before-promotion detached worktrees

- Decision: implementation and verification run in a detached Git worktree;
  the main worktree receives an unstaged binary patch only after review approval.
- Because: this separates model mutation from user state and makes scope, evidence,
  base drift, and review ordering mechanically enforceable.
- Instead of: copying directories, trusting provider sandboxes alone, task commits,
  or applying implementation output before review.

## 2026-08-22 Baseline and cleanliness are mandatory

- Decision: isolated execution requires an existing HEAD and a clean main tree;
  the harness never creates the initial commit or hides/stashes user changes.
- Because: patch provenance and rollback are ambiguous without a stable base, and
  user changes must never be moved or overwritten implicitly.

## 2026-08-22 Main index remains user-owned

- Decision: staging is permitted only in the disposable worktree to capture new
  files; promotion applies without `--index` and leaves main changes unstaged.
- Because: enabling controlled task execution does not authorize staging or commit.
