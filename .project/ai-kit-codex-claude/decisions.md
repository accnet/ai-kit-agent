# Decisions — ai-kit-codex-claude

## Canonical skills with generated projections

Use `.ai/skills/` as the editable workflow source and generate byte-identical `.agents/skills/` and `.claude/skills/` projections. Generated copies are preferred over symlinks for predictable Windows/WSL behavior.

## Advisory model routing

Codex is the primary agent and Claude is the preferred independent reviewer, but `.ai/models.yaml` is explicitly advisory until an external orchestrator consumes it.

## Honest enforcement boundary

Generic Git hygiene and configured CI tests are mechanical. Planning, acceptance interpretation, independent review, and destructive-operation authorization remain task-aware workflow or host-control responsibilities.
