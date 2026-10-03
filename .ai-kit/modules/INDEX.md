# Module Index

Route from this table — read a module's body only when this index says it applies. Every module carries matching frontmatter (name, description).

## Workflow Entry
| Module | Why |
|---|---|
| gates.md | Load for planning, mutation, completion review, commit, or destructive-operation decisions |
| planning/intent-analysis.md | Load when plan/implement must classify a new request; skip for read-only answers and known active tasks |

## Per Phase
| Situation | Load |
|---|---|
| Resume active work / task switch / end handoff | workspace.md |
| Planning a feature/refactor | planning.md → task-breakdown.md → acceptance.md → planning/planning.md |
| Starting any task (building context) | context.md → context-loader.md → [dependency-analysis.md if modifying existing code] → context-ranking.md → token-budget.md → context-assembler.md |
| Task touches domain logic / money / permissions | context/knowledge-loader.md |
| Ambiguous requirement/design trade-off needing a user decision on a durably tracked run | planning/ask-question.md |
| Before any commit | git.md |
| Agents running in parallel | git.md (Worktrees & Parallel Agents) |
| Multiple services, public APIs/events, shared workflows, or data ownership | contracts.md |
| IDE-native parallel task orchestration | orchestration.md → contracts.md → testing.md |
| Review / self-review before handoff | review.md |

## Per Intent / Owner
| Situation | Load |
|---|---|
| Intent = bug | debugging.md |
| Intent = refactor | refactoring.md |
| Task owner = backend | backend.md |
| Task owner = frontend | frontend.md |
| Task touches schema / owner = database | database.md |
| Writing tests (any task) | testing.md |
| Selecting a stack-specific runner or application test | testing.md Stack References; load only the matching language/framework reference |

Shortcut: `.ai-kit/scripts/context-pack.sh <feature> T<n>` emits the deterministic tier-1 context pack for a task (task line, criteria, files: contents, brief, knowledge hits) — start there, then load modules per this table.
