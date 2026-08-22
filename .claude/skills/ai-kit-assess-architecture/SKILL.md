---
name: ai-kit-assess-architecture
description: Assess architecture for a non-trivial or cross-service AI-Kit change and record boundaries, dependencies, trade-offs, and risks without implementing it. Do not use for task sequencing, public contract authoring, or code review.
---

# AI-Kit Assess Architecture

Produce enough technical design for implementation owners to proceed without
inventing component boundaries or irreversible choices.

## Workflow

1. Identify the feature and whether the request is read-only analysis or an
   active planned change. Read the brief, plan, tasks, existing architecture,
   and only the source needed to trace affected dependencies.
2. Load `.ai/agents/architect.md`,
   `.ai/modules/context/dependency-analysis.md`, and existing code conventions.
   Also load `.ai/modules/contracts.md` for cross-service seams and
   `.ai/modules/database.md` when data ownership or schema design is involved.
3. Map current and proposed components, ownership, data flow, dependencies,
   trust boundaries, failure modes, non-functional requirements, and rollout or
   rollback constraints. Prefer established project patterns and identify drift.
4. Compare viable options when a material trade-off exists. Select the simplest
   option satisfying the requirements and record why alternatives were rejected.
5. For an active feature with G1 state, write only
   `.project/<feature>/architecture.md` and architecture decisions. For a
   read-only request, report the assessment without changing files.
6. Stop and return to planning when the design changes requirements, task
   ownership, a public contract, or an irreversible decision. Require user
   direction for unresolved product trade-offs or irreversible choices.

## Boundaries

- Do not write implementation code, migration files, tests, or public contract
  sources.
- Do not silently add dependencies or refactor unrelated architecture.
- An architecture assessment is not contract approval, QA evidence, or G3
  review.

## Output

State the recommended architecture, affected boundaries and owners, dependency
and data-flow impact, decisions and alternatives, risks with mitigations, and
any required replan or user decision.
