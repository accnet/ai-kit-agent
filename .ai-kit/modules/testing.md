---
name: testing
description: Test selection and evidence standards. Load when writing or evaluating tests.
---

# Module: Testing

## Purpose
Testing standards across levels — unit and integration/E2E.

## When to Load
Every implementation task (unit level) and every QA task (integration/E2E level).

## Test Pyramid
- **Unit** — with every implementation task; fast, isolated, no I/O
- **Integration** — module boundaries: API + DB, service + queue; owned by QA, written per feature
- **E2E** — critical user paths only; few, stable, high-value

## Universal Rules
- Derive tests from acceptance criteria and map every criterion to observable
  test evidence.
- Prefer the smallest test level that proves the behavior: unit first,
  integration at module or service boundaries, and E2E only for critical user
  journeys.
- Keep unit tests deterministic and isolated: control time, randomness,
  environment variables, filesystem state, network, and external services.
- Cover error paths and boundary values (empty input, limits, invalid
  permissions, retries, and timeouts) as deliberately as the happy path.
- Preserve the repository's established test layout, naming, runner, and
  package scripts. Do not add a framework or install dependencies implicitly.

## Efficient Verification
- During implementation, run focused checks that prove the changed behavior.
  After the implementation dependency barrier, run all regression profiles
  required by the acceptance criteria. This does not waive QA or G3.
- Use `bash .ai-kit/scripts/qa-report.sh --profile ai-kit` for kit regression.
  Select project profiles explicitly when their runners and scope apply. There
  is no implicit `all`; explicit `all` still runs the full fixed matrix.
- Read the compact summary first. Open only the relevant failed-test artifact
  when diagnosis needs more detail. Do not replay successful raw logs into context.
- `doctor.sh --full` includes the complete kit suite. Avoid running it immediately
  after the same full suite on unchanged inputs merely to obtain another summary.
  Use focused doctor/configuration checks and Git QA for missing evidence.
- A new patch, integration of worker changes, changed tests/configuration/runtime,
  missing evidence, or a review finding can justify another run. Never reuse a
  different snapshot's pass, or skip checks explicitly required by acceptance.
- Treat missing executables/runners and environment setup failures as environment
  defects. Diagnose timeout limits before retrying; use a declared QA profile for
  long checks. Non-zero exits still require diagnosis, not automatic reruns.
- Record attempts through the existing coordinator policy. Do not change code to
  fix an environment error, retry flaky tests into green, or waive failing checks.
- Measure executed checks, duplicate declarations, and log/excerpt bytes from local
  manifests. Missing provider usage stays unknown; bytes are not token/quota counts.
- For compact prompt evidence, verify exact criterion coverage, manual/command
  linkage, current failures, not-run declarations, and artifact reconstruction
  from a fresh provider workspace. Test missing/stale/corrupt/unsafe artifacts
  and package mutation independently of repository mutation checks.
- Compare complete prompts on fixed baseline/compact fixtures, including retry
  and review calls, and disclose empty/tiny overhead and package bytes. The local
  benchmark is `python3 .ai-kit/tests/test_prompt_evidence.py --benchmark`; it does
  not call an LLM or authorize reuse of an earlier run's passing tests.

## Runner Precedence
Use this precedence when choosing how to run tests:

1. An existing project command (`package.json`, `Makefile`, `pyproject.toml`,
   `composer.json`, Maven/Gradle, `.csproj`, or equivalent).
2. A runner already declared by the project's manifest, lockfile, or test
   configuration.
3. The language's native runner.
4. If no safe runner can be identified, report the missing configuration rather
   than installing a package or inventing a command.

The command used, runtime and version, repository-relative working directory,
exit code, pass/fail summary, and acceptance-criteria mapping are required test
evidence. A passing command must exit with code 0. Shell wrappers are not
assumed to discover every language automatically; inspect their implementation
or manifest before relying on them.

## Stack References

Keep runner precedence and acceptance rules above for every task. Load only the
reference needed to select stack-specific checks:

| Situation | Reference |
|---|---|
| Language runner/level selection | `.ai-kit/modules/testing/stacks.md` |
| JavaScript unit-test conventions | `.ai-kit/modules/testing/javascript.md` |
| Node.js application checks | `.ai-kit/modules/testing/node.md` |
| Next.js application checks | `.ai-kit/modules/testing/next.md` |
| Express.js application checks | `.ai-kit/modules/testing/express.md` |

## Test Location and Naming
- Follow the repository's existing convention first; do not move tests merely to
  match this document.
- If no convention exists, use `tests/<stack>/` or `tests/<domain>/` and retain
  the suffix recognized by the selected runner:
  - JavaScript/TypeScript: `*.test.js`, `*.test.ts`, or `*.spec.ts`
  - Python: `test_*.py` or `*_test.py`
  - Go: `*_test.go`
  - Rust: module tests or `tests/*.rs`
  - PHP: `*Test.php`
  - Java/Kotlin: `*Test`
  - .NET: `*Tests`
- Keep tests close to the behavior they verify when the framework convention
  prefers colocated tests, but keep acceptance-to-test mapping in task evidence.

## Standards
- Tests derive from acceptance criteria, not from the implementation
- Each test: one behavior, clear name (`rejects_expired_token`, not `test2`)
- Deterministic: no real time, network, or randomness without control
- Error paths and edge cases (empty, limits, permissions) are mandatory, not stretch goals
- A test that never fails is a liability — verify it fails when the behavior breaks
- A failed QA criterion records reproduction, expected versus actual, severity,
  source task, affected files, and proposed owner. Major/blocker defects are
  coordinator remediation records; QA never fixes implementation code or marks
  the finding resolved.


## Checklist (per feature)
- [ ] Every acceptance criterion mapped to at least one test
- [ ] Unit tests paired with implementation tasks
- [ ] Integration tests at feature boundaries
- [ ] Flaky tests fixed at root cause or deleted, never retried into green

## Output
Tests committed to the suite; mapping criteria → tests noted in tasks.md.
