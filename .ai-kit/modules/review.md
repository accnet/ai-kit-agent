---
name: review
description: Five-pass contract, security, correctness, consistency, and test review procedure.
---

# Module: Review

## Purpose
Review procedure and severity model. Review is mandatory (`rules.yaml`:
`review_required`); reviewer separation is configurable (`.ai-kit/config.json`).

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
- Read `review.independent_enabled` from `.ai-kit/config.json`. When false, perform
  and label an `active-agent` review; unavailable Claude/Codex separation is not
  a blocker. When true, use a provider different from the implementer for an
  `independent` review unless the user explicitly selects the supported
  active-agent override.
- Changing reviewer separation never skips QA, evidence coverage, or any of the
  five review passes.
- Treat compact `evidence_view` as a self-contained projection of canonical
  evidence. Reported criterion PASS, manual inspection, and harness check PASS
  are distinct; do not infer coverage from a global suite result or historical
  evidence. Every required criterion and unresolved finding must remain visible.
- Resolve the workspace-relative package manifest and verify its hash/file
  attribution before following artifact references. Inspect full redacted
  `task.json` when bounded details are insufficient; open raw logs only for
  needed diagnosis. Missing/stale/unsafe evidence blocks a new passing review.
  Isolated packages must remain accessible without granting wider permissions.
- Inspect existing command/artifact evidence against the reviewed snapshot and
  acceptance criteria before rerunning tests. Another complete suite is warranted
  by changed inputs, missing/stale evidence, or a concrete finding, not merely by
  entering review. Worker evidence does not replace integrated regression or the
  harness's independent verification. All five passes remain mandatory.
- `quality.review` may route the harness review command to Codex CLI or Claude
  CLI with its pinned model. Provider selection does not imply independent
  review; the effective policy and implementation-provider comparison remain
  authoritative.

## Output
Verdict (approve / request changes) + findings list, recorded in tasks.md.

## Remediation handoff

Major/blocker findings must be handed to the coordinator as a remediation
record containing source task, exact criterion, severity, reproduction,
affected files, and suggested owner. The coordinator chooses a bounded retry
when the finding stays within the task scope; otherwise the coordinator adds a
new linked fix task during replan. Reviewers never edit `state.json` or
`tasks.md`, and a finding is closed only after the fix passes QA/G2 and review/G3.
