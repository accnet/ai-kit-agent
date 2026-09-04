---
name: git
description: Commit hygiene and optional multi-agent worktree coordination. Load before a requested commit or parallel branch work.
---

# Module: Git

## Purpose

Keep changes reviewable and coordinate parallel agents without treating Git as implicit user authorization.

## Commit hygiene

- A commit must map to one completed task or one coherent trivial change.
- Run the configured test command and `.ai-kit/scripts/check-gates.sh staged` before committing.
- Never stage `.workspace/`, secrets, generated scratch files, or unrelated user changes.
- Do not amend, rebase, force-push, or commit unless the user or an explicitly invoked workflow authorizes it.

## Git QA setup

AI-Kit detects Git without requiring it on every machine:

```bash
bash .ai-kit/scripts/git-qa.sh status
```

`status` never mutates the checkout. When the user authorizes Git setup, run:

```bash
bash .ai-kit/scripts/git-qa.sh setup          # existing repository
bash .ai-kit/scripts/git-qa.sh setup --init   # initialize this AI-Kit root
```

Setup refuses a parent/nested repository mismatch and modifies only local
`core.hooksPath=.githooks`. It does not set identity, stage files, commit, push,
or write global configuration.

Use the worktree view for QA:

```bash
bash .ai-kit/scripts/git-qa.sh check worktree
```

This runs G4 over tracked and non-ignored untracked files, checks staged and
unstaged whitespace errors, and rejects unresolved merge conflicts. `staged`
and `all` remain available for pre-commit and CI respectively. If Git or a
repository is absent, read-only status/check reports a deterministic skip;
explicit setup fails with guidance.

## Coordination modes

Use tool-native subagents/worktrees when the host provides them. For repository-native coordination:

1. Give each task disjoint `files:` ownership and stable interfaces.
2. Create one worktree and branch per task.
3. Claim the task with `next-task.sh --claim`, then commit the claim before implementation.
4. If the claim push is rejected, refresh task state and choose another claimable task.
5. Merge only after G2 passes; run G3 on the integrated diff.

Do not parallelize tasks that edit the same file, change a contract consumed by another task, or have a dependency relationship.

## Output

A focused diff whose task, validation evidence, review status, and ownership are unambiguous.
