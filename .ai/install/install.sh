#!/usr/bin/env bash
# Bootstrap an AI-Kit project from a copied .ai/ directory.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd -P)"
MANIFEST="$SCRIPT_DIR/manifest.txt"
TEMPLATES="$SCRIPT_DIR/templates"
MODE=install
GIT_ENABLED=true
fail=0

usage() {
  cat >&2 <<EOF
usage: bash .ai/install/install.sh [--check] [--no-git]

  --check   verify bootstrap state without changing files
  --no-git  do not initialize or configure a Git repository
EOF
  exit 2
}

error() {
  echo "INSTALL FAIL: $*" >&2
  fail=1
}

for argument in "$@"; do
  case "$argument" in
    --check) MODE=check ;;
    --no-git) GIT_ENABLED=false ;;
    -h|--help) usage ;;
    *) usage ;;
  esac
done

[ -f "$ROOT/.ai/ai.yaml" ] || {
  echo "INSTALL FAIL: expected copied AI-Kit at $ROOT/.ai" >&2
  exit 2
}
[ "$SCRIPT_DIR" = "$ROOT/.ai/install" ] || {
  echo "INSTALL FAIL: installer must run from <project>/.ai/install" >&2
  exit 2
}
[ -f "$MANIFEST" ] && [ ! -L "$MANIFEST" ] || {
  echo "INSTALL FAIL: missing regular manifest $MANIFEST" >&2
  exit 2
}

safe_directory_path() {
  local relative="$1" require_existing="${2:-false}" current="$ROOT" part
  local -a parts
  IFS='/' read -r -a parts <<< "$relative"
  for part in "${parts[@]}"; do
    [ -n "$part" ] || { error "invalid empty path component: $relative"; return; }
    [ "$part" != . ] && [ "$part" != .. ] || {
      error "unsafe directory path: $relative"
      return
    }
    current="$current/$part"
    if [ -L "$current" ]; then
      error "directory path is a symlink: $current"
      return
    fi
    if [ -e "$current" ] && [ ! -d "$current" ]; then
      error "directory path is not a directory: $current"
      return
    fi
  done
  if [ "$require_existing" = true ] && [ ! -d "$ROOT/$relative" ]; then
    error "missing directory: $ROOT/$relative"
  fi
}

safe_file_parent() {
  local relative="$1" parent
  parent="${relative%/*}"
  [ "$parent" != "$relative" ] || return 0
  safe_directory_path "$parent" false
}

validate_manifest_source() {
  local source="$1" destination="$2" mode="$3" kind="$4"
  case "$source" in ''|/*|*..*) error "invalid manifest source: $source"; return ;; esac
  case "$destination" in ''|/*|*..*) error "invalid manifest destination: $destination"; return ;; esac
  case "$mode" in 0644|0755) ;; *) error "invalid manifest mode for $destination: $mode"; return ;; esac
  case "$kind" in managed|seed) ;; *) error "invalid manifest kind for $destination: $kind"; return ;; esac
  if [ ! -f "$TEMPLATES/$source" ] || [ -L "$TEMPLATES/$source" ]; then
    error "missing regular template: $TEMPLATES/$source"
  fi
}

preflight_managed_file() {
  local source="$1" destination="$2" mode="$3" kind="$4" target="$ROOT/$destination"
  safe_file_parent "$destination"
  if [ -L "$target" ]; then
    error "managed destination is a symlink: $target"
  elif [ -e "$target" ] && [ ! -f "$target" ]; then
    error "managed destination is not a regular file: $target"
  elif [ "$kind" = managed ] && [ -f "$target" ] && ! cmp -s "$TEMPLATES/$source" "$target"; then
    error "managed destination differs; reconcile it manually: $target"
  elif [ "$MODE" = check ] && [ ! -f "$target" ]; then
    error "missing managed file: $target"
  elif [ "$MODE" = check ] && [ "$mode" = 0755 ] && [ ! -x "$target" ]; then
    error "managed file is not executable: $target"
  fi
}

required_directories=(features .project .workspace .agents/skills .claude/skills)
for directory in "${required_directories[@]}"; do
  if [ "$MODE" = check ]; then
    safe_directory_path "$directory" true
  else
    safe_directory_path "$directory" false
  fi
done

destinations=$'\n'
while IFS='|' read -r source destination mode kind; do
  case "$source" in ''|\#*) continue ;; esac
  kind="${kind:-managed}"
  validate_manifest_source "$source" "$destination" "$mode" "$kind"
  case "$destinations" in
    *$'\n'"$destination"$'\n'*) error "duplicate manifest destination: $destination" ;;
    *) destinations="${destinations}${destination}"$'\n' ;;
  esac
  preflight_managed_file "$source" "$destination" "$mode" "$kind"
done < "$MANIFEST"

IGNORE_FILE="$ROOT/.gitignore"
if [ -L "$IGNORE_FILE" ]; then
  error ".gitignore is a symlink: $IGNORE_FILE"
elif [ -e "$IGNORE_FILE" ] && [ ! -f "$IGNORE_FILE" ]; then
  error ".gitignore is not a regular file: $IGNORE_FILE"
fi
if [ ! -f "$TEMPLATES/gitignore.entries" ] || [ -L "$TEMPLATES/gitignore.entries" ]; then
  error "missing regular template: $TEMPLATES/gitignore.entries"
else
  while IFS= read -r entry || [ -n "$entry" ]; do
    [ -n "$entry" ] || continue
    if [ "$MODE" = check ] && { [ ! -f "$IGNORE_FILE" ] || ! grep -Fqx -- "$entry" "$IGNORE_FILE"; }; then
      error "missing .gitignore entry: $entry"
    fi
  done < "$TEMPLATES/gitignore.entries"
fi

if [ "$fail" -ne 0 ]; then
  echo "INSTALL FAIL: preflight found conflicts; no bootstrap files were written" >&2
  exit 1
fi

check_git_state() {
  local status
  if [ "$GIT_ENABLED" != true ]; then
    echo "INSTALL git=skipped reason=disabled"
    return 0
  fi
  if ! command -v git >/dev/null 2>&1; then
    echo "INSTALL git=skipped reason=unavailable"
    return 0
  fi
  status="$(GIT_OPTIONAL_LOCKS=0 bash "$ROOT/.ai/scripts/git-qa.sh" status)"
  printf '%s\n' "$status"
  printf '%s' "$status" | grep -q 'repository=yes.*hooks=enabled' || {
    echo "INSTALL FAIL: Git QA is not initialized with repository-local hooks" >&2
    return 1
  }
}

if [ "$MODE" = check ]; then
  bash "$ROOT/.ai/scripts/sync-skills.sh" --check
  check_git_state
  bash "$ROOT/.ai/scripts/validate-kit.sh"
  echo "AI-Kit install check OK: $ROOT"
  exit 0
fi

for directory in "${required_directories[@]}"; do
  mkdir -p "$ROOT/$directory"
done

while IFS='|' read -r source destination mode kind; do
  case "$source" in ''|\#*) continue ;; esac
  target="$ROOT/$destination"
  mkdir -p "$(dirname "$target")"
  if [ ! -f "$target" ]; then
    cp "$TEMPLATES/$source" "$target"
  fi
  if [ "$mode" = 0755 ]; then
    chmod ugo+x "$target"
  fi
done < "$MANIFEST"

touch "$IGNORE_FILE"
needs_ignore_separator=false
if [ -s "$IGNORE_FILE" ] && [ "$(tail -c 1 "$IGNORE_FILE" | wc -l | tr -d ' ')" -eq 0 ]; then
  needs_ignore_separator=true
fi
while IFS= read -r entry || [ -n "$entry" ]; do
  [ -n "$entry" ] || continue
  if ! grep -Fqx -- "$entry" "$IGNORE_FILE"; then
    if [ "$needs_ignore_separator" = true ]; then
      printf '\n' >> "$IGNORE_FILE"
      needs_ignore_separator=false
    fi
    printf '%s\n' "$entry" >> "$IGNORE_FILE"
  fi
done < "$TEMPLATES/gitignore.entries"

bash "$ROOT/.ai/scripts/sync-skills.sh"
if [ "$GIT_ENABLED" != true ]; then
  echo "INSTALL git=skipped reason=disabled"
elif command -v git >/dev/null 2>&1; then
  bash "$ROOT/.ai/scripts/git-qa.sh" setup --init
else
  echo "INSTALL git=skipped reason=unavailable"
fi

bash "$ROOT/.ai/scripts/validate-kit.sh"
echo "AI-Kit install complete: $ROOT"
echo "Next: review git status, then create the baseline commit yourself when ready."
