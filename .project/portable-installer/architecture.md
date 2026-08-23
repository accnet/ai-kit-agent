# Architecture — portable-installer

status: approved-for-implementation
updated: 2026-08-22

## Context

AI-Kit is currently usable in this repository but its required root files live
outside `.ai/`. Copying only `.ai/` to a new project therefore omits agent entry
rules, Claude routing, Git ignore policy, local QA hooks, CI gates, project state,
and generated skill discovery paths. The bootstrap must be portable while keeping
all mutation deterministic, local, inspectable, and independent of model CLIs.

## Components and ownership

### Installer — `.ai/install/install.sh`

Owns root discovery, prerequisite checks, managed-file preflight, missing directory
creation, template installation, required `.gitignore` entry merging, canonical
skill synchronization, optional Git QA setup, and post-install verification. It
accepts `--check` for read-only readiness validation and `--no-git` to suppress all
Git mutation. It never edits `.ai` itself, invokes a provider, stages, commits,
pushes, or changes global Git configuration.

### Templates — `.ai/install/templates/`

Own byte-for-byte bootstrap versions of `AGENTS.md`, `CLAUDE.md`, the pre-commit
hook, GitHub gates workflow, and initial `.project/INDEX.md`. A manifest maps each
source to one project-root destination and records which executable bit is needed.
The current kit's root integration files are validation fixtures for template
parity, except `.project/INDEX.md`, whose bootstrap template is intentionally an
empty index rather than this repository's history.

### Existing deterministic helpers

`.ai/scripts/sync-skills.sh` remains the only writer of `.agents/skills` and
`.claude/skills`. `.ai/scripts/git-qa.sh setup --init` remains the only Git setup
path and enforces exact repository root plus repository-local hooks. The installer
orchestrates these helpers but does not duplicate their policy.

## Install lifecycle

```text
resolve script → require <root>/.ai/ai.yaml → parse flags
  → preflight templates, destinations, symlinks, and ignore file
  → --check: validate projections/Git state and exit without writes
  → create features/.project/.workspace and root integration parents
  → copy missing managed templates + merge missing ignore entries
  → synchronize Codex/Claude skill projections
  → Git available and enabled: git-qa setup --init
  → validate installed kit and report user-owned baseline next step
```

## Mutation and safety invariants

1. Project root is exactly two directories above the physical installer path and
   must contain `.ai/ai.yaml`; no caller-provided root or broad path is accepted.
2. Every managed destination is checked before the first write. An existing
   regular file is accepted only when byte-identical to the shipped template.
3. Existing destination symlinks and differing managed files are hard conflicts;
   the installer has no force or overwrite mode.
4. `.gitignore` is append-only for an exact required entry set. Existing content
   is preserved, duplicate required entries are not added, and symlinks fail.
5. Generated skill projections may be regenerated only after managed preflight;
   their source of truth remains `.ai/skills`.
6. Git setup runs only when `git` exists and `--no-git` is absent. The exact target
   becomes the repository root; a repository rooted at an ancestor is rejected.
7. Git setup may create `.git/` and local `core.hooksPath`; it never configures
   identity, adds files, creates a commit, branch, remote, push, or global setting.
8. `--check` performs no writes and fails if any required managed file, ignore
   entry, projection, executable bit, or enabled Git QA state is absent or drifted.
9. Normal success is idempotent while managed assets remain unchanged. Local
   customization is surfaced as a conflict and requires an explicit human merge.
10. All output names the target and result; errors are nonzero and actionable.

## Failure modes and recovery

- Invalid copy layout or missing canonical kit asset: stop before writes.
- Managed-file conflict or symlink: list the destination and stop before writes;
  preserve both the existing project content and every still-missing asset.
- Failure after apply (disk interruption, sync, Git, or validation): already copied
  deterministic files remain; correct the reported cause and rerun safely.
- Git unavailable: install succeeds with an explicit skipped status; the operator
  may install Git later and rerun without `--no-git`.
- Existing ancestor Git repository: Git QA refuses the mismatched root; files remain
  installed, and the operator must choose an actual project boundary.
- Customized managed asset after installation: `--check` and repeat install fail;
  compare with its template and consciously reconcile rather than force overwrite.

## Non-functional requirements

- Bash with standard POSIX utilities already used by AI-Kit; no network access.
- Paths are quoted, resolved physically, and tested with spaces.
- Tests use disposable directories and restore/compare global Git hook settings.
- Static validation checks shell syntax, executable bits, manifest integrity, and
  root/template parity for the shared integration assets.

## Alternatives considered

- Root-level installer outside `.ai`: rejected because it is absent when only the
  portable kit directory is copied.
- Download/curl bootstrap: rejected because it adds network and supply-chain state.
- Overwrite or `--force`: rejected because bootstrap convenience cannot authorize
  destroying project-owned instructions, hooks, or CI configuration.
- Automatically commit a baseline: rejected because review, identity, history, and
  commit authorization belong to the user and G4.
- Reimplement skill/Git mechanics inside install: rejected because duplicated
  policy would drift from the existing deterministic scripts.

## Rollout and rollback

Ship as additive `.ai/install` content plus validation and test integration. Existing
projects are unchanged until the installer is explicitly run. Rollback removes the
installer assets and their test/validation hooks; installed projects retain plain
files that can be reviewed or reverted normally. No data migration exists.
