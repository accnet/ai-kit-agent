# Architecture — controlled-orchestrator-v2

status: approved-for-implementation
updated: 2026-08-22

## Context

The v0.13 engine invokes an implementation provider in the main repository and
detects scope violations after the process returns. It can restore harness
control files, but an out-of-scope application mutation remains in the user's
tree. v0.14 moves the mutation boundary into a disposable Git worktree and makes
promotion a separate, post-review control-plane transition.

## Components and ownership

### `GitWorkspaceManager` — `.ai/harness/worktrees.py`

Owns Git discovery, baseline validation, worktree creation, patch capture,
promotion preflight/application, and cleanup. It accepts only an AI-Kit root and
explicit feature/task/run identifiers. It never plans tasks, invokes models,
changes canonical state, stages the main index, commits, pushes, or merges.

### Provider request working directory — `.ai/harness/providers.py`

`ProviderRequest.working_directory` is an optional internal execution boundary.
Subprocess adapters validate it as a real, non-symlinked directory before spawn.
Codex uses it for both process cwd and `--cd`; Claude uses it for cwd. Omission
retains the provider's configured repository root for planning and compatibility.

### Orchestration lifecycle — `.ai/harness/engine.py`

The engine owns when a workspace exists and which transition may promote it:

```text
ready
  → create detached worktree at main HEAD
  → provider implementation in worktree
  → independent verification in worktree
  → capture/stage only disposable index and hash binary patch
  → review isolated worktree + patch metadata
  → approve: verify main HEAD/tree, check patch, apply unstaged, cleanup
  → revise/block: main untouched; cleanup or retain per retry/recovery state
```

Canonical task state stores only metadata: phase, base commit, resolved worktree
path, ownership marker, changed paths, and patch SHA-256. Patch bytes remain
derivable from the owned worktree until promotion. No committed file references
the ephemeral path.

## Trust boundaries and invariants

1. Repository root must be exactly the Git top-level and contain AI-Kit.
2. Creation requires Git, a resolvable `HEAD`, and an empty main porcelain status.
3. Worktree parent is a deterministic sibling control root, never inside the main
   worktree, `.git`, `$HOME`, or a caller-provided arbitrary directory.
4. Each workspace has an ownership marker containing repository root, feature,
   task, base commit, and a random run identifier. Cleanup requires an exact match.
5. Provider, mutation snapshots, verification, and review operate on the isolated
   root. Main-tree snapshots are used only for drift checks.
6. Patch capture stages only the disposable worktree index, then exports a binary
   cached diff. This never stages the main index.
7. Promotion requires main `HEAD == base_commit`, clean main porcelain status,
   patch digest match, `git apply --check`, and changed paths within task scope.
8. Promotion uses `git apply` without `--index`; resulting main changes remain
   unstaged. Commit remains a user-authorized G4 action.
9. Any failed invariant stops before provider invocation or patch application.
10. Cleanup uses `git worktree remove --force` only after marker validation and
    prunes metadata; it never recursively deletes an unresolved path.

## State and recovery

Workspace phases are `created`, `implemented`, `verified`, `review`, `promoted`,
`discarded`, and `failed`. A process restart loads the stored metadata, verifies
the marker/base/path, and can resume review. A new implementation retry first
validates and discards the prior owned workspace; an unknown or tampered path
blocks and requires operator inspection. Cleanup of a review/running workspace
requires an explicit abandon command so evidence is not silently lost.

## Failure modes

- No baseline commit or dirty main tree: block before provider call with setup
  guidance; do not create a commit.
- Provider/scope/verification failure: main remains unchanged; record failure and
  discard only the owned worktree.
- Review revise/block: never promote; retain finding evidence and discard owned
  workspace when the task returns to retry/escalated state.
- Main drift before approval: reject promotion and retain workspace for inspection;
  require replan/re-execution against the new base.
- Patch check/apply failure: main remains unchanged because check precedes apply;
  retain workspace and mark promotion failed.
- Crash after apply but before state commit: `repair` does not infer promotion
  completion. Stop automated approval, inspect main changes against the recorded
  patch digest, and reconcile state manually; never apply a second time blindly.

## Non-functional requirements

- Python 3.9 standard library only; Git CLI is the optional runtime dependency.
- All subprocess calls use argument vectors, `shell=False`, bounded output, and
  repository/workspace-specific cwd.
- Deterministic errors are testable without Codex or Claude.
- No secrets, patch bytes, or raw provider/verifier output enter canonical state.

## Alternatives considered

- Copy directory to a temp folder: rejected because it loses Git object identity,
  binary diff fidelity, ignore semantics, and safe base-drift checks.
- Provider-native sandbox only: rejected as the sole boundary because adapters
  differ and post-process side effects cannot be promoted transactionally.
- Branch + commit per task: rejected because the harness is not authorized to
  create commits or mutate user history.
- Apply immediately after implementation: rejected because review would occur
  after the main tree was already changed.

## Rollout and rollback

Ship isolation behind validated CLI configuration, with direct engine tests able
to opt out for legacy fixtures. The CLI's implementation route requires
isolation. Rollback disables the route and restores v0.13 engine/provider files;
owned worktrees remain inspectable and can be removed by the bounded cleanup
command. No application data migration exists.
