# Progress — ai-kit-reasoning-efficiency

status: done
updated: 2026-08-22

## Implemented

- Provider-aware project-instruction de-duplication for Codex and Claude CLI.
- Whole-source deferral before final context truncation, with excluded/truncated
  source telemetry.
- One explicit AI-Kit workflow and owner-contract path per execution task.
- Validated per-role reasoning effort for both native adapters.
- Claude reviewer Bash access under plan mode with a non-mutating instruction.
- Mechanical before/after repository immutability enforcement for every review.

## Measured result

For `ai-kit-agent-harness` at the 16,000-character budget, native context changed
from 10,054 to 7,246 characters. `AGENTS.md` is excluded, the complete 3,774-
character architecture source is present instead of a 1,720-character prefix,
and no project source is truncated. Representative harness prompts dropped from
roughly 2.7–2.8k to 2.0–2.1k estimated tokens before output schema and native
CLI context.

## Validation so far

- Codex and Claude effort flags parse through installed CLI help commands.
- 32 offline harness tests pass; no provider executable was invoked by tests.

## Review

- Verdict: approve (`active-agent`).
- Contract, security, correctness, consistency, and tests reviewed with zero
  remaining findings.
- One initial major finding—Bash-capable review lacked mechanical mutation
  attribution—was resolved by T4 and covered by regression.
- Full doctor passes 32 harness tests and 24 mechanics assertions; Git worktree
  QA passes with staged=0.
