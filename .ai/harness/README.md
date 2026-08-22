# AI-Kit Agent Harness

The v0.14 harness lets Codex or Claude reason about plans and implementation
while deterministic code owns state, policy, approvals, evidence, retries,
scope verification, multi-service contracts, and recovery. It uses Python 3.9
standard library only.

Codex and Claude form the **reasoning plane**: they propose plans, bounded task
changes, and reviews. The harness is the authoritative **control and evidence
plane**: it validates coverage, schedules work, binds approvals to exact
actions, executes accepted verification, and persists transitions. Model text
never overrides canonical state or a failed gate.

## Lifecycle

Create `features/<feature>/brief.md` first; the harness never writes product
intent. Then initialize canonical execution state:

```bash
bash .ai/scripts/harness.sh init <feature> \
  --goal "<measurable outcome>" \
  --constraint "<boundary>" \
  --verify "<completion check>" \
  --size standard
```

For requirement traceability, declare stable IDs during initialization:

```bash
bash .ai/scripts/harness.sh init <feature> \
  --goal "<measurable outcome>" \
  --requirement 'R1=<observable requirement>' \
  --requirement 'R2=<observable requirement>'
```

The planner must attach `requirement_refs` to tasks. The plan is rejected if an
initialized requirement is uncovered or a task references an unknown ID. Tasks
may also declare `verification_commands` as argument arrays such as
`["bash", ".ai/tests/run.sh"]`; these are accepted plan contracts, not
free-form commands returned after implementation.

### Durable control sessions

These lifecycle commands never call a model. They persist a run ID and state so
another harness process can resume the same operator session:

```bash
bash .ai/scripts/harness.sh run <feature>
bash .ai/scripts/harness.sh pause <feature> --reason "operator check"
bash .ai/scripts/harness.sh resume <feature>
bash .ai/scripts/harness.sh needs-input <feature> --reason "choose rollout"
bash .ai/scripts/harness.sh cancel <feature> --reason "stop requested"
```

`paused`, `needs_input`, and `cancelled` runs reject `step`. Resume is allowed
only from `paused` or `needs_input`; cancellation is terminal for that run ID.
This lifecycle is a durable control session, not an autonomous daemon: task
execution remains one explicit bounded `step` at a time.

Independent review is disabled by default. `.ai/config.json` is the canonical
kit policy:

```json
{
  "review": {
    "required": true,
    "independent_enabled": false
  }
}
```

With `false`, initialization records `active-agent` review and an explicit
`--review-policy independent` fails closed. To enable independent review,
manually change only `review.independent_enabled` to `true`; new features then
default to `independent`. QA, acceptance evidence, and G3 remain required in
both modes. Existing canonical feature states keep their recorded policy for
audit, but the global false flag makes their effective policy `active-agent`;
turning the flag back on restores independent enforcement for states that
recorded `independent`.

## Isolated task worktrees

CLI task execution is isolated by default, independently of which provider is
selected:

```json
{
  "execution": {
    "isolated_worktree": {
      "required": true
    }
  }
}
```

Before the first `step`, initialize Git, review what will be tracked, and create
a user-owned baseline commit, for example:

```bash
git init
git status --short
git add <reviewed-paths>
git commit -m "Establish AI-Kit baseline"
```

The harness never stages or creates that commit. It rejects a missing `HEAD` or main-tree
changes outside the current feature's control state before invoking Codex,
Claude, or a scripted provider. Implementation and accepted verification run in
an owned detached worktree; `status` reports its phase, base commit, patch hash,
and changed paths. Review reads the same worktree. Approval rechecks the exact
patch and unchanged main `HEAD`, applies it to main as unstaged changes, then
removes the disposable worktree.

Those promoted changes make main intentionally dirty. Before starting the next
isolated task, review them and either commit them through the normal G4 workflow
or otherwise resolve them deliberately. The harness never commits them and will
reject the next workspace creation while they remain as non-control changes.

`revise` and `block` discard the owned worktree without touching main. A live
`running` or `review` workspace is protected from routine cleanup; abandoning
its evidence must be explicit:

```bash
bash .ai/scripts/harness.sh cleanup <feature> T1 --abandon --actor "<user>"
```

Without `--abandon`, cleanup is limited to non-live workspace records. Ownership
marker, path, repository, and Git checks prevent cleanup of an arbitrary
directory.

## Codex CLI task execution

Task execution through Codex CLI is disabled by default. The same
`.ai/config.json` file contains the opt-in policy and exact model:

```json
{
  "execution": {
    "isolated_worktree": {
      "required": true
    },
    "codex_cli": {
      "enabled": false,
      "model": "gpt-5.6-terra"
    }
  }
}
```

While disabled, every `step` must select a provider explicitly:

```bash
bash .ai/scripts/harness.sh step <feature> --task T1 --provider codex
```

After manually changing `enabled` to `true`, omit the provider:

```bash
bash .ai/scripts/harness.sh step <feature> --task T1
```

The harness then selects only Codex CLI, applies `--model gpt-5.6-terra`, and
rejects Claude or scripted overrides. Planning does not change; QA/Review may
use their independent quality routes below. Implementation retains the `workspace-write` sandbox, structured
evidence, actual file-scope hashing, retries, and approvals. A Codex worker
whose injected prompt already says to implement one bounded harness task works
directly and must not invoke `harness step` recursively.

## QA and Review CLI routing

QA and Review have independent, disabled-by-default routes. Provider identities
and models are fixed in the shared registry; each route selects one identity:

```json
{
  "quality": {
    "providers": {
      "codex-cli": {
        "provider": "codex",
        "model": "gpt-5.6-sol"
      },
      "claude-cli": {
        "provider": "claude",
        "model": "claude-sonnet-5"
      }
    },
    "qa": {
      "enabled": false,
      "provider": "codex-cli"
    },
    "review": {
      "enabled": false,
      "provider": "claude-cli"
    }
  }
}
```

Set a route's `enabled` to `true` and choose `codex-cli` or `claude-cli` in its
`provider`. For a harness task whose owner is `qa`, the QA route takes
precedence over normal Terra task execution:

```bash
bash .ai/scripts/harness.sh step <feature> --task T96
```

For Review, enable its route and omit the provider:

```bash
bash .ai/scripts/harness.sh review <feature> T1
```

An enabled route rejects a conflicting explicit provider and scripted response.
When disabled, the command still requires `--provider`. Codex QA uses the
implementer `workspace-write` sandbox and Codex Review is read-only; Claude QA
uses `acceptEdits` while Claude Review uses plan mode. CLI choice never waives
QA/G3 and never establishes independent review: `review.independent_enabled`
remains the separate authority for reviewer separation. Harness-selected QA or
Reviewer workers act directly and never dispatch their route recursively.

Unless the applicable task or quality route above is enabled, explicitly select
a provider for every model call:

```bash
bash .ai/scripts/harness.sh plan <feature> --provider codex
bash .ai/scripts/harness.sh next <feature>
bash .ai/scripts/harness.sh step <feature> --provider codex
bash .ai/scripts/harness.sh review <feature> T1 --provider codex
bash .ai/scripts/harness.sh status <feature>
```

After manually enabling independent review, select a provider different from
the implementer, for example `--provider claude` after Codex implementation.

Large initial plans and replans stop before scheduling:

```bash
bash .ai/scripts/harness.sh approve-plan <feature> --approved-by "<user>"
```

## Multi-service contract graph

For a frontend/backend/API/event/database feature, the provider plan can add:

- hierarchy: `program_id`, `workstream_id`, and `parent_feature`;
- a `services` registry with domain, owned paths/data, exposed and consumed
  contracts, and allowed/forbidden dependencies;
- versioned `contracts` for API, event, data, frontend, workflow, or operations;
- per-task `service`, `layer`, `contract_reads`, `contract_writes`, `produces`,
  `data_entities`, integration checks, delivery order, and rollback.

Contract references use `<id>@<semver>`, for example
`checkout.api@1.0.0`. Keep durable public sources in repository code such as
`contracts/api/`, `contracts/events/`, or a service-owned schema directory;
do not use generated `.project/` files as product contracts.

Every plan-provided contract enters canonical state as `draft`, even if a
provider labels it approved. The harness schedules no reader or producer until
an explicit approval hashes the current source:

```bash
bash .ai/scripts/harness.sh approve-contract <feature> \
  'checkout.api@1.0.0' --approved-by "<user>" --note "consumer review complete"
```

A contract-writing task must be Architect-owned, own the contract source file,
declare `public-contract`, and be the only writer. Readers in the same plan
must transitively depend on that writer. Starting the writer immediately
returns the contract to `draft`/`pending`; passing implementation review does
not approve it. A successful writer must actually mutate every declared source.
Run `approve-contract` again before consumer tasks proceed.

After all consumers have migrated, explicitly deprecate the approved version:

```bash
bash .ai/scripts/harness.sh deprecate-contract <feature> \
  'checkout.api@1.0.0' --deprecated-by "<user>" --note "migration complete"
```

Deprecated contracts remain in canonical history and block new readers.

At scheduling time, the harness recomputes every approved source hash. A
missing, symlinked, deprecated, or changed source fails closed and requires a
replan or explicit contract approval. Backend, frontend, and database tasks in
a registered plan select one service and may read only contracts that service
produces or consumes. A consumer service declares each producer as a service
dependency. Database entities must belong to that service's declared data
ownership.

The 24-task cap is per feature/workstream. Large programs should use bounded
service workstreams connected by hierarchy and contract metadata, rather than
one flat mega-plan. Cross-feature distributed execution and semantic
OpenAPI/AsyncAPI compatibility diffing are not implemented in v0.14.

Database, destructive, production, credential, and external-write tasks also
need task-specific approval:

```bash
bash .ai/scripts/harness.sh approve <feature> T2 --approved-by "<user>" --note "<scope>"
```

New plan approvals persist a digest of the exact revision, goal, requirement
registry, service/contract graph, and task contracts. Risky-task approvals
persist an action digest covering revision, file scope, risks, environments,
verification commands, contract/data writes, and rollback. Changing a protected
input makes the old approval invalid.

## Independent verification

For a task with `verification_commands`, provider-reported success is not
sufficient. The harness runs each accepted command from the task execution root
(the detached worktree when isolation is required) with `shell=False` and a
120-second timeout, then records the exact argument
vector, exit code, duration, timeout/pass flags, output byte count, and SHA-256
output digest. Raw stdout and stderr are not stored in canonical state.

A non-zero exit, timeout, or repository mutation during verification fails G2.
Plan validation rejects inline `bash -c`/`python -c`, unknown executables, and
unsafe package actions. Accepted forms are repository-relative Python/shell
scripts plus a small allowlist of test/build tools and actions.

`plan`, `step`, and `review` are the only commands above that invoke a model.
Tests use `--provider scripted --response <json>` and never invoke a provider.
Provider executables, optional models, timeouts, output limits, and role routing
live in `.ai/harness/config.json`; kit-level review and task-execution policies
live in `.ai/config.json`.

Each native provider has configurable effort by harness role:

```json
{
  "providers": {
    "codex": {
      "reasoning_effort": {
        "planner": "high",
        "implementer": "high",
        "reviewer": "high"
      }
    }
  }
}
```

The same shape applies to `claude`. Supported portable values are `low`,
`medium`, `high`, `xhigh`, and `max`. Routes remain disabled or explicit as
described above, so setting effort never invokes a provider by itself.

## Context and recovery

```bash
bash .ai/scripts/harness.sh remember <feature> --kind semantic --content "<fact>" --tag <tag>
bash .ai/scripts/harness.sh context <feature> --query "<current task>"
bash .ai/scripts/harness.sh status <feature>
bash .ai/scripts/harness.sh repair <feature>
```

Memory is bounded, ranked, and provenance-hashed; file-backed entries report
staleness and the context result reports excluded or truncated sources. Codex
loads `AGENTS.md` natively, while Claude loads `CLAUDE.md` and its `@AGENTS.md`
import, so the harness omits its duplicate `AGENTS.md` memory block for those
two adapters. Scripted and custom providers retain the project-instruction
block unless they explicitly declare native discovery. A pinned source that
does not fit the reserved source share is deferred whole and reconsidered
against the final budget before truncation.

Execution prompts select one workflow from task ownership and contract-write
metadata, and name its exact `.ai/agents/<owner>.md` contract. The worker loads
those task-specific files on demand instead of receiving every skill body.
`state.json` is canonical, `events.jsonl` is append-only history, and
`plan.md`/`tasks.md` are generated views. A dead process lock is recovered on
the next transition. `repair` can reconstruct a missing final event and refresh
stale projections from canonical state.

A task in workspace phase `review` can be reviewed after restarting the CLI;
the marker, repository, path, base commit, and patch digest are revalidated.
`revise`, `block`, provider/scope failure, and explicit abandonment remove only
that owned workspace. A failed promotion caused by main `HEAD` drift retains the
workspace for inspection and does not modify the task patch in main.

`repair` repairs control-plane event/projection artifacts only. It does not
automatically reconcile the narrow crash window after `git apply` succeeds but
before canonical completion is saved. In that case, stop automated approval,
inspect main status and the recorded patch digest, then reconcile manually; do
not reapply the patch blindly.

## Control boundaries

- Planning and review use read-only/plan provider modes; Codex implementation
  uses `workspace-write`, Claude implementation uses `acceptEdits`, and no route
  uses a permission-bypass flag.
- Claude planning exposes only Read/Glob/Grep. Claude review additionally
  exposes Bash in plan mode for non-mutating tests and Git inspection; the
  review prompt explicitly forbids file edits. The harness snapshots the
  repository before and after every review and rejects the verdict if any path
  changed, including when the provider exits with an error.
- Every CLI implementation and accepted verification runs in an owned detached
  worktree. Before review, actual creates, modifications, and deletions must fit
  task scope and match the captured Git patch. Main `HEAD` and non-control
  changes are checked again before promotion; the main index is never staged.
- `features/`, `.project/`, `.workspace/`, `.git/`, path escapes, and symlink
  scopes are never valid provider write scopes.
- Standard/large work requires review. The default `active-agent` policy checks
  every acceptance item without requiring provider separation. After manual
  activation, the default `independent` policy additionally requires the
  reviewer provider to differ from the implementer.
- Registered multi-service plans additionally enforce C1-C6 from
  `.ai/modules/contracts.md`: ownership, approval, compatibility declaration,
  data safety, integration evidence, and release metadata.
- Three failed attempts escalate. No automatic production or destructive
  operation is performed by the harness.
- v0.14 does not yet provide Codex App Server/Claude Agent SDK event adapters,
  pre-tool interception inside provider processes, container/network/database
  isolation, authenticated attestations, or a multi-workstream daemon. A Git
  worktree protects the repository promotion path; it is not a full operating-
  system sandbox and cannot undo effects outside the repository. CLI providers
  remain stateless subprocess adapters; use host sandboxing, branch protection,
  credential isolation, and explicit approvals at those boundaries.
