# Progress — codex-cli-strict-output-schema

status: done
updated: 2026-08-22

## Discovery

- Isolated Codex/Terra handoff reached the provider but OpenAI rejected the
  execution schema because optional `evidence.command` was not required.
- Harness recorded T1 attempt 1 as `provider_error`; no artifact was created.

## Implemented

- Added a Codex-only strict-schema transport adapter with nullable canonical
  optionals and post-response canonical normalization/validation.
- Preserved rejection of required nulls, unknown fields, and unknown null fields.

## Validation

- Isolated retry through automatic Codex CLI task routing with
  `gpt-5.6-terra`: success; provider `codex`; task state `review`.
- Artifact: exact `CODEX_TASK_OK\n` (14 bytes); actual changed files contain only
  `smoke-output/codex-task.md`.
- Offline suite: 27 integration tests and 24 mechanics assertions pass.
- Full doctor, static validation, skill sync, and Git worktree QA pass; staged=0.

## Review

- Verdict: approve (`active-agent`).
- One major unknown-null cleanup finding was remediated and regression-tested;
  zero major/blocker findings remain.
