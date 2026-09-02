# Conventions

Project-specific conventions learned during work — unique to THIS codebase. Primary convention source alongside the code itself. Newest first.

Format:
```
## <convention title>
- Rule: <what to do>
- Because: <why — one line>
- Discovered: <YYYY-MM-DD>, features/<feature>
```

Rules: existing project code wins over any written convention when they conflict — fix the entry, not the code. Keep entries short — this file is loaded often.

---

## Full QA reporting is compact but coverage-preserving
- Rule: Use `.ai/scripts/qa-report.sh --profile ai-kit|theme|browser|all` (default `all`) to report existing QA commands. `all` keeps their fixed order, runs every selected command after a failure, and exits non-zero if any failed; reject unknown or duplicate profiles.
- Because: Compact local artifacts reduce agent-context tokens without making a changed-path guess that could omit a regression.
- Discovered: 2026-08-30, features/qa-token-optimization

## AI-Kit and project tests have separate roots
- Rule: Keep reusable harness/installer/DAG/profile tests in `.ai/tests/`; put project suites in `/tests` with their own explicit manifest and runner.
- Because: Syncing AI-Kit must never carry a theme's regression tests into another repository, while explicit manifests still prevent stale suites from re-entering QA.
- Discovered: 2026-08-30, features/ai-kit-v2-test-cleanup

## Session pointers are advisory until validated
- Rule: A session feature must be active in `.project/INDEX.md` and its task must still be open; stale pointers fail doctor checks.
- Because: `.workspace/session.md` can outlive a rolled-back or superseded feature.
- Discovered: 2026-08-30, features/ai-kit-optimization

## Native workers require isolated worktrees
- Rule: When orchestration requires per-worker worktrees, `execution.isolated_worktree.required` must also be true.
- Because: Contradictory flags permit parallel workers to share and corrupt a worktree.
- Discovered: 2026-08-30, features/ai-kit-optimization

## QA commands declare their working directory
- Rule: Record command, cwd, timeout, and whether evidence is required in the task/QA record; portable profiles should use `.` when an optional test directory may not exist in a freshly bootstrapped project.
- Because: Running an E2E command from the wrong directory produces a false failure or incomplete coverage.
- Discovered: 2026-08-30, features/ai-kit-optimization

## Cross-feature barriers and QA profiles
- Rule: Declare cross-workstream barriers as `Feature dependencies: <feature-id>:<task-id>, ...`; a target is satisfied only when that task exists and is checked. Store reusable QA commands in `.ai/qa-profiles.json` as argument arrays with a safe cwd, bounded timeout, and evidence metadata.
- Because: A single-feature DAG cannot otherwise prevent dispatch before a baseline workstream is complete, and free-form QA commands can run from the wrong directory.
- Discovered: 2026-08-30, features/ai-kit-cross-feature-qa-hardening

## Canonical cross-feature barriers fail closed
- Rule: Canonical plans resolve declared feature dependencies from target `state.json` when present, otherwise legacy `tasks.md`; malformed state, cycles, and incomplete targets block every local task.
- Because: A generated Markdown view must never override canonical execution state or allow a dependent feature to start early.
- Discovered: 2026-08-30, features/ai-kit-harness-contract-v016

## QA/review findings are coordinator-owned
- Rule: Record a failed criterion before retrying or replanning; same-scope defects retry the source task, while scope-expanding defects use a uniquely linked fix task.
- Because: A provider or worker must not silently rewrite execution history, and every fix needs a new G2/G3 evidence trail.
- Discovered: 2026-08-30, features/ai-kit-remediation-loop

(empty — first real feature will populate this)
