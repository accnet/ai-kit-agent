# Architecture — multi-service-contracts

## Boundary

The LLM remains the reasoning plane. It proposes a plan containing services, versioned contracts, and bounded tasks. The harness remains the control plane and owns schema validation, normalization, approval, source hashing, scheduling, evidence, and state transitions.

## Canonical graph

`state.json` gains optional hierarchy metadata plus normalized `services`, `contracts`, and `contract_approvals`. A contract reference is always `<id>@<version>`. Contract sources are repository-relative and carry either `pending` or a SHA-256 digest.

Services declare domain, owned paths, owned data, exposed/consumed contracts, allowed dependencies, and forbidden dependencies. Contracts declare kind, owner, producers, consumers, compatibility, change type, invariants, verification, rollout, rollback, source, hash, and status.

Tasks may declare one service and layer plus contract read/write sets, produced contracts, data entities, environments, integration tests, deployment predecessors, and rollback guidance. A task still has a single owner and file scope.

## Deterministic gates

1. Registry validation rejects duplicate/unknown services and contracts, illegal dependencies, missing owners, invalid producer/consumer declarations, and data ownership conflicts.
2. Contract-writing tasks are Architect-owned, include the contract source in file scope, declare `public-contract`, and are the sole writer for that contract.
3. Readers of a contract written in the same plan transitively depend on its writer.
4. Backend, frontend, and database tasks in a registered multi-service plan select one service; their non-contract files remain inside that service's declared paths.
5. Database tasks declare only data entities owned by their service and retain the existing database-risk approval gate.
6. Scheduling blocks a reader until every referenced contract is approved and its current source hash matches canonical state.
7. Starting a writer marks its contracts draft/pending, preventing concurrent consumers. Review does not approve the public contract. `approve-contract` performs the explicit approval transition and records a fresh source hash.

## Compatibility

Plans without `services` and `contracts` follow v0.6 behavior. New task fields are optional in the provider schema and normalize to empty values. Existing v1 canonical state remains readable; new state fields default safely rather than forcing migration of completed features.

## Hierarchy

Optional `program_id`, `workstream_id`, and `parent_feature` metadata identify a bounded plan inside a larger program. The 24-task limit remains per workstream, preventing a single context-heavy mega-plan.

## Failure behavior

- Draft contract: typed approval block with the contract references.
- Missing or hash-mismatched contract source: fail closed with `needs_replan` guidance.
- Contract graph changed by a replan: unfinished approvals are cleared; completed task contracts cannot be rewritten.
- Contract writer failure: contract remains draft and consumers remain blocked.
