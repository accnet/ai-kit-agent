# Progress — configurable-quality-cli-routing

status: done
updated: 2026-08-22

## Implemented

- Shared `codex-cli`/`claude-cli` quality registry with pinned Sol and Sonnet 5
  models.
- Independent disabled-by-default QA and Review route switches.
- Owner-aware QA precedence, optional Review routing, conflicts, and fail-closed
  schema validation.
- Disabled QA routing now requires an explicit provider instead of falling
  through to automatic Terra task execution; G3 conflict coverage was expanded.
- AI-Kit v0.10 gates, docs, QA contract, synchronized skills, and recursion
  guards.

## Validation

- Post-remediation harness suite: 26 tests pass without provider calls.
- Static validation and skill synchronization: pass.
- Full doctor and Git worktree QA: pass with 24 mechanics assertions and staged=0.

## Review

- Verdict: approve (`active-agent`).
- Five passes completed: Contract, Security, Correctness, Consistency, Tests.
- One major fail-closed QA fallback finding was remediated and regression-tested;
  zero major/blocker findings remain.
- Both quality routes remain disabled; no real Codex or Claude provider was called.
