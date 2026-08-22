# Plan — configurable-independent-review

status: done
updated: 2026-08-22

## Goal

Make independent QA/review opt-in through one machine-readable AI-Kit
configuration file. Keep QA validation and G3 review mandatory, but use the
active agent for review until a maintainer manually enables independent review.

## Approach

Add `.ai/config.json` as the canonical kit-level runtime policy. The harness
loads and validates it, derives the default review policy from
`review.independent_enabled`, and rejects an explicit `independent` request
while that flag is false. Update human-facing rules, skills, model routing, and
harness documentation to read the same policy. Add offline CLI tests and static
validation, then migrate features that were blocked only on unavailable
independent review to the configured active-agent policy.

## Risks

- A documentation-only flag would leave the harness behavior inconsistent, so
  CLI initialization and validation must enforce the setting.
- Existing canonical states retain their recorded review policy; migration is
  limited to legacy task records currently blocked on independent review.
- Disabling independent review lowers reviewer separation, so the five-pass G3
  review and evidence coverage remain mandatory and the limitation is explicit.

## Out of scope

- Disabling QA tests, G2, or G3.
- Automatic provider authentication or provider calls.
- Git staging, commits, pushes, or global configuration.
- Rewriting existing harness state files.

## Open questions

None. The user explicitly selected disabled-by-default with manual activation.
