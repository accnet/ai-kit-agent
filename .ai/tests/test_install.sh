#!/usr/bin/env bash
# Disposable-project regression tests for the portable installer.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd -P)"
TMP="$(mktemp -d)"
trap 'rm -rf -- "$TMP"' EXIT
pass=0

passed() {
  echo "PASS: $1"
  pass=$((pass+1))
}

copy_kit() {
  local name="$1" target
  target="$TMP/$name"
  mkdir -p "$target"
  cp -R "$ROOT/.ai" "$target/.ai"
  printf '%s' "$target"
}

tree_snapshot() {
  local target="$1"
  (
    cd "$target"
    while IFS= read -r path; do
      if [ -L "$path" ]; then
        printf 'L %s %s\n' "$path" "$(readlink "$path")"
      elif [ -d "$path" ]; then
        printf 'D %s\n' "$path"
      elif [ -f "$path" ]; then
        printf 'F '
        cksum "$path"
      fi
    done < <(find . -mindepth 1 -print | LC_ALL=C sort)
  )
}

NO_GIT="$(copy_kit 'project with spaces')"
printf '%s' '# existing project ignore' > "$NO_GIT/.gitignore"
bash "$NO_GIT/.ai/install/install.sh" --no-git >/dev/null
test -f "$NO_GIT/AGENTS.md"
test -f "$NO_GIT/CLAUDE.md"
test -x "$NO_GIT/.githooks/pre-commit"
test -f "$NO_GIT/.github/workflows/gates.yml"
test -f "$NO_GIT/.project/INDEX.md"
test -d "$NO_GIT/features" && test -d "$NO_GIT/.workspace"
cmp "$NO_GIT/.ai/skills/ai-kit-plan/SKILL.md" "$NO_GIT/.agents/skills/ai-kit-plan/SKILL.md"
cmp "$NO_GIT/.ai/skills/ai-kit-plan/SKILL.md" "$NO_GIT/.claude/skills/ai-kit-plan/SKILL.md"
test ! -e "$NO_GIT/.git"
grep -Fqx '# existing project ignore' "$NO_GIT/.gitignore"
test "$(grep -Fxc '.workspace/' "$NO_GIT/.gitignore")" -eq 1
test "$(sed -n '1p' "$NO_GIT/.gitignore")" = '# existing project ignore'
test -z "$(find "$NO_GIT" -type d -name __pycache__ -print -quit)"
passed "bootstrap preserves a non-newline ignore line and avoids bytecode caches"

snapshot_before="$(tree_snapshot "$NO_GIT")"
bash "$NO_GIT/.ai/install/install.sh" --check --no-git >/dev/null
snapshot_after="$(tree_snapshot "$NO_GIT")"
test "$snapshot_before" = "$snapshot_after"
bash "$NO_GIT/.ai/install/install.sh" --no-git >/dev/null
test "$(grep -Fxc '.workspace/' "$NO_GIT/.gitignore")" -eq 1
passed "check is filesystem-read-only and unchanged install is repeatable"

PRECHECK="$(copy_kit precheck)"
if bash "$PRECHECK/.ai/install/install.sh" --check --no-git >/dev/null 2>&1; then
  echo "FAIL: check must reject an uninstalled project" >&2
  exit 1
fi
test ! -e "$PRECHECK/AGENTS.md"
passed "check rejects missing state without bootstrapping it"

CONFLICT="$(copy_kit conflict)"
printf '%s\n' custom > "$CONFLICT/AGENTS.md"
if bash "$CONFLICT/.ai/install/install.sh" --no-git >/dev/null 2>&1; then
  echo "FAIL: install must reject a differing managed file" >&2
  exit 1
fi
test "$(cat "$CONFLICT/AGENTS.md")" = custom
test ! -e "$CONFLICT/CLAUDE.md"
test ! -e "$CONFLICT/.agents"
passed "managed-file conflict fails before bootstrap writes"

SYMLINK="$(copy_kit symlink-conflict)"
printf '%s\n' outside > "$TMP/outside-agents.md"
ln -s "$TMP/outside-agents.md" "$SYMLINK/AGENTS.md"
if bash "$SYMLINK/.ai/install/install.sh" --no-git >/dev/null 2>&1; then
  echo "FAIL: install must reject a managed destination symlink" >&2
  exit 1
fi
test "$(cat "$TMP/outside-agents.md")" = outside
test ! -e "$SYMLINK/CLAUDE.md"
passed "managed symlink is rejected without touching its target"

ESCAPE="$(copy_kit manifest-escape)"
printf '%s\n' 'AGENTS.md|../escaped.md|0644' >> "$ESCAPE/.ai/install/manifest.txt"
if bash "$ESCAPE/.ai/install/install.sh" --no-git >/dev/null 2>&1; then
  echo "FAIL: install must reject an escaping manifest destination" >&2
  exit 1
fi
test ! -e "$TMP/escaped.md"
test ! -e "$ESCAPE/AGENTS.md"
passed "manifest path escape is rejected before writes"

ORPHAN="$TMP/orphan/.ai/install"
mkdir -p "$ORPHAN"
cp "$ROOT/.ai/install/install.sh" "$ORPHAN/install.sh"
if bash "$ORPHAN/install.sh" --no-git >/dev/null 2>&1; then
  echo "FAIL: installer must require a copied .ai kit" >&2
  exit 1
fi
test ! -e "$TMP/orphan/AGENTS.md"
passed "invalid installer location is rejected"

if command -v git >/dev/null 2>&1; then
  GIT_PROJECT="$(copy_kit git-project)"
  global_before="$(git config --global --get core.hooksPath 2>/dev/null || true)"
  bash "$GIT_PROJECT/.ai/install/install.sh" >/dev/null
  test "$(git -C "$GIT_PROJECT" rev-parse --show-toplevel)" = "$GIT_PROJECT"
  test "$(git -C "$GIT_PROJECT" config --local --get core.hooksPath)" = .githooks
  test -z "$(git -C "$GIT_PROJECT" rev-parse --verify HEAD 2>/dev/null || true)"
  test -z "$(git -C "$GIT_PROJECT" diff --cached --name-only)"
  global_after="$(git config --global --get core.hooksPath 2>/dev/null || true)"
  test "$global_before" = "$global_after"
  git -C "$GIT_PROJECT" config user.name fixture
  git -C "$GIT_PROJECT" config user.email fixture@example.invalid
  git -C "$GIT_PROJECT" add .
  git -C "$GIT_PROJECT" -c core.hooksPath=/dev/null commit -qm baseline
  git_snapshot_before="$(tree_snapshot "$GIT_PROJECT")"
  bash "$GIT_PROJECT/.ai/install/install.sh" --check >/dev/null
  git_snapshot_after="$(tree_snapshot "$GIT_PROJECT")"
  test "$git_snapshot_before" = "$git_snapshot_after"
  bash "$GIT_PROJECT/.ai/install/install.sh" >/dev/null
  test "$(git -C "$GIT_PROJECT" rev-list --count HEAD)" -eq 1
  test -z "$(git -C "$GIT_PROJECT" status --porcelain=v1)"
  passed "Git setup is target-local; check is read-only and repeat adds no commit"
else
  echo "PASS: Git setup fixture skipped because Git is unavailable"
  pass=$((pass+1))
fi

echo "AI-Kit installer tests OK: $pass assertions"
