# Tasks — configurable-independent-review

Intent: feature | Size: standard
Goal: Make independent review disabled by default and manually configurable without disabling QA or G3.
Out of scope: disabling tests/G3, provider authentication/calls, Git mutations, canonical-state rewrites
Open questions: none

## Tasks

- [x] T1 Add canonical independent-review configuration and harness enforcement | owner: backend | scope: M | needs: - | files: .ai/config.json,.ai/harness/cli.py,.ai/harness/engine.py,.ai/harness/models.py
  - Accept: With `review.independent_enabled=false`, harness initialization defaults to `active-agent` and rejects an explicit `independent` policy.
  - Accept: After the flag is manually changed to `true`, harness initialization defaults to `independent` and accepts either supported policy.
  - Accept: Missing, malformed, or type-invalid kit policy fails closed with an actionable error.
  - Evidence: Engine and CLI derive active-agent from the disabled flag, reject disabled independent requests, validate the kit config, and pass Python syntax compilation.
- [x] T2 Add configuration validation and offline regression tests | owner: qa | scope: M | needs: T1 | files: .ai/tests/test_harness.py,.ai/scripts/validate-kit.sh
  - Accept: Offline tests cover disabled default, disabled override rejection, enabled default, enabled active-agent override, and invalid configuration.
  - Accept: Static kit validation requires `.ai/config.json` and verifies its schema and boolean flag.
  - Evidence: 23 offline harness tests pass; static validation now requires and type-checks the canonical kit policy.
- [x] T3 Align rules, review skill, routing, and operator documentation | owner: documenter | scope: M | needs: T1 | files: AGENTS.md,.ai/ai.yaml,.ai/models.yaml,.ai/modules/gates.md,.ai/modules/review.md,.ai/harness/README.md,.ai/knowledge/decisions.md,.ai/skills/ai-kit-review/SKILL.md,.agents/skills/ai-kit-review/SKILL.md,.claude/skills/ai-kit-review/SKILL.md
  - Accept: All canonical guidance states that QA and G3 remain mandatory while reviewer separation follows `.ai/config.json`.
  - Accept: Documentation gives one manual activation instruction and does not imply that unavailable independent review blocks completion while disabled.
  - Evidence: AI-Kit v0.8 guidance and synchronized review skills use `.ai/config.json`; static validation passes.
- [x] T4 Apply active-agent policy to features blocked only by independent review | owner: release | scope: S | needs: T2,T3 | files: .project/git-qa/plan.md,.project/git-qa/tasks.md,.project/git-qa/progress.md,.project/multi-service-contracts/plan.md,.project/multi-service-contracts/tasks.md,.project/multi-service-contracts/progress.md,.project/INDEX.md
  - Accept: Existing clean five-pass reviews satisfy G3 under the disabled independent-review policy, and both previously blocked features are marked done with the policy transition recorded.
  - Evidence: git-qa and multi-service-contracts retain their review histories, record the active-agent policy transition, and are marked done in their plans, progress, tasks, and index.

## Standard Tail

- [x] T96 Run full QA and Git worktree checks | owner: qa | scope: S | needs: T4 | files: .project/configurable-independent-review/tasks.md,.project/configurable-independent-review/progress.md
  - Accept: Harness tests, mechanics tests, static validation, doctor full, and Git worktree QA all exit zero.
  - Evidence: Doctor full exits zero with 23 harness tests, 24 mechanics assertions, synchronized skills, Git QA hooks enabled, worktree clean by G4 policy, and staged=0.
- [x] T5 Apply configured policy to existing states and review prompts | owner: backend | scope: M | needs: T96 | files: .ai/harness/engine.py,.ai/harness/config.json
  - Accept: With independent review disabled, a previously recorded `independent` state can be reviewed by its implementation provider, and the prompt/routing identify active-agent review.
  - Accept: After manual activation, recorded independent states still reject their implementation provider and the prompt identifies independent review.
  - Evidence: Review enforcement derives an effective policy from the global flag plus recorded state; mode-aware prompt and routing compile and parse successfully.
- [x] T6 Add effective-policy regressions and operator clarification | owner: qa | scope: M | needs: T5 | files: .ai/tests/test_harness.py,.ai/harness/README.md
  - Accept: Offline tests cover an existing independent state under disabled and enabled configuration, including provider separation and prompt wording.
  - Accept: Documentation distinguishes recorded state policy from the current effective reviewer-separation policy.
  - Evidence: 24 harness tests pass; state recorded as independent is reviewed by Codex when disabled, while enabled separation and mode-specific prompt assertions remain enforced.
- [x] T7 Re-run full QA after review remediation | owner: qa | scope: S | needs: T6 | files: .project/configurable-independent-review/tasks.md,.project/configurable-independent-review/progress.md
  - Accept: Harness tests, mechanics tests, static validation, doctor full, and Git worktree QA all exit zero after remediation.
  - Evidence: Doctor full exits zero after remediation with 24 harness tests, 24 mechanics assertions, static validation, synchronized skills, and Git worktree QA.
- [x] T8 Persist effective review policy in canonical audit records | owner: backend | scope: S | needs: T7 | files: .ai/harness/engine.py,.ai/harness/models.py,.ai/harness/projection.py
  - Accept: Every new review record stores its effective `active-agent` or `independent` policy, and generated task views label the verdict with that policy.
  - Accept: Plan projection identifies the state field as recorded policy so it is not confused with the current global effective policy.
  - Evidence: Review transitions store validated policy labels; generated tasks show policy plus verdict and plans distinguish recorded policy.
- [x] T9 Add canonical review-policy audit regressions | owner: qa | scope: S | needs: T8 | files: .ai/tests/test_harness.py
  - Accept: Offline tests assert active-agent and independent review records and projections retain the policy used at verdict time.
  - Evidence: 24 harness tests pass with canonical and projected audit assertions for both review policies.
- [x] T10 Run final QA after audit remediation | owner: qa | scope: S | needs: T9 | files: .project/configurable-independent-review/tasks.md,.project/configurable-independent-review/progress.md
  - Accept: Harness tests, mechanics tests, static validation, doctor full, and Git worktree QA all exit zero after audit remediation.
  - Evidence: Final doctor exits zero with 24 harness tests, 24 mechanics assertions, synchronized skills, static validation, and Git worktree QA.
- [x] T97 Review G3 under configured active-agent policy | owner: reviewer | scope: M | needs: T10 | files: .project/configurable-independent-review/tasks.md,.project/configurable-independent-review/progress.md
  - Accept: Five-pass contract, security, correctness, consistency, and tests review has zero major/blocker findings and is labeled active-agent review.
  - Review attempt 1: request changes; active-agent five-pass review.
  - Major: `.ai/harness/engine.py:503` enforces the recorded independent policy without consulting the current disabled flag, so pre-existing independent states remain blocked instead of following the global off switch.
  - Major: `.ai/harness/config.json:20` still routes reviews to Claude and `.ai/harness/engine.py:783` always says “Independently review”, contradicting the configured active-agent mode.
  - Review attempt 2: request changes; the two first-pass findings are fixed.
  - Major: `.ai/harness/engine.py:529` persists provider and verdict but not the effective review policy, so toggling the global flag destroys the audit distinction between active-agent and independent verdicts; persist and project the policy used.
  - Review attempt 3: approve; active-agent five-pass review confirms all three major findings are remediated with no remaining major/blocker.
- [x] T98 Complete release state | owner: release | scope: S | needs: T97 | files: .project/configurable-independent-review/plan.md,.project/configurable-independent-review/tasks.md,.project/configurable-independent-review/progress.md,.project/INDEX.md
  - Accept: Feature and index are marked done only after G2 and configured G3 pass; session points to no stale independent-review blocker.
  - Evidence: Implementation, repeated QA, and configured active-agent G3 pass; plan, progress, index, and session are current.
