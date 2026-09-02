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

AI-Kit protocol contracts belong under `.ai/contracts/`. Project product
contract sources belong in `.contracts/` or below the owning service's declared
paths. `state.json` stores the execution view and current
approved hash; generated `.project/` Markdown is never a product interface
source.

## Supported project contract types

Project contracts in `.contracts/` may use these governed kinds:

| Kind | Canonical representation | Required semantic concerns |
|---|---|---|
| `schema` | JSON Schema | properties, required fields, types, enums, arrays, refs, evolution |
| `api` | OpenAPI with JSON Schema payloads | operations, request/response, errors, auth, idempotency, deprecation |
| `event` | AsyncAPI-like document with optional CloudEvents envelope | channel, message, key, ordering, delivery, replay, duplicates, DLQ |
| `data` | project-owned declarative metadata/schema | single writer, entities, integrity, expand/backfill/switch/contract, reconciliation |
| `workflow` | project-owned state-machine metadata | source of truth, transitions, timeout, retry, idempotency, compensation |

JSON Schema is the reusable payload primitive for API and event contracts. A
CloudEvents envelope is an event concern and does not replace AsyncAPI channel
or message ownership. Frontend view-model, operations/SLO, GraphQL, gRPC,
Avro, and Pact contracts are future extensions unless a feature explicitly
adds an approved adapter.

## Project bootstrap and ownership

Installing `.ai` provisions AI-Kit runtime contracts from `.ai/contracts/` but
must not invent project contracts. A project may create an empty `.contracts/`
registry or skeleton only; services, owners, producers, consumers, versions,
invariants, and rollback decisions require an Architect/user-owned contract
task. `.contracts/` sources are never treated as AI-Kit runtime contracts.

Every project contract declares exactly one owner service, at least one
producer, zero or more consumers, a semantic version, compatibility mode,
change type, source path, verification, rollout, and rollback. The source path
must remain under `.contracts/` or the owning service's declared contract
directory; `.project/` projections and `.ai/contracts/` are invalid project
sources.

## Adapter and compatibility rules

Shape validation, semantic compatibility, and governance are separate layers:

1. A kind adapter parses the declared source into a normalized contract model.
2. The compatibility checker returns `unchanged`, `additive`, `backward`,
   `forward`, `full`, `breaking`, or `unsupported` with path-scoped findings.
3. Policy enforces ownership, approval, dependencies, migration evidence, and
   release metadata.

Adapters are read-only, deterministic, dependency-bounded, and must not use
network or mutate contract sources. Unsupported keywords or protocol features
fail closed. A breaking result requires `change_type: breaking`,
`compatibility: none`, explicit consumer migration tasks, integration evidence,
and a rollback plan; it is never silently downgraded to additive.

The AI-Kit core may validate project contract metadata and invoke approved
adapters, but it never auto-approves, auto-deploys, runs database migrations,
or infers missing service ownership from source files.

## Capability activation

The IDE LLM may recommend contract capabilities when repository or task
evidence warrants them; users do not choose a project-size profile. The
deterministic resolver records signals and provenance and enforces dependencies.
Declared services or contracts always activate their ownership, compatibility,
and integration controls even if the LLM omitted them. Database and production
risks similarly activate database safety and release ordering. Overrides cannot
disable controls required by declarations or the global safety floor.

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

The v0.16 harness mechanically enforces C1, C2, the declared portion of C3,
task-level ownership for C4, and required task declarations plus passing local
evidence for C5/C6. G3 still evaluates evidence quality, and host controls remain
authoritative for deployment because no remote deployment adapter exists.

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

## Cross-feature execution contract

Harness canonical plans may add optional plan-level `feature_dependencies` and
task-level ordered `verification_profiles`. These fields are additive: plans
without them retain legacy local scheduling and inline verification behavior.

- `feature_dependencies` entries name one external `feature` and `task`; every
  local task is blocked until every target is complete.
- Target `state.json` is authoritative when present. A missing or malformed
  state is an error and must not fall back to `tasks.md`; only an absent state
  permits legacy checkbox resolution.
- Duplicate, self, missing, incomplete, malformed, and cyclic target graphs
  fail closed with stable diagnostics. Resolution is read-only.
- `verification_profiles` reference centrally validated profile IDs. Inline
  `verification_commands` execute first, then profiles in declaration order;
  the first failure or timeout stops execution and blocks completion.
- Profile execution uses validated argv, repository-contained cwd, bounded
  timeout, and `shell=False`. Durable evidence snapshots the resolved profile
  ID, argv, cwd, timeout, metadata, exit result, duration, and output digest.

Provider enablement remains governed solely by `.ai/config.json`; these fields
do not select or authorize a provider.

## Context boundary

Implementation and review prompts include the current task's service plus only
services participating in its referenced contracts. Contract objects are kept
verbatim. Unrelated service graphs stay out of the task prompt; durable memory
continues to use provenance hashes and the configured character budget.
