#!/usr/bin/env bash
# Sync canonical .ai-kit/skills into Codex and Claude discovery directories.
# Usage: sync-skills.sh [--check]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
MODE="${1:-sync}"
[ "$MODE" = "sync" ] || [ "$MODE" = "--check" ] || { echo "usage: $0 [--check]" >&2; exit 2; }

SOURCE="$ROOT/.ai-kit/skills"
TARGETS=("$ROOT/.agents/skills" "$ROOT/.claude/skills")
status=0

for skill_dir in "$SOURCE"/*; do
  [ -d "$skill_dir" ] || continue
  name="$(basename "$skill_dir")"
  source_file="$skill_dir/SKILL.md"
  [ -f "$source_file" ] || { echo "missing canonical skill: $source_file" >&2; status=1; continue; }

  for target_root in "${TARGETS[@]}"; do
    target_file="$target_root/$name/SKILL.md"
    if [ "$MODE" = "--check" ]; then
      if [ ! -f "$target_file" ] || ! cmp -s "$source_file" "$target_file"; then
        echo "skill projection drift: $target_file" >&2
        status=1
      fi
    else
      mkdir -p "$(dirname "$target_file")"
      cp "$source_file" "$target_file"
    fi
  done
done

for target_root in "${TARGETS[@]}"; do
  for projected_dir in "$target_root"/ai-kit-*; do
    [ -d "$projected_dir" ] || continue
    name="$(basename "$projected_dir")"
    if [ ! -f "$SOURCE/$name/SKILL.md" ]; then
      echo "stale skill projection: $projected_dir" >&2
      status=1
    fi
  done
done

exit "$status"
