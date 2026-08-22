# Decisions — multi-service-contracts

## D1 — Contract registry is optional
Legacy plans remain valid. Multi-service enforcement activates when `services` or `contracts` is present, avoiding a breaking migration for small repositories.

## D2 — Contract source approval is explicit
A reviewed implementation task does not automatically approve a public contract. A human-named `approve-contract` transition hashes the current source and changes it to approved.

## D3 — One task, one service
Backend, frontend, and database tasks select one registered service. Cross-service behavior is decomposed into per-service tasks plus QA/integration or release tasks.

## D4 — Hierarchy is metadata, not a global lock
Program and workstream identifiers connect plans while execution state and locks stay feature-local. This preserves bounded context and parallelism.
