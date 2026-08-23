# Progress — portable-installer

status: complete
release: 0.15.0
updated: 2026-08-22

## Delivered

- Added a self-contained `.ai/install/install.sh` with `--check` and `--no-git`.
- Added manifest-driven root templates for agent entry rules, Claude routing, Git
  QA hook, GitHub gates, project index, and required ignore entries.
- Added preflight protection for drifted files, symlinks, invalid parents, duplicate
  or escaping manifest destinations, and an invalid copied-kit location.
- Reused canonical skill projection and repository-local Git QA setup; no provider,
  global Git, staging, commit, push, or deployment behavior was introduced.
- Added eight disposable-project regression groups, including paths with spaces,
  repeat/check flows, conflict atomicity, external symlink preservation, path
  escape rejection, no-Git mode, and real local Git initialization without HEAD.
- Added distribution/template integrity checks and operator documentation.

## Validation so far

- `bash .ai/tests/test_install.sh` — pass, 8 groups.
- `bash .ai/scripts/validate-kit.sh` — pass.
- `bash -n .ai/install/install.sh .ai/tests/test_install.sh` — pass.
- `git diff --check` — pass.

## Remaining gates

None.

## Review findings

- Major — `.ai/install/install.sh:171`: read-only `--check` delegates to
  `validate-kit.sh`, whose explicit `py_compile` creates ignored `__pycache__`
  content. Replace the syntax probe with a no-write compilation path and assert a
  before/after filesystem digest in the installer suite.
- Major — `.ai/install/install.sh:192-198`: appending required entries directly to
  a non-empty `.gitignore` without a terminal newline joins the first entry to the
  existing last line. Insert one separator newline only when required and add a
  preservation/deduplication regression.

Both findings were resolved in T5. G3 pass 2 reviewed the final diff in the order
Contract → Security → Correctness → Consistency → Tests and approved it with zero
remaining findings under the configured active-agent policy.

## Release

Release verdict: go for the repository state at v0.15.0. This is an additive local
tooling release with no schema, dependency, production deployment, or external
state change. Rollback is a normal revert of the installer, test, validation, and
documentation changes; already bootstrapped projects contain plain reviewable
files and require no data rollback.

## Deviations and limitations

No architecture deviation. Installation requires Bash plus the kit's ordinary
utilities; it does not provide a native PowerShell flow or install dependencies.
An interruption after managed files are copied but before a later helper finishes
is recovered by correcting the reported cause and rerunning the idempotent install.
