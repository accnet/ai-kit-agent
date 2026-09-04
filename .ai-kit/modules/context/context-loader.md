---
name: context-loader
description: Gather cheap candidate context sources for the current task.
---

# Context Loader

## Purpose
Gather candidate context sources for the current task, cheaply, before any ranking.

## Source Order
1. `features/<feature>/brief.md` — always
2. `.project/<feature>/tasks.md` — current task + its criteria
3. `features/<feature>/research/` + `context/*` — requirements and research (read-only)
3b. `.project/<feature>/plan.md`, `architecture.md`, `decisions.md` — execution context
4. Files named in the task; then their direct imports/dependents
5. `.ai-kit/knowledge/conventions.md` — project conventions, or `.knowledge-index/index.json` top-K when present (see `.ai-kit/modules/context/knowledge-loader.md`)

## Rules
- Scan structure first (paths, signatures, exports), read bodies only when needed
- Prefer interfaces/contracts over implementations at this stage
- Note what was looked for but NOT found — missing context is a finding
- Do not read generated files, lockfiles, or vendored code

## Output
Candidate list: path + one-line reason it might matter. Feeds context-ranking.
