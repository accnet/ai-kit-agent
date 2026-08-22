# Plan — specialized-lifecycle-skills

status: done
updated: 2026-08-22

## Goal

Add four discriminating AI-Kit skills for architecture assessment, public
contract design, database/data migration, and QA validation without duplicating
the existing Plan, Implement, Review, or Status entry points.

## Approach

Create concise canonical skills under `.ai/skills/` that route to the existing
agent contracts and modules. Tighten `ai-kit-implement` so specialized tasks do
not collide with generic implementation. Update operator discovery, version and
static validation, then project the canonical skills into Codex and Claude
discovery directories. Validate every skill with the bundled skill validator,
run the full kit suite, and complete active-agent G3 review.

## Risks

- Overlapping descriptions could cause multiple skills to trigger for one task.
- Migration or contract skills could imply authority to mutate data or approve
  public contracts unless their stopping conditions are explicit.
- Canonical and projected skill copies can drift unless synchronization remains
  the only projection mechanism.

## Out of scope

- Adding `attest-delivery` before a machine-verifiable attestation state exists.
- Renaming or aliasing the existing Plan, Implement, Review, or Status skills.
- Changing harness provider models, route defaults, or executing migrations.

## Open questions

None.
