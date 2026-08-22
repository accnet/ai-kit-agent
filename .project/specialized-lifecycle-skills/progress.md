# Progress — specialized-lifecycle-skills

status: done
updated: 2026-08-22

## Scope

- Add Architecture, Contract, Migration, and QA workflow entry points.
- Preserve existing Plan, Implement, Review, and Status skill identities.
- Defer Delivery Attestation until the harness can verify its evidence.

## Implemented

- Four canonical specialized skills with mutually exclusive routing boundaries.
- Generic implementation yields architecture, public contract, migration, and
  QA tasks to their specialized workflows.
- AI-Kit v0.11.0 discovery and exact eight-skill static registry.
- Byte-identical Codex and Claude projections.

## Validation

- Bundled `quick_validate.py`: all eight canonical skills pass.
- Static kit validation and projection check: pass.
- Full doctor: 27 harness tests and 24 mechanics assertions pass.
- Git worktree QA: pass; staged=0.

## Review

- Verdict: approve (`active-agent`).
- Five passes completed with zero findings: Contract, Security, Correctness,
  Consistency, and Tests.
- `attest-delivery` remains deferred until machine-verifiable attestation state
  and evidence hashing exist.
