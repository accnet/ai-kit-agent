# Decisions — portable-installer

## 2026-08-22 Self-contained copied-kit bootstrap

- Decision: the executable, manifest, templates, and documentation all live below
  `.ai/install/`, so copying `.ai/` carries everything needed to bootstrap a root.
- Because: portability must not depend on a root file that does not yet exist.
- Instead of: a root-level setup script or a network downloader.

## 2026-08-22 Preflight and no force-overwrite mode

- Decision: existing managed files must be byte-identical; conflicts and symlinks
  stop the install before any managed file is written, with no `--force` escape.
- Because: agent rules, hooks, and CI are security-sensitive project-owned inputs.
- Instead of: last-writer-wins copies or heuristic text merging.

## 2026-08-22 Git QA is local and baseline remains user-owned

- Decision: when Git exists, normal install delegates `setup --init` to Git QA and
  configures only local hooks; it never stages or commits, and `--no-git` opts out.
- Because: local Git QA is useful by default, while history creation requires user
review and explicit authority.
