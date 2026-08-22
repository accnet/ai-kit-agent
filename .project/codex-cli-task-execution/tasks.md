# Tasks — codex-cli-task-execution

Intent: feature | Size: standard
Goal: Route harness task execution through Codex CLI with gpt-5.6-terra only when explicitly enabled in AI-Kit configuration.
Out of scope: automatic activation, real provider calls in QA, planner/reviewer routing, auth, Git mutations
Open questions: none

## Tasks

- [x] T1 Add Codex CLI task-execution policy and resolver | owner: backend | scope: M | needs: - | files: .ai/config.json,.ai/harness/cli.py
  - Accept: With `execution.codex_cli.enabled=true`, `step` defaults to provider `codex`, applies the configured `gpt-5.6-terra` model, and rejects `claude` or `scripted` provider overrides.
  - Accept: With the flag false, `step` performs no implicit provider selection and fails with an actionable error unless a provider is explicitly supplied.
  - Accept: Missing, malformed, or type-invalid execution configuration fails closed before any provider call.
  - Evidence: Disabled-by-default policy, conditional step resolver, model override, and conflict errors compile; CLI help exposes optional step provider without changing other commands.
- [x] T2 Add offline routing and command regressions | owner: qa | scope: M | needs: T1 | files: .ai/tests/test_harness.py,.ai/scripts/validate-kit.sh
  - Accept: Offline tests cover enabled default routing/model propagation, conflicting provider rejection, disabled missing-provider rejection, and explicit disabled-mode provider behavior.
  - Accept: A Codex command preview for an implementer contains `--model gpt-5.6-terra`, uses `workspace-write`, and contains no bypass flag.
  - Accept: Static validation requires a boolean enabled flag and non-empty model string without invoking Codex.
  - Evidence: 25 harness tests pass; captured requests and command previews verify Terra model, workspace-write sandbox, conflict rejection, disabled behavior, and zero provider execution.
- [x] T3 Align AI-Kit workflow and operator documentation | owner: documenter | scope: M | needs: T1 | files: AGENTS.md,.ai/ai.yaml,.ai/models.yaml,.ai/harness/README.md,.ai/knowledge/decisions.md,.ai/skills/ai-kit-implement/SKILL.md,.agents/skills/ai-kit-implement/SKILL.md,.claude/skills/ai-kit-implement/SKILL.md
  - Accept: Documentation explains the single activation flag, exact model, explicit behavior while disabled, and the harness sandbox/evidence boundaries.
  - Accept: Implementer guidance prevents a Codex process already selected by the harness from recursively invoking another `step`.
  - Evidence: AI-Kit v0.9 rules, harness docs, routing metadata, durable decision, and synchronized Codex/Claude implementation skills describe opt-in dispatch and the recursion boundary; static validation passes.

## Standard Tail

- [x] T96 Run full QA and Git worktree checks | owner: qa | scope: S | needs: T2,T3 | files: .project/codex-cli-task-execution/tasks.md,.project/codex-cli-task-execution/progress.md
  - Accept: Harness tests, mechanics tests, static validation, doctor full, and Git worktree QA all exit zero without a real provider call.
  - Evidence: Doctor full exits zero with 25 harness tests, 24 mechanics assertions, synchronized skills, static validation, Git QA hooks enabled, staged=0, and all provider execution mocked or preview-only.
- [x] T97 Review G3 under configured active-agent policy | owner: reviewer | scope: M | needs: T96 | files: .project/codex-cli-task-execution/tasks.md,.project/codex-cli-task-execution/progress.md
  - Accept: Five-pass review has zero major/blocker findings and is labeled active-agent.
  - Review attempt 1: approve; active-agent five-pass review found no major/blocker across contract, security, correctness, consistency, and tests.
  - Residual: account entitlement for `gpt-5.6-terra` is verified only on an explicitly enabled real run; QA intentionally performs no provider call.
- [x] T98 Complete release state | owner: release | scope: S | needs: T97 | files: .project/codex-cli-task-execution/plan.md,.project/codex-cli-task-execution/tasks.md,.project/codex-cli-task-execution/progress.md,.project/INDEX.md
  - Accept: Feature and index are marked done only after G2 and configured G3 pass; no provider was called during implementation QA.
  - Evidence: Config, resolver, offline QA, synchronized workflow, and active-agent G3 pass; release records are current.
