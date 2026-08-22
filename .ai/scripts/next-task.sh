#!/usr/bin/env bash
# next-task.sh — list claimable tasks, or claim one (repo-native coordination)
# Usage:
#   next-task.sh <feature>                          # list claimable tasks
#   next-task.sh <feature> --claim T2 --instance x  # claim task T2 as instance x
# Claimable = unchecked, not in-progress, all `needs:` IDs already checked [x].
set -euo pipefail

FEATURE="${1:?usage: next-task.sh <feature> [--claim T<n> --instance <name>]}"
shift || true

CLAIM=""; INSTANCE="agent"
while [ $# -gt 0 ]; do
  case "$1" in
    --claim)    CLAIM="${2:?--claim needs T<n>}"; shift 2 ;;
    --instance) INSTANCE="${2:?--instance needs a name}"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

PROJECT_DIR=".project"
TASKS="$PROJECT_DIR/$FEATURE/tasks.md"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

[ -f "$TASKS" ] || { echo "ERROR: $TASKS not found" >&2; exit 2; }

done_ids=$(grep -oE '^- \[x\] T[0-9]+' "$TASKS" | grep -oE 'T[0-9]+' || true)
is_done() { echo "$done_ids" | grep -qx "$1"; }

is_claimable() { # $1 = task line
  case "$1" in "- [ ] T"*) ;; *) return 1 ;; esac
  echo "$1" | grep -q 'status: in-progress' && return 1
  local needs
  needs=$(echo "$1" | grep -oE 'needs: [^|]*' | sed 's/needs: //' | tr -d ' ' || true)
  if [ -n "$needs" ] && [ "$needs" != "-" ]; then
    for dep in $(echo "$needs" | tr ',' ' '); do
      is_done "$dep" || return 1
    done
  fi
  return 0
}

# ---- claim mode ----
if [ -n "$CLAIM" ]; then
  match=$(grep -nE "^- \[ \] $CLAIM( |\|)" "$TASKS" | head -1 || true)
  [ -n "$match" ] || { echo "ERROR: $CLAIM not found (or already checked) in $TASKS" >&2; exit 2; }
  lno="${match%%:*}"
  text="${match#*:}"
  is_claimable "$text" || { echo "ERROR: $CLAIM is blocked or already in-progress" >&2; exit 1; }
  new="$text | status: in-progress | instance: $INSTANCE"
  tmp="$(mktemp)"
  awk -v n="$lno" -v repl="$new" 'NR==n{print repl; next} {print}' "$TASKS" > "$tmp"
  cat "$tmp" > "$TASKS"; rm -f "$tmp"
  bash "$SCRIPT_DIR/log-event.sh" claimed "$FEATURE" "$CLAIM" "$INSTANCE" "claimed via next-task.sh" 2>/dev/null || true
  echo "claimed $CLAIM as $INSTANCE"
  exit 0
fi

# ---- list mode ----
claimable=0
while IFS= read -r line; do
  if is_claimable "$line"; then
    echo "$line"
    claimable=$((claimable+1))
  fi
done < "$TASKS"

if [ "$claimable" -eq 0 ]; then
  echo "No claimable tasks (all done, claimed, or blocked)." >&2
  exit 1
fi
