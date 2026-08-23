# AI-Kit portable installer

Copy the complete `.ai/` directory into the root of a new project, then run:

```bash
bash .ai/install/install.sh
```

The installer creates the root AI-Kit instructions, Claude entry file, project
index, Git QA hook, GitHub gates workflow, required local directories, ignore
entries, and Codex/Claude skill projections. If Git is installed, it also runs
`git init` when needed and sets repository-local `core.hooksPath=.githooks`.
It never stages files, creates a commit, changes global Git configuration, calls
a model provider, pushes, or deploys.

Use the read-only check after installation:

```bash
bash .ai/install/install.sh --check
```

To install or check without initializing or configuring Git:

```bash
bash .ai/install/install.sh --no-git
bash .ai/install/install.sh --check --no-git
```

The supported runtime is Bash on Linux, macOS, WSL, or Git Bash with the standard
utilities already used by AI-Kit. Python is still required by the harness and its
static validation; the installer does not download system dependencies.

## Safety and repeat runs

Before writing any managed root file, the installer checks all destinations.
Existing files must match the shipped template byte-for-byte. A different file,
a symlink, or a non-directory path stops preflight without writing other managed
destinations. There is intentionally no force-overwrite option. Reconcile a
customized file with `.ai/install/templates/` manually and rerun.

An unchanged installation is repeatable. Required `.gitignore` lines are merged
without deleting existing entries or adding duplicates. If a later step is
interrupted, correct the reported error and rerun; already installed unchanged
assets are accepted.

## After installation

Review the generated files and `git status`. AI-Kit's isolated task execution
needs a clean repository with a baseline commit, but the installer deliberately
does not create it. Configure Git identity if necessary and create that baseline
commit yourself only after review.
