# Progress — configurable-independent-review

status: done
updated: 2026-08-22

## Implemented

- Canonical `.ai/config.json` keeps review required and disables independent
  reviewer separation by default.
- Harness initialization derives the configured policy and rejects independent
  review until the flag is manually enabled.
- Rules, model routing, review modules, harness docs, and synchronized Codex and
  Claude skills use the same configuration.
- Previously blocked git-qa and multi-service-contract features are complete
  under their recorded clean active-agent five-pass reviews.

## Validation

- Targeted harness suite: 23 tests pass.
- Static AI-Kit validation: pass.
- Full doctor: pass with 23 harness tests and 24 mechanics assertions.
- Git worktree QA: pass; repository hooks enabled and staged count remains zero.

## Review

Active-agent G3 attempt 1 requested changes: existing canonical states could
still enforce their recorded independent policy while the global flag was off,
and default reviewer routing/prompt wording still selected independent Claude
review. T5-T7 remedied those findings and repeated validation. Attempt 2 found
that canonical review records did not retain the effective policy used at
verdict time. T8-T10 added validated policy labels, projection coverage, and
final validation. Active-agent G3 attempt 3 approved with no remaining
major/blocker findings.
