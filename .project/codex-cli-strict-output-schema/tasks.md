# Tasks — codex-cli-strict-output-schema

Intent: bug | Size: standard
Goal: Restore real Codex CLI task delegation under strict structured outputs.
Out of scope: model/auth/routing changes, schema relaxation, production writes
Open questions: none

## Tasks

- [x] T1 Add Codex strict-schema transport adapter | owner: backend | scope: M | needs: - | files: .ai/harness/providers.py,.ai/tests/test_harness.py
  - Accept: Codex receives a schema where every object property is required and canonically optional fields accept null.
  - Accept: Optional nulls are removed before canonical validation while required nulls still fail closed.
  - Accept: Claude and scripted provider behavior is unchanged.
  - Evidence: Codex-only transport conversion recursively requires every Plan/Execution/Review object property, makes canonical optionals nullable, strips their nulls, and revalidates the canonical schema.

- [x] T2 Preserve canonical rejection of unknown null fields | owner: backend | scope: S | needs: T1 | files: .ai/harness/providers.py,.ai/tests/test_harness.py
  - Accept: Null cleanup removes only declared optional fields; an unknown null field still reaches canonical validation and fails closed.
  - Evidence: G3 remediation checks membership in canonical properties; regression proves unknown null and required null both fail.

## Standard Tail

- [x] T96 Run offline QA and isolated live Codex/Terra retry | owner: qa | scope: S | needs: T1,T2 | files: .project/codex-cli-strict-output-schema/tasks.md,.project/codex-cli-strict-output-schema/progress.md
  - Accept: Full offline tests pass and the isolated harness task reaches review with exact artifact/evidence and no out-of-scope mutations.
  - Evidence: 27 integration tests and 24 mechanics assertions pass; live auto-routed Terra retry records provider=codex, state=review, exact 14-byte artifact, and one in-scope changed file.
- [x] T97 Review G3 under configured active-agent policy | owner: reviewer | scope: M | needs: T96 | files: .project/codex-cli-strict-output-schema/tasks.md,.project/codex-cli-strict-output-schema/progress.md
  - Accept: Five-pass review has zero remaining major/blocker findings.
  - Evidence: Active-agent Contract/Security/Correctness/Consistency/Tests review approves after unknown-null remediation; zero major/blocker findings remain.
- [x] T98 Complete release state | owner: release | scope: S | needs: T97 | files: .project/codex-cli-strict-output-schema/plan.md,.project/codex-cli-strict-output-schema/tasks.md,.project/codex-cli-strict-output-schema/progress.md,.project/INDEX.md
  - Accept: Feature/index state is done only after G2/G3 pass.
  - Evidence: G2/G3 pass and project/index state is done without changing real-project route defaults.
