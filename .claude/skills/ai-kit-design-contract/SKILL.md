---
name: ai-kit-design-contract
description: Design or revise a versioned public API, event, data, frontend, workflow, or operations contract for an AI-Kit feature. Do not use for internal implementation details, architecture-only assessment, or contract approval.
---

# AI-Kit Design Contract

Create an auditable cross-boundary contract while keeping ownership,
compatibility, and approval separate from implementation.

## Workflow

1. Verify G1 and identify the Architect-owned `public-contract` task, exact
   contract source, owning service, producers, consumers, and declared file
   scope. If these are absent, stop and replan before writing.
2. Load `.ai/agents/architect.md`, `.ai/modules/contracts.md`,
   `.ai/modules/gates.md`, the feature architecture, existing contract versions,
   and only affected producer/consumer code.
3. Define the contract kind and version plus request/response or message shape,
   errors, authentication or permissions, idempotency, ordering, consistency,
   invariants, compatibility, deprecation, verification, rollout, and rollback
   fields that apply to that kind.
4. Preserve one owner and one writer. Declare every producer and consumer and
   create dependencies for consumer migration or integration evidence. A
   breaking change must be explicit and cannot masquerade as additive.
5. Write only the task-scoped contract source and permitted architecture or
   decision records. Leave the contract `draft` with a pending source hash.
6. Run local schema/lint/contract checks. Stop for replan when ownership,
   compatibility, consumer coverage, or rollback remains unresolved.

## Boundaries

- Never run `approve-contract`, declare a draft approved, or act as the named
  human approver. Approval is a separate user-authorized transition.
- Do not implement producers or consumers, migrate data, deploy services, or
  broaden the contract beyond the feature requirements.
- If the harness already selected this worker for one contract task, perform it
  directly and do not recursively dispatch another task.

## Output

Report the contract reference and source, owner/producers/consumers,
compatibility and change type, checks run, rollout/rollback, approval state, and
blocking consumer or product decisions.
