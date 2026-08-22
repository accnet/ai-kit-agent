# Progress — git-qa

status: done
updated: 2026-08-22

## Implemented

- Optional Git detection with non-mutating status and deterministic skip output.
- Explicit root-bound `setup`/`setup --init` using only local hook configuration.
- Git-backed worktree QA for tracked and non-ignored untracked files, whitespace, conflicts, workspace hygiene, and credential patterns.
- Doctor, static validator, canonical config, documentation, and isolated temporary-repository tests.
- Current checkout initialized as a Git repository with `.githooks`; no staging, commit, identity, global config, or push mutation.

## Validation

- Harness: 21 tests pass.
- Mechanics: 24 assertions pass.
- `git-qa.sh check worktree`: pass.
- `doctor.sh --full`: pass.

## Review

G3 attempt 1 requested changes because content scans could dereference a
worktree symlink and expose an external file's matching secret line. T7-T8 own
the fix, regression coverage, and repeated QA.

T7 now skips symlinks before text scans, and T8 passes full QA. The
post-remediation active-agent five-pass review found no major/blocker. On
2026-08-22, `.ai/config.json` made independent review opt-in; the recorded
active-agent verdict therefore satisfies G3 without depending on Claude OAuth.
