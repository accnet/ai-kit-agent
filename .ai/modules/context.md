---
name: context
description: Minimal per-task context pipeline. Load when starting implementation or review work.
---

# Module: Context

## Purpose
Load the minimum context needed for the current task — no more (rules.yaml: minimal_context).

## When to Load
Always, immediately after planning. Context is assembled per task, not per feature.

## Submodules
Pipeline order:

1. `context/context-loader.md` — gather candidate sources
2. `context/dependency-analysis.md` — expand to affected code (when modifying existing code)
3. `context/context-ranking.md` — rank candidates by relevance
4. `context/token-budget.md` — cut to budget
5. `context/context-assembler.md` — merge into working context
6. `context/knowledge-loader.md` — add business/architecture rules (when task touches domain logic)

Trivial task (single known file) → loader + budget is enough.

## Rules
- Check `.workspace/session.md` first when resuming — it may already point at the exact context needed
- Loading "just in case" is a violation — every loaded item must serve the current task
- Context is rebuilt when switching tasks, not accumulated
- If needed context doesn't exist (no docs, no brief) → say so; don't fabricate

## Harness context plane

For a harness-managed feature, the current goal/task contract is injected
directly and remains untrimmed. `.ai/harness/memory.py` then ranks working,
episodic, and semantic records plus project sources within the configured hard
character budget. Every entry carries provenance and a SHA-256 source hash.
File-backed stale entries remain visibly marked `stale=true`; models must verify
them against current source before relying on them.

Native Codex and Claude adapters already load the repository instruction chain,
so harness retrieval excludes its duplicate `AGENTS.md` block for those
providers. Scripted/custom providers keep it by default. Pinned sources that do
not fit the reserved source share are deferred whole and reconsidered against
the remaining total budget; retrieval reports both excluded and truncated
source paths. Execution selects one owner-specific skill and agent-contract
path for on-demand loading rather than embedding all workflow bodies.

## Output
A working context set: files, contracts, rules, and provenance-aware memories relevant to the current task.
