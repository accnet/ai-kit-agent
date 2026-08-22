# Plan — ai-kit-codex-claude

status: done
source: features/ai-kit-codex-claude/

## Goal
Make AI-Kit a lean, verifiable Codex–Claude workflow with correct bootstrap files, progressively disclosed skills, and honest deterministic gates.

## Approach
Repair broken foundations first, move reusable workflows from tool-specific commands to canonical Agent Skills with generated projections, then add repository-native validation and tests. Keep model routing advisory unless a real orchestrator consumes it.

## Risks
- Slimming always-on instructions could drop a safety invariant → preserve source-of-truth, approval, planning, review, and destructive-operation boundaries in AGENTS.md.
- Generated skill projections could drift → add a deterministic sync script and CI check.
- Shell parsers may accept malformed task state → add fixture-based smoke tests for claim, dependency, state, and context-pack behavior.

## Task Summary
7 tasks completed; T1 foundation repair was riskiest because every later workflow depended on valid bootstrap and module routing.
