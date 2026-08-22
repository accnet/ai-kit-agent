# Plan — controlled-orchestrator-v1

status: done
updated: 2026-08-22
source: user conversation

## Goal

Make the local harness authoritative for durable run control, requirement-to-task
coverage, exact approval scope, and independently executed verification while
keeping every model route opt-in.

## Approach

Extend the versioned canonical state with an explicit run lifecycle and optional
requirement registry. Plans that opt into requirements must cover every declared
requirement and tasks must carry requirement references. Bind plan and risky-task
approvals to deterministic digests so a changed revision cannot reuse stale
authorization. Add a bounded verification runner that executes only declared,
argument-vector commands without a shell and records exit code plus output hash.
Expose lifecycle transitions through the CLI, project the new evidence into the
human-readable state, cover failure/resume/tamper paths offline, then update the
operator guide and release metadata.

## Risks

- New state fields could invalidate existing feature state → keep schema version 1
  additive and default missing fields during validation/projection.
- Model-proposed verification could become arbitrary command execution → accept
  JSON argument vectors only, run without a shell, impose timeout/output bounds,
  and require commands to be declared in the accepted task plan.
- Approval digests make legacy risky-task approvals stale → fail closed and
  require explicit reapproval under the current action digest.
- A CLI lifecycle could be mistaken for an autonomous daemon → document that v1
  controls run state and bounded steps; provider session streaming and sandbox
  promotion remain separate work.

## Out of scope

- Codex App Server or Claude Agent SDK adapters.
- Automatic provider-route activation or paid model calls.
- Per-task Git worktree/container isolation and patch promotion.
- Multi-workstream parallel scheduling, deployment, or database adapters.
- Authenticated cryptographic user identity or signed audit chains.

## Open questions

None.

## Task Summary

13 tasks including security hardening, QA, review, documentation, and release; riskiest first: T2
independent verification execution. T1 and documentation preparation are file-
disjoint, but implementation is intentionally serialized to keep one control-plane
writer.
