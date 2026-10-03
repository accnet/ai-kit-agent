---
name: testing-node
description: Stack-specific testing reference; load only when this stack applies.
---

# Testing Reference: node

### Node.js applications
- Test pure functions, parsers, configuration, and service logic as unit tests
  with `node:test` and `node:assert/strict`.
- Test filesystem, child-process, or other I/O adapters at the integration
  boundary with temporary resources and explicit cleanup. Keep network calls
  stubbed unless the acceptance criterion is specifically an external
  integration.
- Example command: `node --test "tests/js/node/**/*.test.js"` (or the project's
  configured script when available).
