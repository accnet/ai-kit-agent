---
name: testing
description: Test selection and evidence standards. Load when writing or evaluating tests.
---

# Module: Testing

## Purpose
Testing standards across levels — unit and integration/E2E.

## When to Load
Every implementation task (unit level) and every QA task (integration/E2E level).

## Test Pyramid
- **Unit** — with every implementation task; fast, isolated, no I/O
- **Integration** — module boundaries: API + DB, service + queue; owned by QA, written per feature
- **E2E** — critical user paths only; few, stable, high-value

## Standards
- Tests derive from acceptance criteria, not from the implementation
- Each test: one behavior, clear name (`rejects_expired_token`, not `test2`)
- Deterministic: no real time, network, or randomness without control
- Error paths and edge cases (empty, limits, permissions) are mandatory, not stretch goals
- A test that never fails is a liability — verify it fails when the behavior breaks

## Checklist (per feature)
- [ ] Every acceptance criterion mapped to at least one test
- [ ] Unit tests paired with implementation tasks
- [ ] Integration tests at feature boundaries
- [ ] Flaky tests fixed at root cause or deleted, never retried into green

## Output
Tests committed to the suite; mapping criteria → tests noted in tasks.md.
