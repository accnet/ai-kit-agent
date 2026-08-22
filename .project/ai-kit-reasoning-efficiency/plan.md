# Plan — ai-kit-reasoning-efficiency

status: done
updated: 2026-08-22

## Goal

Reduce avoidable prompt/context overhead while preserving AI-Kit's deterministic
controls and make task specialization, review verification, and reasoning effort
explicit for Codex CLI and Claude CLI.

## Approach

Make context retrieval provider-aware so native CLIs do not receive project
instructions twice, and change pinned-source budgeting so a source deferred by
the reserved source budget is reconsidered whole before final truncation. Add a
compact, deterministic execution profile that names the selected AI-Kit skill
and owner contract without embedding every skill body. Configure and validate
per-role reasoning effort, and give Claude reviewers Bash access while retaining
plan permission mode and a non-mutating review instruction. Cover each behavior
with offline command/prompt/retrieval tests, then update the operator guide and
release metadata.

## Risks

- Removing `AGENTS.md` from a native-provider prompt could lose rules if a CLI
  stops auto-discovering project instructions → retain it for scripted/custom
  providers and test native-provider capability flags explicitly.
- Exposing Bash to Claude review could permit mutation attempts → keep plan mode,
  explicitly limit Bash to non-mutating verification, and retain repository
  mutation checks outside implementation.
- Higher reasoning effort increases latency/cost when a route is enabled → keep
  every provider route opt-in and make effort visible/configurable.
- Full task-specialist documents would recreate prompt bloat → inject exact
  workflow/owner paths and require on-demand loading instead of embedding bodies.

## Out of scope

- Paid A/B model evaluation or enabling any disabled provider route.
- Changing model identities selected in `.ai/config.json`.
- Raising the 24-task per-workstream cap.

## Open questions

None.
