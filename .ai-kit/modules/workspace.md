---
name: workspace
description: Ephemeral .workspace/ tier, session format, graduation rules, and resume procedure. Load only for active-work resume, task switches, or end handoff.
---

# Module: Workspace

## Purpose
Define `.workspace/` — the agent's ephemeral working state. Local only, never committed, safe to delete at any time.

## Four-Tier Model
| Tier | Content | Lifetime | Committed |
|---|---|---|---|
| `.ai-kit/` | knowledge & process (roles, modules, commands, memory) | permanent | yes |
| `features/` | requirements & research (intent) | per feature | yes |
| `.project/` | execution state (plan, tasks, architecture, progress) | per feature | yes |
| `.workspace/` | session state, scratch, drafts | per session | **no** |

## Layout
```
.workspace/
  session.md      current feature, current task, active agent role, next step
  scratch/        throwaway notes, POC snippets, command outputs
  drafts/         work-in-progress content not ready for .project/ or code
```

## session.md Format
```
feature: <name>
task: <tasks.md line being executed>
role: <agent from .ai-kit/agents/>
status: <one line — where things stand>
next: <first action when resuming>
```

## Rules
- Write `session.md` at start of work and update on every task switch — this is how a new session resumes without re-deriving context
- Parallel agents: each worktree carries its OWN `.workspace/` (separate working dirs) — session.md is per-instance, never shared state; shared state lives only in committed `tasks.md`
- Anything worth keeping graduates OUT of `.workspace/`: per-feature decisions → `.project/<x>/decisions.md`, tasks → `.project/<x>/tasks.md`, requirements discovered → `features/<x>/` (via user/Researcher), code → the repo
- Never reference `.workspace/` paths from committed code or docs
- `.workspace/` is in `.gitignore`; agents must never `git add` it
- Deleting `.workspace/` must lose nothing but convenience — if that's not true, something wasn't graduated

## Resume Procedure (new session)
1. `.workspace/session.md` exists → resume from `next:`
2. Missing/stale → rebuild from `.project/<feature>/tasks.md` (source of truth) and `.project/INDEX.md`, then rewrite session.md
