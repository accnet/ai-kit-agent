# Progress — multi-service-contracts

status: done
version: 0.7.0
updated: 2026-08-22

## Implemented

- Optional hierarchy, service registry, and versioned contract registry in provider plans and canonical state.
- One-service task boundaries with contract read/write/produce sets, data entities, integration, delivery, and rollback metadata.
- Deterministic service path/data ownership, producer/consumer, single-writer, transitive dependency, and stale-source gates.
- Explicit `approve-contract` lifecycle; writer start invalidates prior approval before model execution.
- Bounded service/contract context in implementation and review prompts plus human-readable projections.
- Contract-first module and C1-C6 process documentation.

## Validation

- `bash .ai/tests/run.sh`: pass; 21 harness tests and 14 legacy mechanics assertions.
- `python3 .ai/tests/test_harness.py`: pass; 21 tests.
- `bash .ai/scripts/doctor.sh --full`: pass.

## Limits

- No semantic OpenAPI/AsyncAPI compatibility diff.
- No remote contract registry or deployment adapter.
- Program/workstream hierarchy is metadata; locks and execution remain feature-local.

## Review

G3 attempt 1 requested changes with five major findings covering service participation,
completed-contract auditability, symlink traversal, actual writer mutation, and the
missing deprecation transition. T9-T11 remedied the findings; the post-remediation
suite now passes 21 harness tests and 14 mechanics assertions. Independent review is next.

The post-remediation active-agent five-pass review found no remaining
major/blocker. A Claude Code 2.1.215 plan/read-only review was attempted, but
authentication failed before inference; no independent verdict was inferred.
On 2026-08-22, `.ai/config.json` made independent review opt-in, so the recorded
active-agent verdict satisfies G3 without depending on provider authentication.
