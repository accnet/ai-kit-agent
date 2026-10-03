---
name: testing-express
description: Stack-specific testing reference; load only when this stack applies.
---

# Testing Reference: express

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
