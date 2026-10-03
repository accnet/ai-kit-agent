# AI-Kit Agent Harness

## IDE-native orchestration boundary

The optional `orchestration` policy in `.ai-kit/config.json` describes Codex IDE native-worker execution.
The harness validates the policy and exposes read-only DAG/manifest checks, but it never creates native
workers or calls an LLM API for orchestration. Task claims and completion transitions remain coordinator
owned; each worker must use a distinct clean worktree supplied by Codex IDE. QA and G3 are blocked until
the declared implementation dependency barrier closes.

The v0.16 harness lets Codex or Claude reason about plans and implementation
while deterministic code owns state, policy, approvals, evidence, retries,
scope verification, multi-service contracts, and recovery. It uses Python 3.9
standard library only.

Codex and Claude form the **reasoning plane**: they propose plans, bounded task
changes, and reviews. The harness is the authoritative **control and evidence
plane**: it validates coverage, schedules work, binds approvals to exact
actions, executes accepted verification, and persists transitions. Model text
never overrides canonical state or a failed gate.

## Lifecycle

## Test discovery and evidence

Reusable AI-Kit mechanics suites are selected by `.ai-kit/tests/manifest.json`,
not by a filesystem glob. Project-owned tests belong under `/tests` and use
their own runner/manifest; they are never packaged with the kit. Every QA
record should include the exact command, repository-relative working directory,
timeout, exit code, and the feature/task it verifies. Commands that require a
subdirectory (for example, browser suites under `tests/e2e`) must declare that
working directory explicitly.

### Compact full-QA reporting

Use the reporter when the objective is to reduce agent-context text without
changing what QA executes:

```bash
.ai-kit/scripts/qa-report.sh --profile ai-kit|theme|browser|all
```

An explicit profile is required; omitting it exits with usage status 2 before
running any command. Use `--profile ai-kit` for kit regression in this repository.
Explicit `--profile all` runs the existing AI-Kit, theme, and browser
commands in their fixed repository order, with their existing coverage and
compute cost. It continues through every profile even after one fails, then
returns a non-zero status when any profile failed. A named profile runs only
that existing command. Unknown profile names and duplicate profile arguments
are usage errors and fail without running QA. A selected profile whose required
runner/package file is absent reports an environment failure, never a pass or
silent skip. Select profiles from the task's acceptance scope and available project
runners; do not request optional theme/browser suites in a kit-only checkout.

Normal output is a bounded summary of each selected profile's status, duration,
and local artifact location; a failure also identifies its command. Raw stdout and stderr are retained only
in owner-only local artifacts; they are never automatically copied into agent
context. On failure, the summary also identifies the failed profile and a
bounded diagnostic excerpt. `--verbose` reproduces the stored logs for the
selected run. The reporter is a presentation and evidence layer: it does not
select tests from changed paths, weaken a suite, or reduce browser coverage.
The local manifest includes output/excerpt byte counts and completed-profile
counts. `llm_usage: null` means unavailable, not zero tokens or zero quota cost.

Legacy cross-workstream barriers use a task-plan metadata line:

`Feature dependencies: v1-section-column-layout:T96`

The DAG resolves each target task and dispatches only when every referenced task is checked.
Missing, malformed, duplicate, or incomplete targets are errors. For reusable QA commands,
`.ai-kit/qa-profiles.json` records an argument-array command, repository-relative `cwd`, bounded
timeout, and evidence metadata (portable profiles may invoke optional suites such as
`tests/e2e` through a command argument while keeping `cwd` at `.`); run `python3 .ai-kit/scripts/qa_profiles.py` before accepting a
profile or use the same check through `doctor.sh`/`validate-kit.sh`.

### QA/review remediation

QA and review findings are coordinator-owned state, not worker edits. A finding
records its source gate (`qa` or `review`), source task, severity, exact
acceptance criterion, and reproducible summary. A defect within the current
task scope retries that task under the normal three-attempt limit. A defect
requiring new files, ownership, contracts, or acceptance criteria is handled by
replan with a new task linked to the finding. A finding is resolved only after
the linked work passes G2 and the required G3 review; provider prose alone
cannot close it.

### v0.16 canonical barriers and verification profiles

Harness-managed canonical plans may declare optional `feature_dependencies` at
the plan level. Each entry is an object with exactly `feature` and `task`
strings. Every local task is blocked until every target is complete. For each
target, the resolver reads `<feature>/state.json` when it exists; it reads
`<feature>/tasks.md` only when state is absent. A canonical task satisfies a
barrier only with status `complete`; a legacy task satisfies it only with `[x]`.
Missing, malformed, duplicate, self-referencing, unfinished, or cyclic targets
are deterministic policy errors. Resolution is read-only and never falls back
from malformed canonical state to Markdown.

Tasks may also declare optional ordered `verification_profiles` alongside
legacy `verification_commands`. A profile ID expands from `.ai-kit/qa-profiles.json`
to a validated argument vector, repository-contained working directory,
bounded timeout, and immutable evidence metadata. Profiles are resolved before any
command executes. Inline commands run first, then profiles in declared order.
Exact duplicate declarations with the same argv, resolved cwd, and timeout execute
once in that verification batch, retaining one evidence record per declaration.
Conflicting timeouts among selected profiles for the same command/cwd fail before
execution. Execution stops at the first non-zero exit,
timeout, unsafe profile, or repository mutation; no later command runs.
Profiles never use a shell and cannot override command, cwd, timeout, or
metadata inline. Inline commands retain a 120-second timeout unless an explicitly
selected profile has the same argv and cwd; that profile supplies the timeout for
both declarations. Use profiles for longer checks instead of retrying a command
that cannot finish within the inline timeout.

Every completed verification records an ordered evidence item. Inline evidence
records its command outcome; profile evidence additionally snapshots profile
ID, command argv, cwd, timeout, metadata, exit code, duration, and output
digest. Each executed check also stores checksummed stdout/stderr artifacts in the
coordinator's local QA directory, so isolated-worktree cleanup does not erase them.
Canonical evidence contains artifact pointers, a bounded redacted failure excerpt,
source snapshots before/after, runtime/environment attribution, and a check digest.
Failure kinds distinguish configuration, policy, environment/launch, timeout,
signal, non-zero test exit, repository mutation, and artifact failures; do not infer
a root cause from an exit code alone. Artifact capture failure blocks verification.
Raw output is not stored in canonical state. Declared barriers and
verification profiles participate in the normalised plan and task-action
digests only when present, preserving compatibility for legacy plans.

The local verification manifest counts declared/executed checks, duplicate
references, and output bytes. It makes no claim about unavailable LLM token usage.
Deduplication only coalesces duplicate declarations in the current batch. It does
not reuse previous runs, worker claims, another worktree's results, or cached passes.
Source snapshots are evidence attribution, not a complete fingerprint of external
services or installed dependencies. Keep verification checks isolated and deterministic.
After an environment/timeout failure, correct the environment or declared timeout
before retrying; a failed assertion goes back to its owning implementation task.

Create `features/<feature>/brief.md` first; the harness never writes product
intent. Then initialize canonical execution state:

```bash
bash .ai-kit/scripts/harness.sh init <feature> \
  --goal "<measurable outcome>" \
  --constraint "<boundary>" \
  --verify "<completion check>" \
  --size standard
```

For requirement traceability, declare stable IDs during initialization:

```bash
bash .ai-kit/scripts/harness.sh init <feature> \
  --goal "<measurable outcome>" \
  --requirement 'R1=<observable requirement>' \
  --requirement 'R2=<observable requirement>'
```

The planner must attach `requirement_refs` to tasks. The plan is rejected if an
initialized requirement is uncovered or a task references an unknown ID. Tasks
may also declare `verification_commands` as argument arrays such as
`["bash", ".ai-kit/tests/run.sh"]`; these are accepted plan contracts, not
free-form commands returned after implementation.

### Durable control sessions

These lifecycle commands never call a model. They persist a run ID and state so
another harness process can resume the same operator session:

```bash
bash .ai-kit/scripts/harness.sh run <feature>
bash .ai-kit/scripts/harness.sh pause <feature> --reason "operator check"
bash .ai-kit/scripts/harness.sh resume <feature>
bash .ai-kit/scripts/harness.sh needs-input <feature> --reason "choose rollout"
bash .ai-kit/scripts/harness.sh cancel <feature> --reason "stop requested"
```

`paused`, `needs_input`, and `cancelled` runs reject `step`. Resume is allowed
only from `paused` or `needs_input`; cancellation is terminal for that run ID.
This lifecycle is a durable control session, not an autonomous daemon: task
execution remains one explicit bounded `step` at a time.

`needs-input`'s `--reason` is a plain string with no structured schema. For a
bounded, host-neutral multi-choice question — validated, hash-bound to the
exact question set, and rejected if answered against a stale plan revision —
use the structured variants instead (`.project/structured-user-input/architecture.md`;
rendering mechanics: `.ai-kit/modules/planning/ask-question.md`):

```bash
bash .ai-kit/scripts/harness.sh request-input <feature> --reason "choose rollout" --questions-file questions.json
bash .ai-kit/scripts/harness.sh answer-input <feature> --request-id IN-1 --answers-file answers.json
```

Independent review is disabled by default. `.ai-kit/config.json` is the canonical
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
bash .ai-kit/scripts/harness.sh cleanup <feature> T1 --abandon --actor "<user>"
```

Without `--abandon`, cleanup is limited to non-live workspace records. Ownership
marker, path, repository, and Git checks prevent cleanup of an arbitrary
directory.

## Generic task CLI execution

Generic implementation-task execution is opt-in. The `execution.task_cli`
policy selects one configured provider and an optional model; it does not route
planning, QA, or review:

```json
{
  "execution": {
    "isolated_worktree": {
      "required": true
    },
    "task_cli": {
      "enabled": true,
      "provider": "grok",
      "model": null
    }
  }
}
```

While disabled, every `step` must select a provider explicitly:

```bash
bash .ai-kit/scripts/harness.sh step <feature> --task T1 --provider grok
```

After manually changing `enabled` to `true`, omit the provider:

```bash
bash .ai-kit/scripts/harness.sh step <feature> --task T1
```

The harness then selects only the configured provider, applies its configured
model when non-null, and rejects all conflicting or scripted overrides.
Planning does not change; QA/Review retain their independent quality routes
below. The current repository config selects Grok for generic implementation
tasks only. Grok uses a prompt file (never a process argument), non-interactive
tool approval, and `acceptEdits`; planner/reviewer Grok commands use `plan`
mode. Its adapter validates the final canonical JSON after the CLI envelope
rather than passing a JSON schema to Grok, because schema mode can terminate on
an intermediate reasoning response. A bounded call gets one continuation of the
same `sessionId` only when Grok reports an incomplete terminal state such as
`cancelled` or `max_turns`. The continuation is never accepted as success unless
it returns a schema-valid final result; otherwise the error includes both stop
reason and session ID for operator recovery. File-scope hashing, retries, and
approvals remain harness-owned. A worker whose injected prompt already says to
implement one bounded harness task works directly and must not invoke `harness
step` recursively.

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
bash .ai-kit/scripts/harness.sh step <feature> --task T96
```

For Review, enable its route and omit the provider:

```bash
bash .ai-kit/scripts/harness.sh review <feature> T1
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
bash .ai-kit/scripts/harness.sh plan <feature> --provider codex
bash .ai-kit/scripts/harness.sh next <feature>
bash .ai-kit/scripts/harness.sh step <feature> --provider codex
bash .ai-kit/scripts/harness.sh review <feature> T1 --provider codex
bash .ai-kit/scripts/harness.sh status <feature>
```

After manually enabling independent review, select a provider different from
the implementer, for example `--provider claude` after Codex implementation.

Large initial plans and replans stop before scheduling:

```bash
bash .ai-kit/scripts/harness.sh approve-plan <feature> --approved-by "<user>"
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
`checkout.api@1.0.0`. AI-Kit protocol contracts are shipped under
`.ai-kit/contracts/`. Keep project product sources in `.contracts/` or below the
owning service's declared paths; do not use generated
`.project/` files as product contracts.

Every plan-provided contract enters canonical state as `draft`, even if a
provider labels it approved. The harness schedules no reader or producer until
an explicit approval hashes the current source:

```bash
bash .ai-kit/scripts/harness.sh approve-contract <feature> \
  'checkout.api@1.0.0' --approved-by "<user>" --note "consumer review complete"
```

A contract-writing task must be Architect-owned, own the contract source file,
declare `public-contract`, and be the only writer. Readers in the same plan
must transitively depend on that writer. Starting the writer immediately
returns the contract to `draft`/`pending`; passing implementation review does
not approve it. A successful writer must actually mutate every declared source.
Run `approve-contract` again before consumer tasks proceed.

Project contract kinds supported by the core are JSON Schema, OpenAPI,
AsyncAPI with optional CloudEvents envelopes, data metadata, and workflow
metadata. Their sources belong under `.contracts/`; `.ai-kit/contracts/` is reserved
for AI-Kit's own runtime protocol contracts. Adapters are deterministic and
read-only. Unsupported protocol features fail closed and require an explicit
adapter extension; the harness never invents project contracts during install
or approval.

## IDE LLM capability selection

The harness exposes capabilities rather than user-facing size profiles. An IDE
LLM may propose capabilities with repository or task signals. The resolver in
`capability_config.py` validates the catalog, expands dependencies, preserves
provenance, and fails closed when a proposal has no evidence. Plan declarations
also impose non-optional capabilities: services require ownership, contracts
require the contract graph/compatibility/integration QA, database work requires
database safety, and production work requires release ordering.

`effective-config` renders the deterministic decision. `init --capability ...
--signal ...` persists it under `.project/<feature>/capabilities.json`; canonical
state carries the same decision after planning. No selection may disable the
planning, file-scope, approval, testing, review, credential, or destructive-op
safety floor, and selection never invents services or project contracts.

After all consumers have migrated, explicitly deprecate the approved version:

```bash
bash .ai-kit/scripts/harness.sh deprecate-contract <feature> \
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
one flat mega-plan. The built-in adapters compare the governed OpenAPI and
AsyncAPI/CloudEvents subset documented in `.ai-kit/modules/contracts.md`; features
outside that subset fail closed and need an adapter extension. A distributed
multi-workstream execution daemon is not implemented in v0.16.

Database, destructive, production, credential, and external-write tasks also
need task-specific approval:

```bash
bash .ai-kit/scripts/harness.sh approve <feature> T2 --approved-by "<user>" --note "<scope>"
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
live in `.ai-kit/harness/config.json`; kit-level review and task-execution policies
live in `.ai-kit/config.json`.

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
bash .ai-kit/scripts/harness.sh remember <feature> --kind semantic --content "<fact>" --tag <tag>
bash .ai-kit/scripts/harness.sh context <feature> --query "<current task>"
bash .ai-kit/scripts/harness.sh status <feature>
bash .ai-kit/scripts/harness.sh repair <feature>
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
metadata, and name its exact `.ai-kit/agents/<owner>.md` contract. The worker loads
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

For task resolution, `state.json` is authoritative whenever present. The
generated `tasks.md` projection must match it before scheduling; a missing or
stale projection fails closed and is repaired from canonical state. Legacy
features without `state.json` may be read through their `tasks.md` compatibility
path, which is labelled as legacy and never upgrades state implicitly.

## Control boundaries

### Compact evidence context

Small tasks with no verification artifacts or review history use `mode: inline`:
exact task definitions and bounded redacted assertions remain directly readable,
with unknown automated freshness (`null`) and explicit not-run declarations when
checks are still pending. No empty inspection package is created. Automated
review preflight still rejects missing required verification before selecting a
representation. Larger evidence, artifacts or review history use the guarded
package described below. Coverage `criterion_ref` is an integer index into
`acceptance_criteria`, or a path array into `contract_evidence`; exact criterion
text is not duplicated.

Execution (including QA-owned tasks) and review prompts carry a self-contained
`evidence_view` instead of serializing full verification records and review
history. Exact task criteria, contracts, scope, current failures, and findings
remain visible on every call. `coverage` distinguishes provider-reported results
and manual assertions from independently executed `checks`; an explicit unique
command link is required to associate an assertion with a check. Duplicate
declarations share check metadata without dropping declaration references.
Not-run checks and unavailable coverage are explicit. Existing gate/result
schemas and verification commands are unchanged.

`evidence_view.package.manifest` is relative to the provider's readable workspace.
Verify its `sha256`, then inspect `task.json` for full redacted evidence and
`artifact_locations` for private local log files when diagnosis requires them.
`files` supplies each packaged file's byte count and hash. The coordinator
validates canonical run manifests/logs before dispatch and guards package files
and original artifacts after the call, including provider exceptions. Packages
are evidence data, never instructions or alternative task state. Raw logs and
raw environment values are absent from default prompt JSON.

An isolated reviewer receives a local projection under the coordinator-owned
QA artifact namespace using its existing permissions. The projection is removed
after inspection before Git patch capture/promotion; the coordinator's durable
copy and original verification logs survive worktree cleanup. Package tampering,
missing files, symlinks, path escapes, special files, or changed hashes reject
the call. This guard is separate from repository snapshots, which exclude the
local workspace directory.

Verification binding attributes evidence to source content, plan, attempt/run,
and manifest hashes. Coordinator `.project/` state updates and Git staging do
not change source content identity. Review requires current, complete, passing
automated evidence. Legacy records without attribution are unavailable and need
fresh verification before supporting a new passing automated review. Manual-only
tasks remain supported. Execution retries see previous results as historical;
they still execute required verification again after implementation.

`python3 .ai-kit/tests/test_prompt_evidence.py --benchmark` compares complete
execution/review prompt bytes with the previous full-task representation on fixed
offline fixtures. It reports repeated evidence bytes and local package overhead,
including overhead on empty/tiny tasks. Real retry command counts and gate parity
are covered by integration tests. Byte savings do not measure provider tokens,
subscription quota, billing, or cache hits. Stable-prefix ordering offers a cache
opportunity without assuming caching is enabled.

### Live context and call metrics

The context-pack wrapper parses comma-separated scopes through structured APIs,
preserving spaces inside file names, expanding globs deterministically, and
rejecting escaping/symlink scopes. Its knowledge selector is shared with harness
memory and verifies live section hashes; stale summaries never serve merely
because an old index labels them approved. Invalid/absent indexes fall back to
canonical knowledge. Refresh the derived index explicitly when maintaining it.
Memory filters stale/nonmatching background, prioritizes pinned sources and
counts rendered headers/separators within `context_budget_chars`.

Planner, execution and review calls retain private metadata in
`.workspace/qa/call-*/metrics.json`: complete harness prompt bytes/characters,
declared schema bytes, rendered context size/cap, phase timings, provider-call
outcome, and available native subprocess/resume/captured-stream byte counts.
Configured wrappers forward adapter observations; scripted/custom providers
without native observations report null counts. Raw prompts, outputs and
environment values are absent. Native IDE tool-output bytes, tokens, quota and
cache hits remain null when unobservable. Prompt size is the harness-supplied
prompt, not a claim to include all native discovery/tool context. Elapsed time
is measured up to metadata persistence; individual phase timings explain the
observed work and do not certify external billing or model performance.

Within one verification phase, caller/verifier full snapshots are shared to avoid
duplicate scans; every executed command still has its own post-command snapshot,
with fallback scans after artifact errors. Provider boundaries and fresh review
retain full mutation/freshness checks. Each unique canonical artifact is read once
per package preparation and guarded again after dispatch. Identical rendered
projections skip writes; stale content is repaired. No passing test result is
cached across calls, runs, snapshots or worktrees.

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
  `.ai-kit/modules/contracts.md`: ownership, approval, compatibility declaration,
  data safety, integration evidence, and release metadata.
- Three failed attempts escalate. No automatic production or destructive
  operation is performed by the harness.
- v0.16 does not yet provide Codex App Server/Claude Agent SDK event adapters,
  pre-tool interception inside provider processes, container/network/database
  isolation, authenticated attestations, or a multi-workstream daemon. A Git
  worktree protects the repository promotion path; it is not a full operating-
  system sandbox and cannot undo effects outside the repository. CLI providers
  remain stateless subprocess adapters; use host sandboxing, branch protection,
  credential isolation, and explicit approvals at those boundaries.
