---
name: knowledge-loader
description: Load only domain rules and architecture decisions relevant to the current task.
---

# Knowledge Loader

## Purpose
Load business rules and architecture decisions that constrain the task — the "why" behind the code.

## When to Load
Task touches domain logic, money, permissions, or crosses module boundaries. Skip for pure mechanical changes.

## Sources (in order)
1. `.ai/knowledge/decisions.md` — cross-feature decisions that bind this task's domain
2. `.ai/knowledge/conventions.md` — project-specific conventions
3. `.ai/knowledge/postmortems.md` — lessons relevant to this task's risk area
4. `.project/<feature>/decisions.md` + `features/<feature>/research/` — decisions and research for this feature
5. AGENTS.md / rules.yaml — process constraints

## Graduation Rule (.project/ → knowledge/)
When a feature closes, Documenter moves anything that binds FUTURE work:
- decision constraining other features → `knowledge/decisions.md`
- codebase-specific rule discovered → `knowledge/conventions.md`
- incident/defect with a lesson → `knowledge/postmortems.md`
One-off context stays in `.project/<feature>/decisions.md`.

## Rules
- Business rule found only in code comments or old chats → extract it into `.project/<feature>/decisions.md` now (or `features/` via user if it's a requirement)
- Conflicting rules between features → escalate to user; don't pick silently
- Knowledge loaded must be dated/attributed — stale business rules are worse than none
- knowledge/ files are loaded by relevant section, not wholesale (minimal_context applies)

## Output
Short constraint list ("must", "must not", "because") merged into working context at assembly tier 5.
