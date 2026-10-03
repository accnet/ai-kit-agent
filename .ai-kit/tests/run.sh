#!/usr/bin/env bash
# Dependency-free mechanics tests for AI-Kit.
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

pass=0
check() {
  local message="$1"
  shift
  if "$@"; then
    echo "PASS: $message"
    pass=$((pass+1))
  else
    echo "FAIL: $message" >&2
    exit 1
  fi
}

check "static kit validation" .ai-kit/scripts/validate-kit.sh
check "skill projections are synchronized" .ai-kit/scripts/sync-skills.sh --check
check "harness Python integration suite" python3 .ai-kit/tests/test_harness.py
check "portable installer regression suite" bash .ai-kit/tests/test_install.sh
check "explicit AI-Kit mechanics manifest" python3 .ai-kit/tests/test_manifest.py

# Only reusable AI-Kit mechanics live here. Project tests are executed by the
# repository-owned tests/run.sh runner and must never be copied with the kit.
while IFS= read -r suite; do
  [ -n "$suite" ] || continue
  check "AI-Kit suite $(basename "$suite" .py)" python3 "$suite"
done < <(python3 -c 'import json; from pathlib import Path; root=Path(".ai-kit/tests"); data=json.loads((root/"manifest.json").read_text()); print("\n".join(str(root/name) for name in data["suites"]))')

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

SYNC_FIXTURE="$TMP/sync"
mkdir -p "$SYNC_FIXTURE/.ai-kit/scripts"
cp -R .ai-kit/skills "$SYNC_FIXTURE/.ai-kit/skills"
cp .ai-kit/scripts/sync-skills.sh "$SYNC_FIXTURE/.ai-kit/scripts/"
(cd "$SYNC_FIXTURE" && .ai-kit/scripts/sync-skills.sh)
check "generated projection check passes" bash -c 'cd "$1" && .ai-kit/scripts/sync-skills.sh --check' _ "$SYNC_FIXTURE"
mkdir -p "$SYNC_FIXTURE/.agents/skills/ai-kit-stale"
printf '%s\n' stale > "$SYNC_FIXTURE/.agents/skills/ai-kit-stale/SKILL.md"
if (cd "$SYNC_FIXTURE" && .ai-kit/scripts/sync-skills.sh --check >/dev/null 2>&1); then
  echo "FAIL: projection check must reject stale AI-Kit skills" >&2
  exit 1
fi
echo "PASS: projection check rejects stale AI-Kit skills"
pass=$((pass+1))

FIXTURE="$TMP/repo"
mkdir -p "$FIXTURE/.ai-kit/scripts" "$FIXTURE/.project/demo" "$FIXTURE/features/demo" "$FIXTURE/src" "$FIXTURE/.githooks"
cp .ai-kit/scripts/next-task.sh .ai-kit/scripts/orchestrate.py .ai-kit/scripts/dag.py .ai-kit/scripts/state.sh .ai-kit/scripts/context-pack.sh .ai-kit/scripts/log-event.sh .ai-kit/scripts/check-gates.sh .ai-kit/scripts/git-qa.sh "$FIXTURE/.ai-kit/scripts/"
cp .ai-kit/scripts/context_pack.py .ai-kit/scripts/knowledge_retrieval.py .ai-kit/scripts/knowledge-projector.py .ai-kit/scripts/task_state.py "$FIXTURE/.ai-kit/scripts/"
cp .githooks/pre-commit "$FIXTURE/.githooks/"

printf '%s\n' '# Demo brief' 'Exercise task mechanics.' > "$FIXTURE/features/demo/brief.md"
printf '%s\n' 'fixture payload' > "$FIXTURE/src/example.txt"
printf '%s\n' \
  '# Tasks — demo' \
  '' \
  'Intent: feature | Size: standard' \
  'Goal: exercise mechanics' \
  'Out of scope: none' \
  'Open questions: none' \
  '' \
  '## Tasks' \
  '- [ ] T1 Build fixture | owner: backend | scope: S | needs: - | files: src/example.txt' \
  '  - Accept: fixture payload is packed' \
  '- [ ] T2 Verify dependency | owner: qa | scope: S | needs: T1 | files: tests/' \
  '  - Accept: T2 becomes claimable after T1' \
  > "$FIXTURE/.project/demo/tasks.md"

cd "$FIXTURE"
git_qa_status="$(.ai-kit/scripts/git-qa.sh status)"
check "Git QA status skips outside a repository" bash -c 'printf "%s" "$1" | grep -q "status=skip.*repository=no"' _ "$git_qa_status"
if .ai-kit/scripts/git-qa.sh setup --invalid >/dev/null 2>&1; then
  echo "FAIL: Git QA setup must reject invalid arguments" >&2
  exit 1
fi
echo "PASS: Git QA setup rejects invalid arguments"
pass=$((pass+1))

claimable="$(.ai-kit/scripts/next-task.sh demo)"
check "dependency blocks T2 initially" bash -c 'printf "%s" "$1" | grep -q "T1" && ! printf "%s" "$1" | grep -q "T2"' _ "$claimable"

check "worker claim is coordinator-only" bash -c '! .ai-kit/scripts/next-task.sh demo --claim T1 --instance fixture-agent >/dev/null 2>&1'
state="$(.ai-kit/scripts/state.sh demo)"
check "state remains unchanged after worker claim rejection" bash -c 'printf "%s" "$1" | grep -q '"'"'"id":"T1","status":"todo"'"'"'' _ "$state"

sed -i 's/^- \[ \] T1 /- [x] T1 /' .project/demo/tasks.md
claimable="$(.ai-kit/scripts/next-task.sh demo)"
check "T2 unblocks after T1" bash -c 'printf "%s" "$1" | grep -q "T2"' _ "$claimable"

pack="$(.ai-kit/scripts/context-pack.sh demo T1)"
check "context pack includes acceptance and scoped file" bash -c 'printf "%s" "$1" | grep -q "fixture payload" && printf "%s" "$1" | grep -q "Accept: fixture payload is packed"' _ "$pack"

git init -q
git config user.name fixture
git config user.email fixture@example.invalid
global_hooks_before="$(git config --global --get core.hooksPath 2>/dev/null || true)"
check "Git QA configures repository-local hooks" .ai-kit/scripts/git-qa.sh setup
check "Git QA local hook path is canonical" bash -c '[ "$(git config --local --get core.hooksPath)" = .githooks ]'
global_hooks_after="$(git config --global --get core.hooksPath 2>/dev/null || true)"
check "Git QA leaves global hook config unchanged" bash -c '[ "$1" = "$2" ]' _ "$global_hooks_before" "$global_hooks_after"

printf '%s\n' safe > 'safe file.txt'
printf '%s\n' '.workspace/' > .gitignore
git add 'safe file.txt'
check "G4 accepts a safe staged filename with spaces" .ai-kit/scripts/check-gates.sh staged
git commit -qm 'safe fixture'
check "G4 all mode accepts safe tracked content" .ai-kit/scripts/check-gates.sh all
check "Git QA validates tracked and untracked worktree files" .ai-kit/scripts/git-qa.sh check worktree

mkdir -p .workspace
printf '%s\n' ignored > .workspace/ignored.txt
check "Git QA ignores ephemeral workspace files" .ai-kit/scripts/git-qa.sh check worktree

printf 'AKIA%s\n' '0000000000000000' > untracked-secret.txt
if .ai-kit/scripts/git-qa.sh check worktree >/dev/null 2>&1; then
  echo "FAIL: Git QA must reject a secret in an untracked file" >&2
  exit 1
fi
echo "PASS: Git QA rejects secrets in untracked files"
pass=$((pass+1))
rm -f untracked-secret.txt

EXTERNAL_SECRET="$TMP/external-secret.txt"
printf 'AKIA%s\n' '1111111111111111' > "$EXTERNAL_SECRET"
ln -s "$EXTERNAL_SECRET" external-secret-link
symlink_output="$(.ai-kit/scripts/git-qa.sh check worktree 2>&1)"
check "Git QA does not dereference external symlink targets" bash -c 'printf "%s" "$1" | grep -q "GIT_QA OK" && ! printf "%s" "$1" | grep -q "AKIA"' _ "$symlink_output"

printf '%s\n' base > conflict.txt
git add conflict.txt .gitignore
git commit -qm 'conflict base'
base_branch="$(git branch --show-current)"
git checkout -qb qa-conflict
printf '%s\n' other > conflict.txt
git commit -qam 'other side'
git checkout -q "$base_branch"
printf '%s\n' current > conflict.txt
git commit -qam 'current side'
git merge qa-conflict >/dev/null 2>&1 || true
if .ai-kit/scripts/git-qa.sh check worktree >/dev/null 2>&1; then
  echo "FAIL: Git QA must reject unresolved merge conflicts" >&2
  exit 1
fi
echo "PASS: Git QA rejects unresolved merge conflicts"
pass=$((pass+1))
git merge --abort

printf '%s\n' leak > .workspace/leak.txt
git add -f .workspace/leak.txt
if .ai-kit/scripts/check-gates.sh staged >/dev/null 2>&1; then
  echo "FAIL: G4 must reject committed workspace content" >&2
  exit 1
fi
echo "PASS: G4 rejects committed workspace content"
pass=$((pass+1))

echo "AI-Kit mechanics tests OK: $pass assertions"
