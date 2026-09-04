# AI-Kit Core

AI-Kit is a chat-first, tool-neutral workflow for coding agents. This file contains only rules that must be available in every session. Reusable procedures live in Agent Skills and detailed guidance lives in `.ai-kit/modules/`.

## Sources of truth

| Tier | Purpose | Persistence |
|---|---|---|
| `.ai-kit/` | Maintained process, skills, scripts, and durable knowledge | committed |
| `features/` | User requirements and Researcher-owned research — WHAT | committed |
| `.project/` | Regenerable plans, tasks, decisions, and progress — HOW | committed |
| `.workspace/` | Session pointers and scratch state | local, gitignored |

Requirements discovered during implementation go back to the user or Researcher; do not bury them in `.project/`. Only the Researcher writes `features/`. Edit `.ai-kit/` only when the user explicitly requests a kit/process change.

## Session knowledge bootstrap

- At session start, check for `.knowledge-index/project-map.md` and `.knowledge-index/index.json`; if present, load only via the rule in `.ai-kit/modules/context/knowledge-loader.md`.
- Absent, empty, or invalid `.knowledge-index/` → fall back to `.ai-kit/knowledge/` directly; passive IDE file indexing is never sufficient bootstrap evidence.

## Route the request

- Answer, explain, review, diagnose, or report status: inspect relevant material and report; do not implement changes unless requested.
- Plan work: use the `ai-kit-plan` skill.
- Assess non-trivial architecture: use the `ai-kit-assess-architecture` skill.
- Design or revise a public cross-boundary contract: use the `ai-kit-design-contract` skill.
- Build, change, or fix ordinary application/tooling code: use the `ai-kit-implement` skill.
- Change database schema or data: use the `ai-kit-migrate-data` skill.
- Validate acceptance behavior as QA: use the `ai-kit-validate-quality` skill.
- Review completed work: use the `ai-kit-review` skill.
- Report project execution state: use the `ai-kit-status` skill.

## Native parallel orchestration

When `.ai-kit/config.json` sets `orchestration.enabled=true`, Codex IDE remains the scheduler and worker
factory; `.ai-kit` only validates this protocol. The coordinator must:

1. Run `.ai-kit/scripts/dag.py <feature> --json`.
2. Verify `needs`, declared `files`, contract approval, and ownership before dispatch.
3. Spawn at most `orchestration.max_workers` native workers, each with one task and an isolated worktree.
4. Give each worker exactly its declared task and file scope.
5. Keep task-state ownership centrally: workers must not edit `tasks.md`, claim another task, commit,
   push, or spawn nested workers.
6. Record claim/completion/retry/rejection state only after validating the worker result.
7. Run QA and G3 only after the implementation dependency barrier is complete.

Workers must return evidence and patches through their IDE-supplied worktree. The `.ai-kit` scripts never
call an LLM API or create native workers. Any dependency cycle, missing dependency, file-scope overlap,
shared/dirty worktree, contract mismatch, or ownership violation fails closed.

If a session resumes active work, read `.workspace/session.md` first. Otherwise, do not load process files speculatively; load only the selected skill, current task contract, target files, and directly relevant modules.

## Planning and completion

- Standard or large changes require `.project/<feature>/tasks.md` with binary acceptance criteria before implementation (G1).
- For harness-managed features, `.project/<feature>/state.json` is canonical; `tasks.md` is a generated projection and is legacy-compatible only when canonical state is absent.
- A change is trivial only when it touches at most two files, changes no database data/schema, dependency, or contract, and is reversible with one revert. Trivial work may use the skill's inline checklist.
- Any database change is never trivial and always requires a full plan.
- Close a task only when its acceptance criteria pass and relevant tests/lint/typecheck succeed (G2).
- QA validation and G3 review remain required. Reviewer separation is controlled by `.ai-kit/config.json`: with `review.independent_enabled=false`, the active agent performs and labels the five-pass review; set the flag to `true` manually before requiring an independent provider.
- Legacy features use `tasks.md` as execution state. Harness-managed features use versioned `state.json`; `plan.md` and `tasks.md` are generated views.

## Safety and scope

- Follow existing project code patterns; report drift instead of refactoring unrelated code.
- Do not expand beyond the user's requested scope or perform external writes merely because a tool is available.
- Destructive or hard-to-recover actions, production deploys, force-pushes, and irreversible migrations require explicit user approval for the specific action (G5).
- Never commit `.workspace/`, secrets, or credentials. Run repository checks before any requested commit (G4).
- Provider calls are opt-in through `.ai-kit/scripts/harness.sh`. In `.ai-kit/config.json`, `execution.task_cli.enabled=true` opts generic implementation tasks into its configured provider (Grok in this repository), while `quality.qa.enabled` and `quality.review.enabled` independently opt QA and Review into their selected CLI. Planning still requires an explicit provider. A worker already selected by the harness performs its injected task or review directly and never invokes its route recursively.

## Runtime harness

For durable LLM-driven execution, follow `.ai-kit/harness/README.md`. Models own planning, replanning, implementation strategy, and evidence synthesis. The harness owns structured state, context retrieval, approvals, scheduling, actual file-scope verification, retries, configured reviewer-separation enforcement, and recovery. Large plan revisions and risky tasks stop for explicit approval.

## Layout

```text
.ai-kit/agents/       role contracts loaded on demand
.ai-kit/skills/       eight canonical planning, design, execution, QA, review, and status workflows
.ai-kit/modules/      conditional process and engineering references
.ai-kit/scripts/      deterministic state, sync, and gate mechanics
.ai-kit/harness/      provider-neutral state, memory, policy, and orchestration runtime
.ai-kit/tests/        dependency-free mechanics tests
features/<x>/     requirements and research
.project/<x>/     plan, tasks, architecture, decisions, progress
.workspace/       local session state
```

Definition of Done: acceptance criteria met, validation passes, required review approves, and project task/index state is current.
