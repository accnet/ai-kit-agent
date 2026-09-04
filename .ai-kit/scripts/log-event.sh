#!/usr/bin/env bash
# log-event.sh — append one event to the execution log (.project/log.jsonl)
# Usage: log-event.sh <event> <feature|-> <task|-> <actor> [detail]
# Events: claimed | gate_pass | gate_fail | retry | completed | escalated
set -euo pipefail

EVENT="${1:?usage: log-event.sh <event> <feature|-> <task|-> <actor> [detail]}"
FEATURE="${2:--}"
TASK="${3:--}"
ACTOR="${4:-unknown}"
DETAIL="${5:-}"

LOG=".project/log.jsonl"
mkdir -p .project

# minimal JSON escaping for detail (quotes, backslashes)
esc() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }

printf '{"ts":"%s","event":"%s","feature":"%s","task":"%s","actor":"%s","detail":"%s"}\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  "$(esc "$EVENT")" "$(esc "$FEATURE")" "$(esc "$TASK")" "$(esc "$ACTOR")" "$(esc "$DETAIL")" \
  >> "$LOG"
