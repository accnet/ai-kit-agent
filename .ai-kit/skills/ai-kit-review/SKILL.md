---
name: ai-kit-review
description: Review an AI-Kit task or diff against acceptance criteria using contract, security, correctness, consistency, and test passes. Use for review requests, not implementation unless fixes are separately requested.
---

# AI-Kit Review

Deliver an evidence-backed G3 verdict without silently fixing the reviewed work.

## Workflow

1. Determine the exact diff and feature/task being reviewed. Read its acceptance criteria, any architecture contracts, `review.independent_enabled`, and `quality.review` from `.ai-kit/config.json`.
2. Load `.ai-kit/agents/reviewer.md`, `.ai-kit/modules/review.md`, relevant target files, direct callers, and paired tests.
3. Review in this order: Contract → Security → Correctness → Consistency → Tests.
4. For every finding, provide severity, tight file/line location, impact, and a concrete correction.
5. Request changes for any blocker or major finding. Approve only when none remain; minor-only notes may approve.
6. Record the verdict in `tasks.md` when the review belongs to an active AI-Kit feature. Convert blocker/major findings into owned tasks.

QA and G3 are mandatory in both modes. When `review.independent_enabled` is `false`, perform the five passes as the active agent, label the verdict `active-agent`, and do not block on a second provider. When the flag is manually set to `true`, use a provider different from the implementer for an `independent` verdict unless the user explicitly selects the supported active-agent override. Never represent active-agent review as independent.

At a top-level harness-managed review, `quality.review.enabled=true` authorizes `.ai-kit/scripts/harness.sh review <feature> <task>` with the configured quality CLI/model. If the current prompt already identifies this process as the harness-selected reviewer, review directly and never invoke another review command. CLI selection does not establish independence; the effective review policy remains authoritative.

## Output

Lead with findings in severity order, then give the verdict and residual test/coverage gaps. If there are no findings, say so explicitly and state what was verified.
