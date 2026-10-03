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

## Language / Stack Matrix

| Language or stack | Unit focus | Integration focus | System / E2E focus | Runner default |
|---|---|---|---|---|
| JavaScript / Node.js | Pure functions, parsers, services | HTTP, filesystem, process adapters | Critical service workflow | `node:test` + `node:assert/strict` |
| TypeScript | Typed domain and utility logic | Module/API boundaries | Application workflow | Existing Vitest/Jest/`tsx` setup; native runner when configured |
| Next.js / React | Utilities, validation, Server Actions | Route/data/cache boundaries | Navigation and rendered journeys | Existing Jest/Vitest + Testing Library; Playwright for browser E2E |
| Express.js | Middleware, controllers, serializers | Real HTTP routes and auth wiring | API workflow | `node:test` + `fetch`; Supertest only if approved/already present |
| Python | Functions, classes, services | DB, HTTP, queue adapters | Critical user/service flow | `pytest`; `unittest` when that is the project convention |
| PHP | Domain and service classes | HTTP, DB, framework boundaries | Critical web flow | PHPUnit or the configured framework runner |
| Go | Package and handler logic | DB, transport, external adapters | Service/system workflow | `go test ./...` |
| Rust | Module and pure function logic | Async, network, persistence boundaries | Binary/service workflow | `cargo test` |
| Java / Kotlin | Class and service logic | API, DB, messaging boundaries | Application workflow | Maven or Gradle test task |
| C# / .NET | Class and service logic | ASP.NET/API and DB boundaries | Critical endpoint flow | `dotnet test` |
| Ruby | Methods, services, jobs | Rails/controller/DB boundaries | Critical user flow | Existing RSpec or `rake test` setup |
| Shell | Functions and branch behavior | CLI, filesystem, process effects | Deployment/automation path | Existing Bats or project script; ShellCheck is static analysis |
| SQL / migrations | Query, constraint, and function behavior | Migration, rollback, and fixtures | Disposable database workflow | Project DB harness or database-native test tooling |

The matrix is guidance, not a claim that every repository contains every stack.
For a framework not listed here, follow the same unit → integration → E2E
boundary model and the runner-selection precedence above.

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

## JavaScript / Node.js Testing (Frontend and Backend)
- **Runner**: Use Node.js Native Test Runner (`node --test`) and the built-in
  `node:assert` module. Target Node.js 18 or newer; do not add npm packages
  solely for unit-test execution.
- **Location and naming**: Place tests under `tests/theme-builder/*.test.js`
  or `tests/js/*.test.js`. Name files `*.test.js` so Node's test discovery can
  find them.
- **Test structure**: Import `test` (and `describe`/`it` when useful) from
  `node:test`; use strict assertions from `node:assert/strict`. Keep tests
  isolated and map each test to one acceptance-criteria behavior.
- **Running tests**: Run a complete JavaScript suite with `node --test
  "tests/**/*.test.js"`, or run one file directly with `node --test
  tests/theme-builder/example.test.js`. Use the repository's configured test
  script when one exists, but do not assume a shell runner discovers JavaScript
  files automatically.
- **Evidence**: A successful run must exit with code 0. Record the command and
  result in the task evidence; failures must include the failing test name and
  expected versus actual behavior.
- **Scope**: Prefer pure unit tests for Theme Builder logic. Mock browser or
  external APIs at the boundary; do not require a real browser, network, clock,
  or random source for deterministic tests.

### Node.js applications
- Test pure functions, parsers, configuration, and service logic as unit tests
  with `node:test` and `node:assert/strict`.
- Test filesystem, child-process, or other I/O adapters at the integration
  boundary with temporary resources and explicit cleanup. Keep network calls
  stubbed unless the acceptance criterion is specifically an external
  integration.
- Example command: `node --test "tests/js/node/**/*.test.js"` (or the project's
  configured script when available).

### Next.js applications
- Test shared utilities, validation, data-fetching helpers, and Server Action
  logic with the Node.js runner when they do not require a browser or React
  renderer.
- For React Client Components, hooks, DOM behavior, and accessibility, use the
  Next.js project's existing Jest/Vitest + Testing Library setup. Do not replace
  an established framework runner with `node --test`.
- Cover critical navigation and rendered user journeys with the project's
  configured browser E2E runner (for example, Playwright) when one exists.
  Mock server actions and external APIs at unit level; reserve live services for
  integration/E2E tests.
- Keep tests near the established project convention; otherwise use
  `tests/js/next/**/*.test.js` for Node-level tests and
  `tests/js/next/**/*.spec.js` for framework/browser tests.

### Express.js applications
- Unit-test middleware, controllers, serializers, and services independently;
  pass plain request/response doubles when that is sufficient.
- For route integration tests, start the Express app on an ephemeral port and
  call it with the built-in `fetch` available in Node.js 18+. Always close the
  server in teardown, and assert status, headers, and response body.
- Use Supertest only when it is already an approved project dependency or when
  the task explicitly adds it; it is not required for basic HTTP route tests.
- Example location: `tests/js/express/**/*.test.js`. Keep authentication,
  database, and third-party boundaries mocked in unit tests and cover their
  wiring in focused integration tests.

## Checklist (per feature)
- [ ] Every acceptance criterion mapped to at least one test
- [ ] Unit tests paired with implementation tasks
- [ ] Integration tests at feature boundaries
- [ ] Flaky tests fixed at root cause or deleted, never retried into green

## Output
Tests committed to the suite; mapping criteria → tests noted in tasks.md.
