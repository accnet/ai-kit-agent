# Plan — portable-installer

status: complete
updated: 2026-08-22
source: user conversation

## Goal

Make a copied `.ai/` directory able to bootstrap an otherwise empty project with
the root integration files, skill projections, local workspace directories, and
optional repository-local Git QA wiring required by AI-Kit.

## Approach

Add a self-contained Bash installer under `.ai/install/` with versioned templates
for root-owned integration files. The installer derives the project root from its
own location, validates the copied kit, preflights every managed destination, and
then creates missing files and directories without silently overwriting drifted
content. It merges only required ignore entries, regenerates Codex and Claude skill
projections through the canonical sync script, and, when Git is available, uses
the existing Git QA setup to initialize the repository and configure local hooks.
It never stages, commits, pushes, invokes a model provider, or changes global Git
configuration. Add disposable-project tests, static distribution checks, and an
operator README covering first install, repeat install, conflicts, Git behavior,
and the required user-owned baseline commit.

## Risks

- Bootstrap could overwrite project-owned files → preflight all managed files and
  fail before mutation when an existing destination differs from its template.
- Running from the wrong location could modify another tree → derive and resolve
  the root from `.ai/install/install.sh` and require the copied `.ai/ai.yaml`.
- Git setup could affect parent/global state → require the exact project Git root,
  use repository-local `core.hooksPath`, and never change global configuration.
- A multi-step install can be interrupted → make completed steps repeatable and
  emit the exact failed step so rerunning safely completes unchanged assets.
- Template and installed-root integration files can drift in this kit → validate
  template parity and exercise installation from a copied `.ai` fixture.

## Out of scope

- Overwriting or merging customized `AGENTS.md`, `CLAUDE.md`, hooks, or CI files.
- Creating a baseline commit, staging files, pushing, deploying, or invoking LLMs.
- Installing Git, Python, Codex CLI, Claude CLI, or other system dependencies.
- Windows-native PowerShell installation; Bash/WSL/Git Bash is the supported path.
- Bootstrapping application-specific source code, dependencies, or contracts.

## Open questions

None.

## Task Summary

Seven tasks cover architecture, installer assets and behavior, integration tests,
documentation, QA, active-agent review, and release-state synchronization.
