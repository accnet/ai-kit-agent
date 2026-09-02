# AI-Kit

AI-Kit is a chat-first, tool-neutral workflow and control harness for using strong
LLMs such as Codex and Claude to plan, execute, validate, and review software work
with durable context, explicit task contracts, bounded file scope, Git evidence,
approval gates, retries, and recovery.

The maintained kit lives in `.ai/`. Project requirements remain in `features/`,
regenerable execution state in `.project/`, and local session pointers in the
gitignored `.workspace/` directory. `AGENTS.md` is the always-loaded core; the
specialized skills under `.ai/skills/` route planning, architecture, contracts,
implementation, migration, QA, review, and status work on demand.

## Install into a new project

Copy the complete `.ai/` directory to the empty project root and run:

```bash
bash .ai/install/install.sh
bash .ai/install/install.sh --check
```

The installer creates the required root instructions, local directories, skill
projections, QA hook, and CI workflow. When Git exists it initializes only that
project and configures repository-local hooks; use `--no-git` to skip this. It
does not stage, commit, push, deploy, install dependencies, or call a model.

The installer never force-overwrites a customized managed file. Resolve any
reported conflict manually, then rerun. After a successful install, inspect
`git status` and create the baseline commit yourself when the project is ready.
See [the portable installer guide](.ai/install/README.md) for all behavior and
supported environments.

## Validate this distribution

```bash
bash .ai/tests/run.sh
bash .ai/scripts/doctor.sh --full
```

Provider execution is configured in `.ai/config.json` and remains opt-in.
## Project contracts

AI-Kit runtime contracts live in `.ai/contracts/`. Contracts owned by a
multi-service project live in `.contracts/` and are governed through its
registry. Supported kinds are JSON Schema, OpenAPI, AsyncAPI/CloudEvents,
data metadata, and workflow metadata. Bootstrap may create an empty registry
skeleton, but AI-Kit never invents product contracts.

## IDE-selected capabilities

AI-Kit does not require a project-size profile. The IDE LLM proposes the
minimum capabilities justified by the current repository and task—for example
service ownership, contract compatibility, database safety, integration QA, or
release ordering. A deterministic resolver validates that proposal, adds
required dependencies, records its signals and provenance, and rejects
evidence-free or unknown capabilities.

Core planning, file-scope, approval, testing, review, credential, and
destructive-operation gates are always enabled. Explicit overrides are audited
and cannot disable this safety floor. Use `effective-config` to inspect the
decision; legacy and small projects without multi-service signals retain only
the core behavior.
