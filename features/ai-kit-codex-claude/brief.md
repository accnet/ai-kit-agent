# Brief — Optimize AI-Kit for Codex and Claude

status: approved
approved-by: user directive, 2026-08-22

## Problem

AI-Kit has a sound four-tier concept but its current distribution has broken bootstrap files, incomplete module metadata, advisory configuration presented as routing, deprecated command wiring, and documented gates that do not all ship as mechanical checks.

## Required outcome

- Codex and Claude load the same concise canonical rules without duplication.
- Reusable plan, implement, review, and status workflows use progressively disclosed Agent Skills.
- Codex and Claude discovery projections come from one canonical source and cannot drift silently.
- Model routing clearly distinguishes advisory preferences from executable orchestration.
- Repository checks honestly distinguish deterministic enforcement from agent workflow judgment.
- A dependency-free test suite verifies task state, context packing, skill sync, and commit hygiene.
- A single doctor command diagnoses structural and mechanics failures.

## Constraints

- Preserve the four-tier source-of-truth model and human-readable Markdown task state.
- Do not add application, API, database, deployment, or provider-orchestration behavior.
- Keep destructive and external actions approval-gated.
- Prefer cross-platform generated skill projections over symlink-only wiring.

## Acceptance

- `bash .ai/tests/run.sh` passes all mechanics assertions.
- `.ai/scripts/doctor.sh --full` passes.
- All canonical skills pass the Agent Skill validator.
- The final five-pass review has zero blocker or major findings.
