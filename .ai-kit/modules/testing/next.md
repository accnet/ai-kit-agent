---
name: testing-next
description: Stack-specific testing reference; load only when this stack applies.
---

# Testing Reference: next

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
