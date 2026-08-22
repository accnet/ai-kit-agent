# Tasks — specialized-lifecycle-skills

Intent: feature | Size: standard
Goal: Add four non-overlapping lifecycle skills with enforceable safety boundaries.
Out of scope: delivery attestation, aliases, provider configuration, real migrations
Open questions: none

## Tasks

- [x] T1 Create specialized canonical skill contracts | owner: architect | scope: M | needs: - | files: .ai/skills/ai-kit-assess-architecture/SKILL.md,.ai/skills/ai-kit-design-contract/SKILL.md,.ai/skills/ai-kit-migrate-data/SKILL.md,.ai/skills/ai-kit-validate-quality/SKILL.md,.ai/skills/ai-kit-implement/SKILL.md
  - Accept: Each new skill has a discriminating trigger, explicit exclusions, bounded writes, stopping conditions, outputs, and routes only to existing AI-Kit agents/modules.
  - Accept: Architecture does not implement, contract design cannot self-approve, migration cannot infer permission for real/destructive environments, and QA cannot fix application code or issue a G3 verdict.
  - Accept: Generic implementation explicitly yields to the four specialized workflows.
  - Evidence: Four concise canonical skills define disjoint routing, permissions, stopping conditions, and outputs; generic implementation routes Architect/public-contract/Database/QA owners to them.
- [x] T2 Integrate discovery, version, and static validation | owner: documenter | scope: S | needs: T1 | files: AGENTS.md,.ai/ai.yaml,.ai/scripts/validate-kit.sh
  - Accept: The canonical workflow list documents eight lifecycle/utility skills, AI-Kit version advances, and validation requires the exact eight canonical skill names.
  - Evidence: `AGENTS.md` exposes all eight routes, AI-Kit is v0.11.0, and static validation requires the exact eight-name registry.
- [x] T3 Synchronize Codex and Claude projections | owner: documenter | scope: S | needs: T1,T2 | files: .agents/skills/ai-kit-assess-architecture/SKILL.md,.agents/skills/ai-kit-design-contract/SKILL.md,.agents/skills/ai-kit-migrate-data/SKILL.md,.agents/skills/ai-kit-validate-quality/SKILL.md,.agents/skills/ai-kit-implement/SKILL.md,.claude/skills/ai-kit-assess-architecture/SKILL.md,.claude/skills/ai-kit-design-contract/SKILL.md,.claude/skills/ai-kit-migrate-data/SKILL.md,.claude/skills/ai-kit-validate-quality/SKILL.md,.claude/skills/ai-kit-implement/SKILL.md
  - Accept: Both discovery trees are byte-identical to the canonical skill source and contain no stale AI-Kit skill.
  - Evidence: Sync and check mode pass; canonical, Codex, and Claude trees each contain the same eight AI-Kit skills.

## Standard Tail

- [x] T96 Validate all skills and run full offline QA/Git checks | owner: qa | scope: S | needs: T1,T2,T3 | files: .project/specialized-lifecycle-skills/tasks.md,.project/specialized-lifecycle-skills/progress.md
  - Accept: Bundled quick validation passes for all eight skills; static validation, full tests, doctor and Git worktree QA exit zero.
  - Evidence: Eight quick validations pass; doctor full exits zero with 27 harness tests, 24 mechanics assertions, static validation, synchronized projections, Git worktree QA, and staged=0.
- [x] T97 Review G3 under configured active-agent policy | owner: reviewer | scope: M | needs: T96 | files: .project/specialized-lifecycle-skills/tasks.md,.project/specialized-lifecycle-skills/progress.md
  - Accept: Contract/Security/Correctness/Consistency/Tests review finds zero remaining major/blocker issues.
  - Evidence: Active-agent five-pass review approves with zero findings; trigger collision, bounded writes, approval separation, destructive migration, QA/G3 separation, and projection integrity were verified.
- [x] T98 Complete release state | owner: release | scope: S | needs: T97 | files: .project/specialized-lifecycle-skills/plan.md,.project/specialized-lifecycle-skills/tasks.md,.project/specialized-lifecycle-skills/progress.md,.project/INDEX.md
  - Accept: Feature/index state is done only after G2/G3 pass and `attest-delivery` remains explicitly deferred.
  - Evidence: G2/G3 pass, plan/progress/index are done, eight skills ship, and no `attest-delivery` skill exists.
