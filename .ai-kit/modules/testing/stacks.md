---
name: testing-stacks
description: Stack-specific testing reference; load only when this stack applies.
---

# Testing Reference: stacks

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
