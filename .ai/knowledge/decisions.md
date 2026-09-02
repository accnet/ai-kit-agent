# Decisions

Cross-feature architecture and technology decisions. One entry per decision, newest first.

Format:
```
## <YYYY-MM-DD> <decision title>
- Decision: <what was chosen>
- Because: <constraint or reason>
- Instead of: <rejected alternative, one line>
- Scope: <where this binds — module, stack, whole project>
- Source: features/<feature>
```

Rules: entries are append-only; a reversed decision gets a NEW entry linking the old one, the old entry is never edited. Only decisions that bind FUTURE work belong here — one-off choices stay in `.project/<feature>/decisions.md`.

## 2026-08-30 IDE-Native Parallel Orchestration Is Coordinator-Owned
- Decision: parallel implementation uses a versioned AI-Kit orchestration contract; Codex IDE owns native-worker scheduling and worktree creation, while AI-Kit validates DAG readiness, disjoint file scopes, worker manifests, and coordinator-owned transitions.
- Because: `.ai` cannot create native Codex workers or call a provider API; task-state writes must remain serialized and auditable.
- Instead of: workers self-editing `tasks.md`, sharing a worktree, or treating declarative JSON as an implicit scheduler.
- Scope: `.ai/config.json`, `.ai/scripts/`, coordinator protocol, and all future parallel workstreams.
- Source: user request and `.project/ai-kit-parallel-orchestration/`

## 2026-08-30 Grok CLI Is the Generic Implementation Provider
- Decision: `execution.task_cli` selects `grok` with no pinned model for generic harness implementation tasks; Codex remains the explicit planner/default primary identity and QA/review routes remain unchanged.
- Because: implementation task execution needs an opt-in Grok route without coupling it to planning or quality-provider policy.
- Supersedes: the Codex-only execution selection in “Codex CLI Task Execution Is Explicitly Configured”; legacy `execution.codex_cli` remains readable as a compatibility fallback.
- Scope: `.ai/harness/`, `.ai/config.json`, implementation skill, and operator workflow.
- Source: user request and `.project/grok-cli-implementer/`

## 2026-08-22 QA and Review CLI Routing Is Independently Configured
- Decision: `.ai/config.json` contains separate disabled-by-default QA and Review routes selecting `codex-cli`/`gpt-5.6-sol` or `claude-cli`/`claude-sonnet-5`
- Because: quality work may need a stronger or cross-model agent without coupling provider choice to normal implementation or silently invoking a billed service
- Boundary: QA routing applies only to harness tasks owned by QA; Review routing applies only to the review command; provider choice does not establish independent review
- Scope: harness quality routing, QA/Review skills, and G2/G3 operator workflow
- Source: user request and `.project/configurable-quality-cli-routing/`

## 2026-08-22 Codex CLI Task Execution Is Explicitly Configured
- Decision: `.ai/config.json` controls opt-in harness task execution through Codex CLI; when enabled, `step` selects only Codex and applies the configured `gpt-5.6-terra` model
- Because: model/provider routing must be durable, auditable, and mechanically enforced without making ordinary QA invoke a billed service
- Boundary: the policy applies only to top-level harness task dispatch; an already-selected Codex implementer never invokes a nested step
- Scope: harness `step`, implementation skill, and operator workflow
- Source: user request and `.project/codex-cli-task-execution/`

## 2026-08-22 Independent Review Is Explicitly Configured
- Decision: QA and G3 remain mandatory, while reviewer separation is controlled by `.ai/config.json`; `review.independent_enabled=false` is the fail-safe default and `true` must be set manually before independent review is required
- Because: local provider authentication or availability must not block otherwise complete work unless maintainers explicitly opt into that dependency
- Supersedes: the unconditional provider-separated-review part of the earlier harness control-plane decision; evidence coverage and five-pass review enforcement remain unchanged
- Scope: whole kit and harness initialization for new canonical feature states
- Source: user request and `.project/configurable-independent-review/`

---

## 2026-08-22 LLM-first runtime with deterministic control plane (supersedes advisory routing when harness is used)
- Decision: harness-managed features use Codex/Claude for reasoning and `state.json` plus sequenced events for machine state; the harness enforces approvals, scheduling, actual mutation scope, retry, provider-separated review, and recovery
- Because: intelligent plan/replan must remain model-driven while authorization, persistence, audit, and resume must fail closed and be testable offline
- Instead of: a hardcoded workflow engine, regex-parsed Markdown as canonical state, implicit provider calls, or trusting model-reported file changes
- Scope: `.ai/harness/` and every feature that opts into its runtime
- Source: features/ai-kit-agent-harness

## 2026-08-22 Canonical Agent Skills for Codex and Claude
- Decision: reusable AI-Kit workflows live in `.ai/skills/` and are generated byte-identically into `.agents/skills/` and `.claude/skills/`; model routing stays explicitly advisory without an orchestrator
- Because: both tools support progressively disclosed Agent Skills but use different repository discovery paths; generated projections are cross-platform and mechanically checkable
- Instead of: deprecated Codex custom prompts, collision-prone Claude command aliases, symlink-only wiring, or YAML that implies executable provider routing
- Scope: whole kit
- Source: features/ai-kit-codex-claude

## 2026-07-11 P6 revived: module frontmatter + INDEX + context-pack (supersedes "P6 dropped")
- Decision: all 22 modules carry frontmatter (name, description); modules/INDEX.md routes by situation; context-pack.sh emits deterministic tier-1 pack per task
- Because: module count grew, token cost became a stated priority (Retrieval Engine analysis), and "When to Load" inside the body forces reading the body to decide whether to read it
- Instead of: full retrieval engine (embeddings/vector index) — agentic search won for code in 2026; only the deterministic slice is precomputed
- Scope: .ai/modules/*, .ai/scripts/context-pack.sh
- Source: user directive, 2026-07-11

## 2026-07-11 Playbooks removed entirely (supersedes "Playbooks are SKILL.md-compatible")
- Decision: .ai/playbooks/ deleted. Stack conventions now come from: existing project code (canonical) → .ai/knowledge/conventions.md (learned) → Agent Skills installed in the host tool (ecosystem expertise)
- Because: user call — the Agent Skills ecosystem already ships maintained stack expertise (Stripe, framework, DB skills from vendors); duplicating it in-kit is maintenance burden; project code + learned conventions cover what's project-specific
- Instead of: maintaining 14 in-kit playbooks
- Scope: whole kit (all agents, modules, commands, pointer files updated)
- Source: user directive, 2026-07-11

## 2026-07-11 Multi-agent coordination: claim-by-commit, orchestrator = Planner
- Decision: parallel agents coordinate in two modes — tool-native (Agent Teams etc.) or repo-native claim-by-commit on tasks.md (push rejected = task taken); one worktree + `agent/<feature>-<task-id>` branch per task; Planner doubles as orchestrator (no 11th agent), never writes feature code while orchestrating; 3 safety checks (files disjoint, interface stable, no needs:) gate parallelization
- Because: kit is markdown-only — git itself must be the lock; orchestrator with clean context is the 2026 consensus pattern
- Instead of: lock files, a dedicated orchestrator agent, or tool-specific-only coordination
- Scope: whole project (git.md, planner.md, task-breakdown.md)
- Source: upgrade-2026 P5

## 2026-07-11 Playbooks are SKILL.md-compatible; repo is canonical for skills
- Decision: all playbooks carry Agent Skills frontmatter (name, description); export = copy as `<name>/SKILL.md` into a tool's skills dir; repo remains the canonical source, tool dirs are projections
- Because: Agent Skills is the AAIF open standard read by 32+ tools; repo-canonical keeps team + agents on one version
- Instead of: maintaining separate skill copies per tool
- Scope: .ai/playbooks/*
- Source: upgrade-2026 P2

## 2026-07-11 P6 (module INDEX / progressive disclosure) dropped
- Decision: no modules/INDEX.md, no module frontmatter — P6 cancelled by user
- Because: user call; AGENTS.md directory map + module "When to Load" sections cover routing adequately at current kit size (20 modules)
- Instead of: 20 frontmatter edits + INDEX table
- Scope: .ai/modules/
- Source: upgrade-2026 close-out

## 2026-07-11 Four-tier split: features/ (intent) vs .project/ (execution)
- Decision: features/ holds requirements+research (user + Researcher write only); .project/ holds plan/tasks/architecture/decisions/progress (agents write); tasks.md replaces todo.md; lifecycle via .project/INDEX.md metadata, not folder moves (except archive/)
- Because: separating intent from execution makes plans regenerable (change stack → delete .project/<x>, regenerate from features/<x>) and prevents feature folders becoming graveyards
- Instead of: original mixed layout (brief + todo + context in one folder); physical backlog/active/done folder moves (breaks paths/history)
- Scope: whole project
- Source: features/upgrade-2026 (P4.5)

## 2026-07-11 Canonical instruction entry point
- Decision: AGENTS.md is the single canonical rules file; tool files (CLAUDE.md, .cursor/rules, ...) are thin pointers
- Because: 28+ tools read AGENTS.md natively; duplicated rules drift
- Instead of: maintaining parallel per-tool rule files
- Scope: whole project
- Source: features/upgrade-2026
