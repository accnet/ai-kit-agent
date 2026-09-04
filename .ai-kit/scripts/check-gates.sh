#!/usr/bin/env bash
# Gate G4 repository hygiene checks.
# Usage: check-gates.sh staged|all|worktree
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

MODE="${1:-staged}"
case "$MODE" in
  staged|all|worktree) ;;
  *) echo "usage: $0 staged|all|worktree" >&2; exit 2 ;;
esac
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "G4 ERROR: not inside a Git worktree" >&2; exit 2; }

files=()
if [ "$MODE" = "staged" ]; then
  while IFS= read -r -d '' file; do files+=("$file"); done < <(git diff --cached --name-only --diff-filter=ACM -z)
elif [ "$MODE" = "all" ]; then
  while IFS= read -r -d '' file; do files+=("$file"); done < <(git ls-files -z)
else
  while IFS= read -r -d '' file; do files+=("$file"); done < <(git ls-files --cached --others --exclude-standard -z)
fi

[ "${#files[@]}" -gt 0 ] || exit 0
fail=0

for file in "${files[@]}"; do
  case "$file" in
    .workspace/*)
      echo "G4 FAIL: .workspace content must not be committed: $file" >&2
      fail=1
      ;;
  esac
done

# Kit definitions and project planning records may DESCRIBE .workspace; product code may not depend
# on it. Plans and task files legitimately explain which paths stay ignored, so .project/* is
# exempt from the mention scan. .knowledge-index/ is a derived projection of already-exempt
# .ai-kit/knowledge/ and .project/*/decisions.md content (see architecture.md #5: summaries are
# inert data, quoted verbatim), so a projected mention is exempt for the same reason its source
# is. Committing .workspace CONTENT is still blocked by the loop above, which is the protection
# that actually matters.
for file in "${files[@]}"; do
  case "$file" in
    .ai-kit/*|.agents/*|.project/*|.knowledge-index/*|AGENTS.md|CLAUDE.md|README.md|ROADMAP.md|CHANGELOG.md|.gitignore|.githooks/*|.github/*|.claude/*|.cursor/*|.windsurf/*) continue ;;
  esac
  [ -L "$file" ] && continue
  [ -f "$file" ] || continue
  if grep -qE '\.workspace/' "$file" 2>/dev/null; then
    echo "G4 FAIL: committed file references ephemeral .workspace state: $file" >&2
    fail=1
  fi
done

secret_patterns='-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----|AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{36}|xox[baprs]-[A-Za-z0-9-]+'
for file in "${files[@]}"; do
  [ -L "$file" ] && continue
  [ -f "$file" ] || continue
  case "$file" in *.png|*.jpg|*.jpeg|*.gif|*.pdf|*.zip|*.ico) continue ;; esac
  hits="$(grep -nE -e "$secret_patterns" "$file" 2>/dev/null | head -3 || true)"
  if [ -n "$hits" ]; then
    echo "G4 FAIL: possible secret in $file:" >&2
    echo "$hits" >&2
    fail=1
  fi
done

if [ "$fail" -ne 0 ]; then
  echo "Gate G4 blocked. Fix the reported hygiene violations." >&2
  exit 1
fi

echo "G4 OK ($MODE)"
