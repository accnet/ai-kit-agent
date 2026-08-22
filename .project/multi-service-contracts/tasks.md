# Tasks — multi-service-contracts

Intent: feature | Size: large
Goal: Add versioned multi-service contracts, deterministic ownership gates, stale-source detection, and contract-aware scheduling to the AI-Kit harness.
Out of scope: production deploy adapters, remote registries, semantic OpenAPI/AsyncAPI diffing, distributed cross-feature execution
Open questions: none
Plan approval: user instructed execution after reviewing the contract analysis on 2026-08-22

## Tasks
- [x] T1 Define the multi-service contract architecture | owner: architect | scope: M | needs: - | files: .project/multi-service-contracts/architecture.md,.project/multi-service-contracts/decisions.md
  - Accept: Architecture names the canonical service, contract, task, hierarchy, approval, stale-source, and compatibility boundaries.
  - Evidence: architecture.md and decisions.md created before harness implementation.
- [x] T2 Add provider schemas and canonical state fields | owner: backend | scope: M | needs: T1 | files: .ai/harness/schemas.py,.ai/harness/models.py
  - Accept: A legacy plan validates unchanged and a plan can express hierarchy, services, contracts, and contract-aware task fields.
  - Accept: Canonical state validation accepts normalized contract fields and rejects structurally corrupted graph state.
  - Evidence: Python compilation and a legacy PLAN_SCHEMA validation fixture passed.
- [x] T3 Enforce ownership, dependency, and contract readiness policy | owner: backend | scope: M | needs: T2 | files: .ai/harness/policy.py
  - Accept: Invalid ownership, duplicate writers, missing writer dependencies, and database data ownership violations are rejected deterministically.
  - Accept: Draft contract reads block scheduling and changed or missing approved contract sources fail closed.
  - Evidence: Policy compiles; legacy and representative producer/writer/consumer graphs normalize successfully; invalid-path branches are implemented for QA coverage.
- [x] T4 Add contract lifecycle transitions and CLI | owner: backend | scope: M | needs: T3 | files: .ai/harness/engine.py,.ai/harness/cli.py
  - Accept: Starting a contract writer marks its contracts draft and `approve-contract` records approver, current hash, and approval event.
  - Accept: Model prompts contain the bounded service and contract graph relevant to the task.
  - Evidence: Engine and CLI compile; all 12 pre-existing offline harness lifecycle tests pass.
- [x] T5 Project contract state for humans | owner: frontend | scope: S | needs: T2 | files: .ai/harness/projection.py
  - Accept: Generated plan and task views show hierarchy, services, contract status, task service/layer, and contract read/write sets without changing legacy task rendering semantics.
  - Evidence: Projection compiles and all 12 legacy harness tests pass with conditional multi-service rendering.
- [x] T6 Add offline contract-graph coverage | owner: qa | scope: M | needs: T3,T4,T5 | files: .ai/tests/test_harness.py
  - Accept: Tests cover valid multi-service scheduling, invalid ownership/writer dependencies, draft approval, stale hash blocking, writer invalidation, projections, and legacy compatibility.
  - Evidence: 17 offline harness tests pass, including five new multi-service lifecycle and corruption cases.
- [x] T7 Document contract-first workflow and gates | owner: documenter | scope: M | needs: T4,T5 | files: .ai/harness/README.md,.ai/modules/contracts.md,.ai/modules/INDEX.md,.ai/modules/gates.md,.ai/modules/planning/task-breakdown.md,.ai/ai.yaml
  - Accept: Documentation explains service/API/event/data/frontend/workflow/operations contracts, contract approval commands, and the contract-first scheduling rules.
  - Evidence: v0.7 README and contracts module document lifecycle, C1-C6 boundaries, hierarchy, context, limitations, and CLI usage.
- [x] T8 Update static module inventory validation | owner: qa | scope: S | needs: T7 | files: .ai/scripts/validate-kit.sh
  - Accept: Static validation recognizes the new routed contracts module and still fails on an unexpected module count.
  - Evidence: Validator requires exactly 23 non-index modules and reports the same count on success.

## Standard/Large Tail
- [x] T96 QA: run harness, legacy mechanics, and doctor suites | owner: qa | scope: S | needs: T6,T7,T8 | files: .project/multi-service-contracts/tasks.md,.project/multi-service-contracts/progress.md
  - Accept: `bash .ai/tests/run.sh`, `python3 .ai/tests/test_harness.py`, and `bash .ai/scripts/doctor.sh --full` exit zero.
  - Attempt 1: `bash .ai/tests/run.sh` failed because static validation expected 22 routed modules after `contracts.md` raised the correct count to 23; remediation split into T8.
  - Evidence: Attempt 2 passed 17 harness tests, 14 legacy mechanics assertions, static validation, synchronized skill projections, and `doctor.sh --full` with exit 0.
- [x] T9 Close service participation, dependency, symlink, and completed-contract policy gaps | owner: backend | scope: M | needs: T96 | files: .ai/harness/policy.py,.ai/harness/engine.py
  - Accept: A service can read only contracts it produces or consumes, and every cross-service consumer declares each producer as a dependency.
  - Accept: Contract sources with any symlink path component fail closed, and replans cannot remove or change contracts referenced by completed tasks.
  - Evidence: Policy/engine compile and all 17 existing tests pass after participant, producer-dependency, symlink-component, and completed-reference enforcement.
- [x] T10 Complete contract writer and deprecation lifecycle | owner: backend | scope: M | needs: T9 | files: .ai/harness/engine.py,.ai/harness/cli.py
  - Accept: A successful contract writer must actually mutate every declared contract source.
  - Accept: `deprecate-contract` records an explicit transition and prevents new scheduling against that contract.
  - Evidence: Engine/CLI compile; success now checks actual contract source mutations and explicit deprecation writes canonical state plus an audit event.
- [x] T11 Add remediation tests and align lifecycle documentation | owner: qa | scope: M | needs: T9,T10 | files: .ai/tests/test_harness.py,.ai/harness/README.md,.ai/modules/contracts.md
  - Accept: Offline tests reproduce and then reject all five G3 findings, while documentation matches the implemented transitions.
  - Attempt 1: 20/21 tests passed; completed-contract replan fixture accidentally completed the whole feature, so the engine correctly rejected replan before the target policy branch.
  - Evidence: Attempt 2 passed all 21 tests; regression cases cover every G3 finding and docs include actual-write and deprecation behavior.
- [x] T12 Re-run full validation after remediation | owner: qa | scope: S | needs: T11 | files: .project/multi-service-contracts/tasks.md,.project/multi-service-contracts/progress.md
  - Accept: Harness tests, legacy mechanics, static validation, and doctor full pass after remediation.
  - Evidence: 21 harness tests, 14 mechanics assertions, static validation, synchronized projections, and doctor full all pass.
- [x] T97 Review G3 across contract, security, correctness, consistency, and tests | owner: reviewer | scope: M | needs: T12 | files: .project/multi-service-contracts/tasks.md,.project/multi-service-contracts/decisions.md,.project/multi-service-contracts/progress.md
  - Accept: Review records an approve verdict with zero blocker or major findings, or creates explicit remediation tasks.
  - Review attempt 1: request changes; same-session self-review, not independent provider review.
  - Major: `.ai/harness/policy.py:296` does not require a task's service to participate in each contract it reads, and service manifests do not require consumer-to-producer dependencies.
  - Major: `.ai/harness/policy.py:406` preserves completed tasks while `.ai/harness/engine.py:124` replaces the contract registry, allowing historical contract references to disappear or change on replan.
  - Major: `.ai/harness/policy.py:116` rejects a symlink only at the final source path, so an internal symlink directory can bypass the documented fail-closed source rule.
  - Major: `.ai/harness/engine.py:378` accepts a successful contract-writer result when no declared source appears in the actual mutation set.
  - Major: `.ai/harness/schemas.py:99` declares `deprecated`, but engine/CLI provide no valid transition into that state.
  - Review attempt 2: same-session five-pass review found the five major findings remediated and no new major/blocker; this does not satisfy independent review.
  - Independent provider attempt: Claude Code 2.1.215 was invoked in plan/read-only mode, but authentication failed before inference because the OAuth session expired; no approval was recorded.
  - Policy transition: `.ai/config.json` disables independent review; attempt 2 is accepted as the required labeled active-agent five-pass review with zero major/blocker findings.
- [x] T98 Complete docs and release state | owner: release | scope: S | needs: T97 | files: .project/multi-service-contracts/plan.md,.project/multi-service-contracts/tasks.md,.project/multi-service-contracts/progress.md,.project/INDEX.md
  - Accept: Project index is done only after all acceptance criteria, validation, and review pass.
  - Evidence: Contract gates and remediation tests pass; configured active-agent G3 approves; plan, progress, and index are done.
