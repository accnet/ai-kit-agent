# Progress — ai-kit-agent-harness

status: done
version: 0.6.0
updated: 2026-08-22

## Delivered

- Dependency-free Python harness with canonical JSON state, sequenced JSONL
  events, deterministic Markdown projections, locks, status, and repair.
- Working, episodic, and semantic memories with bounded lexical retrieval,
  provenance hashes, and stale-source reporting.
- Structured scripted, Codex CLI, and Claude CLI adapters; model calls are
  explicit and no sandbox or permission bypass flag is used.
- LLM-first plan/replan, dependency scheduling, task approval, three-attempt
  escalation, evidence, and provider-separated independent review.
- Large-plan revision approval and per-task approval for database, destructive,
  production, credential, and external-write risks.
- SHA-256 before/after mutation verification, segment-aware scopes, control-file
  restoration, symlink/path guards, and crash artifact reconciliation.

## Evidence

- `bash .ai/tests/run.sh`: pass — 12 harness integration/failure tests and 14
  legacy mechanics assertions.
- `.ai/scripts/doctor.sh --full`: pass.
- Static validation: 22 modules, 4 canonical skills, synchronized projections,
  Python syntax, JSON config, and shell syntax.
- G3: approve with notes after four major first-pass findings were fixed and
  covered by T10-T13 regressions; zero blocker/major findings remain.

## Residual notes

- Provider commands were verified structurally but no live/billed Codex or
  Claude call was made during tests.
- Repository mutation snapshots are linear in repository file bytes; v0.6 runs
  one active implementation task per harness process.
- Review was a reviewer-role pass in the same Codex session, not external Claude.
