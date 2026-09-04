---
name: ai-kit-validate-quality
description: Validate an AI-Kit feature or QA-owned task against acceptance criteria using integration, end-to-end, edge-case, and Git worktree evidence. Do not use to implement application fixes or issue the G3 review verdict.
---

# AI-Kit Validate Quality

Produce reproducible G2 quality evidence from user intent rather than accepting
the implementation's claims.

## Workflow

1. Identify the active feature and QA task. Read the brief, acceptance criteria,
   architecture/contracts, implementation evidence, and relevant adjacent
   behavior; do not derive expected behavior from code alone.
2. Load `.ai-kit/agents/qa.md`, `.ai-kit/modules/testing.md`, and
   `.ai-kit/modules/gates.md`. Read `quality.qa` from `.ai-kit/config.json` before any
   top-level harness dispatch.
3. Map every acceptance criterion to at least one reproducible check. Cover the
   happy path plus applicable invalid, empty, boundary, permission, concurrency,
   failure, recovery, compatibility, and regression cases.
4. Run the smallest relevant checks first, then integration/E2E and configured
   broader validation. When Git is available, include
   `.ai-kit/scripts/git-qa.sh check worktree` for repository evidence.
5. Write only missing test code or fixtures inside the QA task scope. Record
   defects with severity, reproduction, expected versus actual behavior, owner,
   and affected criterion. Do not fix application code; return defects to the
   owning implementation task.
6. At top level, `quality.qa.enabled=true` may route a QA-owned harness step to
   its selected CLI/model. If this process was already selected for one bounded
   QA task, validate directly and never recursively invoke another step.
7. Close QA only when all criteria have passing evidence and no blocker/major
   defect remains. Flaky, skipped, unavailable, or environment-blocked checks
   remain visible limitations rather than passes.

## Boundaries

- QA evidence does not approve G3 and does not establish reviewer independence.
- Do not change product requirements, waive gates, deploy, or mutate external
  environments merely to make validation pass.

## Output

Report criterion-to-check coverage, commands and environments used, pass/fail
results, defects and limitations, Git QA status, and whether the feature is
ready for `ai-kit-review`.
