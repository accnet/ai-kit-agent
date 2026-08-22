# Legacy command compatibility

Canonical reusable workflows are Agent Skills in `.ai/skills/`:

| Legacy command | Canonical skill |
|---|---|
| `plan` | `ai-kit-plan` |
| `implement` | `ai-kit-implement` |
| `review` | `ai-kit-review` |
| `status` | `ai-kit-status` |

Run `.ai/scripts/sync-skills.sh` after editing a canonical skill. It generates byte-identical projections in `.agents/skills/` for Codex and `.claude/skills/` for Claude Code. CI uses `--check` to reject drift.

Files in `.ai/commands/` are documentation compatibility shims only. Claude and Codex should invoke the namespaced skills, avoiding collisions with built-in commands. Do not copy these shims to deprecated custom-prompt directories.
