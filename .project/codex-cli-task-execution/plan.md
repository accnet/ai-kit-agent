# Plan — codex-cli-task-execution

status: done
updated: 2026-08-22

## Goal

Add an opt-in AI-Kit execution policy that routes harness task execution to
Codex CLI with model `gpt-5.6-terra` while preserving explicit provider
selection when the policy is disabled.

## Approach

Extend `.ai/config.json` with a disabled-by-default `execution.codex_cli`
section. Validate the boolean flag and model, then make only the harness `step`
command conditionally select Codex CLI and apply the configured model. Reject a
conflicting provider while enabled and reject a missing provider while
disabled. Keep planning/review provider selection explicit, retain the
workspace-write sandbox and structured-output contract, and document a
non-recursive handoff boundary for agents already executing inside the harness.

## Risks

- Conditional argparse behavior can silently fall back to another provider;
  selection must be resolved and validated after configuration is loaded.
- A model configured only in JSON may not reach `codex exec`; tests must inspect
  the final provider request and command preview without invoking a model.
- A Codex worker could recursively invoke `harness step`; skill guidance must
  distinguish top-level dispatch from an already-selected implementer prompt.

## Out of scope

- Enabling Codex CLI automatically in this checkout.
- Calling a paid model during tests or this configuration change.
- Changing planner or reviewer provider routing.
- Authentication setup, account entitlements, commits, pushes, or deployment.

## Open questions

None. The configuration is opt-in and preserves the exact requested model ID.
