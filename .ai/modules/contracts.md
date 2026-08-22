---
name: contracts
description: Multi-service contract graph, ownership, compatibility, approval, and scheduling rules. Load for cross-service frontend/backend/API/event/database work.
---

# Module: Multi-Service Contracts

## Purpose

Give LLMs freedom to design bounded work while the harness controls the seams
between services. The contract graph is the scheduling boundary; file scope
alone never proves two service tasks are independent.

## Contract hierarchy

| Contract | Required decisions |
|---|---|
| Domain/system | bounded context, vocabulary, business invariants |
| Service | domain, owned paths/data, dependencies, forbidden dependencies |
| API | request/response/errors, auth, idempotency, version/deprecation |
| Event | producer/consumer, key, ordering, delivery, replay, duplicates, DLQ |
| Data | single writer, integrity, expand/backfill/switch/contract, reconciliation |
| Frontend | view model, loading/empty/error/success, permissions, error mapping |
| Workflow | state machine, source of truth, saga/compensation, consistency window |
| Operations | SLO, health, telemetry, capacity, deploy order, canary, rollback |

Product contract sources belong in committed code such as `contracts/` or an
owning service. `state.json` stores the execution view and current approved
hash; generated `.project/` Markdown is never a product interface source.

## Planning rules

1. Identify service and data ownership before creating implementation tasks.
2. Version API/event/data/frontend/workflow/operations contracts and name all
   producers and consumers.
3. Create one Architect-owned `public-contract` task per changed contract.
4. Create one implementation task per service/layer. Use a separate QA task for
   cross-service integration and a Release task for delivery ordering.
5. Declare exact contract read/write/produce sets and a rollback statement.
6. Keep each feature a bounded workstream of at most 24 tasks; link larger
   programs with hierarchy metadata.

## Contract gates

- **C1 Ownership**: service IDs are unique; paths and data have one owner;
  dependencies are known and do not conflict with forbidden dependencies.
- **C2 Approval**: every consumed/produced source is explicitly approved and
  its on-disk SHA-256 matches canonical state.
- **C3 Compatibility**: version, compatibility, change type, consumers,
  rollout, rollback, invariants, and verification are declared. A breaking
  contract declares compatibility `none` and needs consumer migration work.
- **C4 Data safety**: database tasks select the owning service, list owned data
  entities, declare database risk, and follow expand/contract migration rules.
- **C5 Integration**: producer and consumer checks are named in the contract
  and task evidence; cross-service behavior is verified outside either
  service's unit boundary.
- **C6 Release**: environment, service delivery predecessors, rollout, and
  rollback are visible before a release task can close.

The v0.7 harness mechanically enforces C1, C2, the declared portion of C3, and
task-level ownership for C4. G2/G3 evidence and reviewers enforce C5/C6 until a
deployment adapter exists. Do not claim remote deploy enforcement.

## Scheduling and invalidation

- A contract has one writer task. Every same-plan reader/producer depends
  transitively on it.
- Starting a writer clears prior approval and marks the contract
  `draft`/`pending` before the model runs.
- Review completion does not approve a public contract. A named user runs
  `approve-contract`, which hashes the current regular repository file.
- A writer that reports success must have actually mutated each declared source.
- `deprecate-contract` is the explicit transition from approved to deprecated;
  deprecated versions remain auditable and block new scheduling.
- Draft contracts block with an approval reason. Deprecated, missing,
  symlinked, or hash-mismatched contracts fail closed with replan guidance.
- Replan preserves an approval only when public metadata and the source digest
  are unchanged.

## Context boundary

Implementation and review prompts include the current task's service plus only
services participating in its referenced contracts. Contract objects are kept
verbatim. Unrelated service graphs stay out of the task prompt; durable memory
continues to use provenance hashes and the configured character budget.
