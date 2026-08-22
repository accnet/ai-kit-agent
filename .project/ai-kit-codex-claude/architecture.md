# Architecture — Codex–Claude AI-Kit v0.5

## Components

- `AGENTS.md`: lean, tool-neutral invariants loaded by Codex and imported by Claude.
- `CLAUDE.md`: one-line Claude bootstrap importing `AGENTS.md`.
- `.ai/skills/`: canonical workflow skills; no tool-specific behavior in their bodies.
- `.agents/skills/` and `.claude/skills/`: generated, byte-identical discovery projections.
- `.ai/modules/`: conditional reference material with valid routing metadata.
- `.ai/scripts/`: deterministic state, validation, synchronization, and gate mechanics.
- `.ai/tests/`: dependency-free shell fixtures validating the shipped mechanics.

## Contracts

1. Canonical skills are the only editable workflow source; projections must match byte-for-byte.
2. Always-on instructions contain invariants, not multi-step procedures.
3. Model routing is advisory until an external orchestrator consumes the configuration.
4. Documentation may claim mechanical enforcement only for files and checks that ship in the repository.
5. Task state remains human-readable Markdown in the existing parseable line format.

## Data flow

User request → AGENTS/CLAUDE bootstrap → matching AI-Kit skill → routed role/modules → task state/scripts → tests and review.

## Risks and mitigations

- Tool discovery paths differ → generate projections from one canonical source and check them in CI.
- Markdown state is regex-parsed → retain the constrained format and cover it with fixtures.
- Cross-model review can add latency → require it for standard/large or high-risk work, not trivial changes.
- Prompt rules are not hard enforcement → keep security/destructive boundaries in hooks, scripts, and platform permissions where possible.
