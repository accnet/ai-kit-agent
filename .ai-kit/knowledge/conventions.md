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

## Harness structured-payload hashing uses `policy.py`'s `canonical_digest`
- Rule: To hash an in-memory structured (dict/list) payload anywhere in `.ai-kit/harness/`, reuse `policy.py`'s `canonical_digest(value)` (`"sha256:" + hex(sha256(json.dumps(value, sort_keys=True, separators=(",",":"))))`) — the same function `plan_revision_digest`/`task_action_digest` already use. Reserve `qa_report.py`'s `sha256_and_readback` for hashing bytes already on disk (a file), not an in-memory structure.
- Because: Two similar-looking but subtly different hash conventions in the same codebase would make digests non-comparable across features for no reason; `canonical_digest` already existed and is exactly the right tool.
- Discovered: 2026-09-03, features/structured-user-input

## Harness CLI structured input uses `--<name>-file <path>`, not inline JSON
- Rule: A new `.ai-kit/harness/cli.py` subcommand that needs a structured (dict/list) argument should accept a JSON file path (e.g. `--answers-file <path>`), reading it with the existing `try: json.loads(Path(...).read_text()) except (OSError, json.JSONDecodeError): raise EngineError(...)` pattern (`cli.py`'s scripted-provider `--response <path>` flag is the original precedent) — never an inline `--<name>-json '<string>'` argument.
- Because: Inline JSON on a command line is fragile across bash/PowerShell quoting, especially nested quotes; this session hit exactly that class of problem repeatedly on unrelated shell commands before this rule was written down.
- Discovered: 2026-09-03, features/structured-user-input

## `.ai-kit/scripts/*.py` atomic writes must stay Python 3.9-safe
- Rule: Use `Path.write_bytes(content.encode("utf-8"))` for an atomic-write helper, not `Path.write_text(..., newline="\n")` — the `newline` keyword is Python 3.10+-only and raises `TypeError` on 3.9.
- Because: The kit's own runtime targets Python 3.9 (see the `ai-kit-agent-harness` dependency-free-runtime decision); a script that only ever ran under a newer interactive interpreter shipped a 3.10-only call that broke under the kit's actual floor.
- Discovered: 2026-09-03, features/project-knowledge-index

## New committed top-level directories need a `check-gates.sh` exemption
- Rule: When adding a new top-level directory meant to hold kit/plan documentation (or a projection of already-exempt content, e.g. quoting `.ai-kit/knowledge/`), add it to `check-gates.sh`'s `.workspace/`-mention exemption `case` list, alongside `.ai-kit/*`/`.project/*`.
- Because: The scan otherwise fails G4 on any file that merely *mentions* `.workspace/` as documentation text, even though only committing actual `.workspace/` content is the real hazard.
- Discovered: 2026-09-03, features/project-knowledge-index

## Full QA reporting is compact but coverage-preserving
- Rule: Use `.ai-kit/scripts/qa-report.sh --profile ai-kit|theme|browser|all` with an explicit profile to report existing QA commands. `all` keeps their fixed order, runs every selected command after a failure, and exits non-zero if any failed; reject missing, unknown, or duplicate profiles. Select `ai-kit` for kit-only regression and preserve all acceptance-required project coverage.
- Because: Compact local artifacts reduce agent-context tokens without making a changed-path guess that could omit a regression.
- Discovered: 2026-08-30, features/qa-token-optimization; explicit selection updated 2026-10-03, .project/test-quota-efficiency

## AI-Kit and project tests have separate roots
- Rule: Keep reusable harness/installer/DAG/profile tests in `.ai-kit/tests/`; put project suites in `/tests` with their own explicit manifest and runner.
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
- Rule: Declare cross-workstream barriers as `Feature dependencies: <feature-id>:<task-id>, ...`; a target is satisfied only when that task exists and is checked. Store reusable QA commands in `.ai-kit/qa-profiles.json` as argument arrays with a safe cwd, bounded timeout, and evidence metadata.
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
