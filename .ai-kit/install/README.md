# AI-Kit portable installer

Copy the complete `.ai-kit/` directory into the root of a new project, then run:

```bash
bash .ai-kit/install/install.sh
```

The installer creates the root AI-Kit instructions, Claude entry file, project
index, Git QA hook, GitHub gates workflow, required local directories, ignore
entries, and Codex/Claude skill projections. If Git is installed, it also runs
`git init` when needed and sets repository-local `core.hooksPath=.githooks`.
It never stages files, creates a commit, changes global Git configuration, calls
a model provider, pushes, or deploys.

Use the read-only check after installation:

```bash
bash .ai-kit/install/install.sh --check
```

To install or check without initializing or configuring Git:

```bash
bash .ai-kit/install/install.sh --no-git
bash .ai-kit/install/install.sh --check --no-git
```

The supported runtime is Bash on Linux, macOS, WSL, or Git Bash with the standard
utilities already used by AI-Kit. Python is still required by the harness and its
static validation; the installer does not download system dependencies.

## Safety and repeat runs

The manifest marks each destination `managed` or `seed`.

A **managed** file must match its shipped template byte-for-byte; the installer refuses to write
anything when one differs. A **seed** file is created once and then belongs to the project, which
is free to edit it — `.project/INDEX.md` is a seed, because `ai-kit-plan` requires the project to
maintain it. Marking it managed made `install.sh --check` permanently fail on any project that
actually used the planning workflow.

Before writing any managed root file, the installer checks all destinations.
Existing managed files must match the shipped template byte-for-byte. A different file,
a symlink, or a non-directory path stops preflight without writing other managed
destinations. There is intentionally no force-overwrite option. Reconcile a
customized file with `.ai-kit/install/templates/` manually and rerun.

An unchanged installation is repeatable. Required `.gitignore` lines are merged
without deleting existing entries or adding duplicates. If a later step is
interrupted, correct the reported error and rerun; already installed unchanged
assets are accepted.

## After installation

Review the generated files and `git status`. AI-Kit's isolated task execution
needs a clean repository with a baseline commit, but the installer deliberately
does not create it. Configure Git identity if necessary and create that baseline
commit yourself only after review.

## Project knowledge index (optional, explicit, separate step)

`install.sh` never scans the project for domain knowledge and never writes
`.knowledge-index/`. Semantic project discovery is a second, explicit,
user-invoked phase — run it only when you want a portable, deterministic
knowledge projection for faster session/task bootstrap:

```bash
bash .ai-kit/scripts/knowledge-bootstrap.sh --initial   # first-time bootstrap
bash .ai-kit/scripts/knowledge-bootstrap.sh --check     # read-only verification
bash .ai-kit/scripts/knowledge-bootstrap.sh --refresh   # update an existing projection
```

- **`--initial`** creates `.knowledge-index/` and runs the projection flow for
  the first time. It fails closed — writing nothing — if the directory
  already holds real projected content, so it can never silently overwrite
  project-owned knowledge; use `--refresh` in that case instead.
- **`--check`** is read-only: it validates structure and, when available,
  source-hash freshness. It never writes.
- **`--refresh`** requires an existing projection and updates only
  approved/stale outputs. Any conflict, malformed source, or redaction
  reject fails the whole run closed with no partial writes, the same
  preflight-then-write pattern `install.sh` itself uses.

None of these phases install dependencies, call a model, or use the network.
Full contract: `.project/project-knowledge-index/architecture.md`. Layout and
policy: `.knowledge-index/README.md`.
