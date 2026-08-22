# Architecture — AI-Kit Agent Harness v0.6

## Principle

The LLM is the reasoning plane, the harness is the control plane, and the memory
store is the context plane. Models make planning and strategy judgments;
deterministic code owns persistence, authorization, locking, and validation.

## Components

- `models.py`: state constructors and transition constants.
- `store.py`: root-safe paths, atomic JSON, JSONL events, and locks.
- `policy.py`: plan graph, scope, approval, retry, and completion validation.
- `memory.py`: bounded retrieval, provenance hashes, and staleness.
- `providers.py`: scripted, Codex CLI, and Claude CLI adapters.
- `engine.py`: initialize, plan/replan, schedule, execute, review, resume.
- `projection.py`: deterministic `plan.md` and `tasks.md` rendering.
- `cli.py`: explicit commands; no implicit provider calls.

## Canonical data

```text
.project/<feature>/state.json       versioned current state
.project/<feature>/events.jsonl     append-only transition audit
.project/<feature>/memory.jsonl     durable context entries
.project/<feature>/plan.md          generated human view
.project/<feature>/tasks.md         generated human view
workspace-tier harness lock        ephemeral exclusive lock
```

`features/<feature>/` remains the intent source. Markdown projections are never
parsed back into state. Existing features without `state.json` remain legacy.

## State and provider contracts

State contains schema version, event sequence, goal, lifecycle, plan revision, constraints,
verification criteria, tasks, approvals, provider history, timestamps, and the
last transition. Tasks contain IDs, dependencies, acceptance criteria, owner,
file scope, risk labels, state, attempts, evidence, and review records.

Every model call receives a role, bounded context, and JSON Schema. Planning and
review are read-only. Execution uses normal workspace-write/accept-edits modes,
never bypass flags. Invalid or oversized output fails closed.

Large plan revisions enter `plan_pending_approval`. Independent review records
the implementation provider and rejects the same provider as reviewer.

## Control loop

1. Retrieve requirements and relevant memories with provenance.
2. Ask an LLM to propose or revise a structured plan.
3. Validate graph, scopes, risk, size, and acceptance criteria.
4. For large work, record explicit approval of the exact plan revision.
5. Persist state, append a sequenced event, and render Markdown.
6. Select one dependency-safe, approved task and build its context pack.
7. Snapshot repository hashes, ask an implementer to execute, then verify every actual mutation.
8. Ask an independent reviewer when policy requires it.
9. Complete, retry, block, or replan, recording every outcome.

## Safety boundaries

- Validate feature IDs and derived paths before filesystem access.
- Use subprocess argument arrays and stdin; never interpolate a shell command.
- Implementation scopes cannot write intent, execution-state, ephemeral-workspace, or Git-control tiers; path escapes and symlink scopes are rejected.
- Risk labels `database`, `destructive`, `production`, `credentials`, and
  `external-write` require explicit per-task approval.
- Three failures escalate. Review approval must check every acceptance item.
- Live locks stay exclusive; dead-owner locks recover. Sequenced events and
  deterministic projections expose crash gaps through `status` and `repair`.
- v0.6 runs one active task per harness process; parallelism is future work.

## Decisions

- Python 3.9 standard library, JSON state, and JSONL events give zero-bootstrap,
  diffable, auditable storage.
- Deterministic lexical retrieval precedes optional future embeddings.
- Provider routing is configuration, not hardcoded workflow logic.
