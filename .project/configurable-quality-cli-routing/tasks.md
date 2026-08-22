# Tasks — configurable-quality-cli-routing

Intent: feature | Size: standard
Goal: Configure QA and Review to independently select Codex CLI or Claude CLI with pinned models when enabled.
Out of scope: automatic activation, real provider calls, planner/non-QA routing, auth, gate waivers, Git mutations
Open questions: none

## Tasks

- [x] T1 Add quality CLI registry and route enforcement | owner: backend | scope: M | needs: - | files: .ai/config.json,.ai/harness/cli.py
  - Accept: Configuration defines `codex-cli` with `gpt-5.6-sol`, `claude-cli` with `claude-sonnet-5`, and independent disabled-by-default QA/Review route selections.
  - Accept: An enabled QA route applies only to a resolved `owner: qa` task; an enabled Review route applies only to `review`; each pins its selected provider/model and rejects a conflicting provider or scripted response.
  - Accept: Disabled routes require explicit provider selection, and missing/type-invalid/unknown provider configuration fails closed before any provider call.
  - Evidence: Config registry, exact model validation, QA owner-aware precedence, optional Review routing, conflict errors, and locked task selection compile; CLI help exposes optional routed providers.
- [x] T2 Add offline QA/Review routing regressions | owner: qa | scope: M | needs: T1 | files: .ai/tests/test_harness.py,.ai/scripts/validate-kit.sh
  - Accept: Tests cover QA and Review routing through both CLIs, exact model propagation, conflict rejection, disabled behavior, and QA precedence over normal Terra task execution.
  - Accept: Command previews show Codex review read-only, Claude review plan mode, QA implementation permissions, exact models, and no bypass flags.
  - Accept: Static validation verifies the provider registry and both route schemas without invoking a provider.
  - Evidence: 26 harness tests pass with both CLIs, exact models, permission modes, QA precedence, conflicts, disabled behavior, and mocked invocations; static validation passes.
- [x] T3 Align gates, agent skills, and operator documentation | owner: documenter | scope: M | needs: T1 | files: AGENTS.md,.ai/ai.yaml,.ai/models.yaml,.ai/agents/qa.md,.ai/modules/gates.md,.ai/modules/review.md,.ai/harness/README.md,.ai/knowledge/decisions.md,.ai/skills/ai-kit-implement/SKILL.md,.ai/skills/ai-kit-review/SKILL.md,.agents/skills/ai-kit-implement/SKILL.md,.agents/skills/ai-kit-review/SKILL.md,.claude/skills/ai-kit-implement/SKILL.md,.claude/skills/ai-kit-review/SKILL.md
  - Accept: Documentation explains independent QA/Review switches, provider/model choices, route precedence, and that reviewer CLI choice does not waive or imply independent review.
  - Accept: QA and Reviewer workers already selected by the harness are instructed to act directly and never recursively invoke their route command.
  - Evidence: AI-Kit v0.10 rules, gates, QA contract, review module, operator docs, durable decision, and synchronized implementation/review skills describe route selection, precedence, separation, and recursion boundaries; static validation passes.

- [x] T4 Make disabled QA routing fail closed | owner: backend | scope: S | needs: T1 | files: .ai/harness/cli.py,.ai/tests/test_harness.py
  - Accept: A QA-owned task never falls through to automatic Terra task execution while `quality.qa.enabled=false`; it requires an explicit provider.
  - Accept: Enabled QA and Review routes reject both conflicting providers and scripted responses before provider invocation.
  - Evidence: G3 finding remediated with owner-aware fail-closed routing and offline regression assertions for disabled QA fallback plus QA/Review conflicts.

## Standard Tail

- [x] T96 Run full offline QA and Git worktree checks | owner: qa | scope: S | needs: T2,T3,T4 | files: .project/configurable-quality-cli-routing/tasks.md,.project/configurable-quality-cli-routing/progress.md
  - Accept: Harness tests, mechanics tests, static validation, doctor full, and Git worktree QA exit zero without real provider calls.
  - Evidence: Post-remediation doctor full exits zero with 26 harness tests, 24 mechanics assertions, synchronized skills, static validation, Git worktree QA, staged=0, and mocked/preview-only provider paths.
- [x] T97 Review G3 under configured active-agent policy | owner: reviewer | scope: M | needs: T96 | files: .project/configurable-quality-cli-routing/tasks.md,.project/configurable-quality-cli-routing/progress.md
  - Accept: Active-agent five-pass review has zero major/blocker findings.
  - Evidence: Active-agent Contract/Security/Correctness/Consistency/Tests review approved after remediating disabled-QA fallback; zero remaining major/blocker findings.
- [x] T98 Complete release state | owner: release | scope: S | needs: T97 | files: .project/configurable-quality-cli-routing/plan.md,.project/configurable-quality-cli-routing/tasks.md,.project/configurable-quality-cli-routing/progress.md,.project/INDEX.md
  - Accept: Feature and index are done only after G2/G3 pass, with both quality routes still disabled and no provider call made during QA.
  - Evidence: G2/G3 pass, project/index state is done, both route switches remain false, and validation used mocked/preview-only provider paths.
