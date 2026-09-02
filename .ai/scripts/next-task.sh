#!/usr/bin/env bash
# next-task.sh — list claimable tasks, or claim one (repo-native coordination)
# Usage:
#   next-task.sh <feature>                          # list ready tasks
# Task transitions are coordinator-only and must use orchestrate.py.
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
# The command is intentionally rooted at the caller's project checkout. This
# keeps copied AI-Kit fixtures and installed kits portable; SCRIPT_DIR only
# locates the helper DAG implementation.
ROOT="$(pwd -P)"

[ -f "$TASKS" ] || { echo "ERROR: $TASKS not found" >&2; exit 2; }

if [ -n "$CLAIM" ]; then
  echo "ERROR: task transitions are coordinator-only; use .ai/scripts/orchestrate.py" >&2
  exit 1
fi

# Prefer the canonical DAG when this checkout has the full AI-Kit policy. The
# small fallback below keeps the portable fixture/legacy mode usable when only
# next-task.sh was copied into a project.
if [ -f "$ROOT/.ai/config.json" ] && [ -f "$SCRIPT_DIR/dag.py" ]; then
  if ! dag_report="$(python3 "$SCRIPT_DIR/dag.py" "$FEATURE" --json 2>/dev/null)"; then
    echo "No claimable tasks: DAG is invalid or blocked." >&2
    exit 1
  fi
  dispatchable="$(printf '%s' "$dag_report" | python3 -c 'import json,sys; print("\n".join(json.load(sys.stdin).get("dispatchable", [])))')"
  if [ -z "$dispatchable" ]; then
    echo "No claimable tasks (all done, claimed, blocked, or conflicted)." >&2
    exit 1
  fi
  while IFS= read -r line; do
    task_id="$(printf '%s\n' "$line" | grep -oE '^- \[[ xX]\] T[0-9]+' | grep -oE 'T[0-9]+' || true)"
    case " $dispatchable " in
      *" $task_id "*) echo "$line" ;;
    esac
  done < "$TASKS"
  exit 0
fi

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
