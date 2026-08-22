---
name: review
description: Five-pass contract, security, correctness, consistency, and test review procedure.
---

# Module: Review

## Purpose
Review procedure and severity model. Review is mandatory (`rules.yaml`:
`review_required`); reviewer separation is configurable (`.ai/config.json`).

## When to Load
Every Reviewer task; engineers may load it for self-review before handoff.

## Review Passes (in order)
1. **Contract** — does the diff satisfy the task's acceptance criteria and the Architect's contracts?
2. **Security** — injection, authz per endpoint, secrets in code, unsafe deserialization, input trust
3. **Correctness** — edge cases, error paths, concurrency, off-by-one, resource cleanup
4. **Consistency** — project conventions, naming, dead code, debug leftovers
5. **Tests** — do tests actually verify the criteria, or just execute the code?

## Severity Model
- **Blocker**: security hole, data loss, broken contract, failing tests → must fix
- **Major**: wrong edge-case behavior, missing error path, untested criterion → fix before merge
- **Minor**: naming, style, docs → note, don't block

## Rules
- Findings reference file:line, state why, and suggest a fix — "this is bad" is not a finding
- Review the diff in codebase context; a correct diff can still break a caller
- Approve-with-notes is valid for minor-only findings
- Read `review.independent_enabled` from `.ai/config.json`. When false, perform
  and label an `active-agent` review; unavailable Claude/Codex separation is not
  a blocker. When true, use a provider different from the implementer for an
  `independent` review unless the user explicitly selects the supported
  active-agent override.
- Changing reviewer separation never skips QA, evidence coverage, or any of the
  five review passes.
- `quality.review` may route the harness review command to Codex CLI or Claude
  CLI with its pinned model. Provider selection does not imply independent
  review; the effective policy and implementation-provider comparison remain
  authoritative.

## Output
Verdict (approve / request changes) + findings list, recorded in tasks.md.
