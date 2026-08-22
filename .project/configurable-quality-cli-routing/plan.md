# Plan — configurable-quality-cli-routing

status: done
updated: 2026-08-22

## Goal

Allow QA and Review to independently opt into either Codex CLI or Claude CLI,
using `gpt-5.6-sol` for Codex and `claude-sonnet-5` for Claude, without changing
the existing task-execution or independent-review defaults.

## Approach

Add a shared quality-provider registry plus separate `quality.qa` and
`quality.review` route switches to `.ai/config.json`. A QA route applies only
when harness `step` resolves a task owned by `qa`; a Review route applies only
to the harness `review` command. Enabled routes select and model-pin their CLI,
reject conflicting provider/response arguments, and remain subject to existing
sandbox, structured evidence, file-scope, and reviewer-separation gates. When a
route is disabled, explicit provider selection remains required. Tests inspect
requests and command previews without invoking either provider.

## Risks

- QA ownership must be resolved before provider construction without starting
  a task or creating a race-prone second selection.
- Quality routing must not silently override normal task execution or equate a
  Claude reviewer with independent review when separation is disabled.
- CLI model aliases can drift; use the exact official Codex ID and Claude Code
  full model name in the auditable registry.
- Harness-selected QA/reviewer workers must not recursively dispatch themselves.

## Out of scope

- Enabling QA or Review CLI routing in this checkout.
- Real model calls, authentication, entitlement checks, or budget configuration.
- Planner routing or normal non-QA task execution changes.
- Waiving QA, G3, evidence coverage, or independent-review policy.
- Commits, pushes, deployment, or database changes.

## Open questions

None. Routes are independent, disabled by default, and select from two fixed
CLI identities with configurable model strings.
