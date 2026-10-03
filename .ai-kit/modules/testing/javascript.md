---
name: testing-javascript
description: Stack-specific testing reference; load only when this stack applies.
---

# Testing Reference: javascript

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
