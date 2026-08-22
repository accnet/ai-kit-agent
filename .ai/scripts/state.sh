#!/usr/bin/env bash
# state.sh — render a feature's tasks.md as JSON (derived view, never stored)
# Usage: state.sh <feature>
# Output: {"feature":..., "tasks":[{id,status,owner,scope,needs,files,attempts,title}], "counts":{...}}
set -euo pipefail

FEATURE="${1:?usage: state.sh <feature>}"
TASKS=".project/$FEATURE/tasks.md"
[ -f "$TASKS" ] || { echo "ERROR: $TASKS not found" >&2; exit 2; }

esc() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }
field() { # $1=line $2=key — extract "key: value" between pipes
  echo "$1" | grep -oE "$2: [^|]*" | head -1 | sed "s/$2: //" | sed 's/[[:space:]]*$//' || true
}

first=1
tasks_json=""
n_done=0; n_prog=0; n_todo=0

while IFS= read -r line; do
  case "$line" in
    "- [x] T"*) status="done" ;;
    "- [ ] T"*) if echo "$line" | grep -q 'status: in-progress'; then status="in-progress"; else status="todo"; fi ;;
    *) continue ;;
  esac
  id=$(echo "$line" | grep -oE 'T[0-9]+' | head -1)
  title=$(echo "$line" | sed -E 's/^- \[.\] T[0-9]+ //' | cut -d'|' -f1 | sed 's/[[:space:]]*$//')
  owner=$(field "$line" owner); scope=$(field "$line" scope)
  needs=$(field "$line" needs); files=$(field "$line" files)
  attempts=$(field "$line" attempts); instance=$(field "$line" instance)
  [ -z "$attempts" ] && attempts=0

  case "$status" in done) n_done=$((n_done+1));; in-progress) n_prog=$((n_prog+1));; todo) n_todo=$((n_todo+1));; esac

  [ "$first" -eq 1 ] && first=0 || tasks_json="$tasks_json,"
  tasks_json="$tasks_json{\"id\":\"$id\",\"status\":\"$status\",\"owner\":\"$(esc "$owner")\",\"scope\":\"$(esc "$scope")\",\"needs\":\"$(esc "$needs")\",\"files\":\"$(esc "$files")\",\"attempts\":$attempts,\"instance\":\"$(esc "$instance")\",\"title\":\"$(esc "$title")\"}"
done < "$TASKS"

total=$((n_done+n_prog+n_todo))
printf '{"feature":"%s","tasks":[%s],"counts":{"total":%d,"done":%d,"in_progress":%d,"todo":%d}}\n' \
  "$(esc "$FEATURE")" "$tasks_json" "$total" "$n_done" "$n_prog" "$n_todo"
