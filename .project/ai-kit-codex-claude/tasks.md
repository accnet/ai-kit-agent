# Tasks — ai-kit-codex-claude

Intent: refactor | Size: standard
Goal: Optimize AI-Kit for reliable Codex–Claude operation with lean context and enforceable repository checks.
Out of scope: API-based automatic model orchestration, production deployment, application/database changes
Open questions: none

## Tasks
- [x] T0 Capture the approved optimization brief | owner: researcher | scope: S | needs: - | files: features/ai-kit-codex-claude/brief.md
  - Accept: The committed brief preserves the user's requested outcome, constraints, and validation criteria without adding product scope.
  - Result: Approved Codex–Claude optimization requirements are now the regenerable intent source.
- [x] T1 Repair bootstrap and canonical process contracts | owner: architect | scope: M | needs: T0 | files: AGENTS.md,CLAUDE.md,.gitignore,.ai/ai.yaml,.ai/models.yaml,.ai/modules/**,.ai/templates/tasks.md,.project/INDEX.md,.project/ai-kit-codex-claude/architecture.md
  - Accept: A fresh Codex or Claude session reaches the same canonical rules without a missing required file.
  - Accept: All 22 routed modules have valid name/description frontmatter and the Git module contains executable workflow guidance.
  - Accept: Retry and QA/review ordering are internally consistent.
  - Result: Claude imports AGENTS.md; AGENTS is 478 words; all 22 modules pass metadata checks; Git guidance, retry policy, and QA→Review order are restored.
  - Review fix: module routing no longer loads gates, intent analysis, or workspace guidance for unrelated read-only requests.
- [x] T2 Migrate reusable workflows to Agent Skills | owner: backend | scope: M | needs: T1 | files: .ai/skills/**,.agents/skills/**,.claude/skills/**,.ai/commands/**,.claude/commands/**,.ai/scripts/sync-skills.sh
  - Accept: plan, implement, review, and status exist as valid canonical skills and identical Codex/Claude projections.
  - Accept: Codex and Claude expose namespaced skills without relying on deprecated custom prompts or aliases that collide with built-in commands.
  - Result: Four canonical skills pass quick_validate; Codex and Claude projections are byte-identical; documentation shims point to the namespaced skills.
  - Review fix: projection checking also rejects stale generated AI-Kit skill directories.
  - Review fix: removed legacy Claude command aliases whose names collide with host built-ins.
- [x] T3 Add deterministic repository enforcement | owner: backend | scope: M | needs: T1,T2 | files: .ai/scripts/doctor.sh,.ai/scripts/validate-kit.sh,.ai/scripts/check-gates.sh,.githooks/pre-commit,.github/workflows/gates.yml,.ai/modules/gates.md
  - Accept: One local command detects missing bootstrap files, malformed module metadata, skill drift, NUL bytes, and invalid shell syntax.
  - Accept: Pre-commit and CI invoke repository-native checks that actually ship in the kit.
  - Result: doctor validates bootstrap, metadata, projections, NULs, contradictions, and shell syntax; shipped hook/CI run G4 and configured tests; gate docs now distinguish mechanical from workflow enforcement.
  - Review fix: NUL scanning is limited to AI-Kit-owned text paths and deprecated-text detection no longer requires ripgrep.
- [x] T4 Add fixture-based script tests | owner: qa | scope: M | needs: T3 | files: .ai/tests/**
  - Accept: Tests verify task claiming, dependency unblocking, JSON state, context packing, validator success, and skill projection consistency.
  - Result: `.ai/tests/run.sh` passes 10 assertions covering all acceptance scenarios, including filenames with spaces and workspace-leak rejection.
- [x] T5 Review the complete change (G3) | owner: reviewer | scope: M | needs: T4 | files: -
  - Accept: Contract, security, correctness, consistency, and tests passes report zero blocker or major findings.
  - Result: Approve with notes after fixing over-broad binary scanning, ripgrep dependency, stale projections, eager module routing, alias collisions, and missing intent source. No blocker/major findings remain; external Claude was not invoked.
- [x] T6 Finalize state and documentation | owner: documenter | scope: S | needs: T5 | files: .project/ai-kit-codex-claude/**,.project/INDEX.md,.ai/knowledge/decisions.md
  - Accept: tasks.md records evidence and verdict, progress is summarized, INDEX is done, and session state has no stale next action.
  - Result: Project decisions/progress and durable knowledge are current; INDEX and session state are finalized.

## Review verdict

Approve with notes — zero blocker or major findings. Validation: 22 module contracts, 4 canonical skills, 12 synchronized projections, 13 mechanics assertions, full doctor pass, YAML parse pass, and G4 `all` pass on a staged copy of the distribution. ShellCheck was unavailable; review was a separate reviewer-role pass in the same Codex session, not an external Claude invocation.
