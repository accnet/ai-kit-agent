#!/usr/bin/env bash
# context-pack.sh — emit the deterministic tier-1 context pack for a task
# Usage: context-pack.sh <feature> T<n>
# Pack = task line + acceptance criteria + brief + files: scope contents
#        + matching .ai/knowledge/ entries. Same task → same pack.
# The agent starts from this pack, then agentic-searches the rest (tier 2+).
set -euo pipefail

FEATURE="${1:?usage: context-pack.sh <feature> T<n>}"
TID="${2:?usage: context-pack.sh <feature> T<n>}"
TASKS=".project/$FEATURE/tasks.md"
[ -f "$TASKS" ] || { echo "ERROR: $TASKS not found" >&2; exit 2; }

task_line=$(grep -E "^- \[.\] $TID " "$TASKS" || true)
[ -n "$task_line" ] || { echo "ERROR: $TID not found in $TASKS" >&2; exit 1; }

echo "=== TASK ==="
echo "$task_line"
# acceptance criteria: indented lines following the task line
awk -v tid="$TID" '
  $0 ~ "^- \\[.\\] "tid" " {grab=1; next}
  grab && /^  / {print; next}
  grab {exit}
' "$TASKS"

echo ""
echo "=== PLAN HEADER ==="
sed -n '1,10p' "$TASKS" | grep -E '^(Intent|Goal|Out of scope|Open questions)' || true

echo ""
echo "=== BRIEF ==="
BRIEF="features/$FEATURE/brief.md"
if [ -f "$BRIEF" ]; then cat "$BRIEF"; else echo "(no brief — trivial fast path?)"; fi

echo ""
echo "=== FILES IN SCOPE ==="
files=$(echo "$task_line" | grep -oE 'files: [^|]*' | sed 's/files: //' | sed 's/[[:space:]]*$//' || true)
if [ -z "$files" ] || [ "$files" = "-" ]; then
  echo "(no files scope)"
else
  for pat in $files; do
    # expand globs; list dirs; print small files whole, large files head
    for f in $(compgen -G "$pat" 2>/dev/null || echo ""); do
      if [ -d "$f" ]; then
        echo "--- $f/ (directory listing) ---"; ls -1 "$f" | head -40
      elif [ -f "$f" ]; then
        lines=$(wc -l < "$f")
        echo "--- $f ($lines lines) ---"
        if [ "$lines" -le 200 ]; then cat "$f"; else sed -n '1,120p' "$f"; echo "... (truncated at 120/$lines — read the rest on demand)"; fi
      fi
    done
    [ -e "$pat" ] || compgen -G "$pat" >/dev/null 2>&1 || echo "--- $pat (not created yet) ---"
  done
fi

echo ""
echo "=== KNOWLEDGE HITS ==="
# grep knowledge for the feature name and significant words from the task title
title=$(echo "$task_line" | sed -E 's/^- \[.\] T[0-9]+ //' | cut -d'|' -f1)
hits=0
for kw in "$FEATURE" $(echo "$title" | tr 'A-Z' 'a-z' | grep -oE '[a-z]{4,}' | head -4); do
  found=$(grep -ri -A3 "$kw" .ai/knowledge/ 2>/dev/null | head -12 || true)
  if [ -n "$found" ]; then echo "--- matches for '$kw' ---"; echo "$found"; hits=1; fi
done
[ "$hits" -eq 0 ] && echo "(none)"

echo ""
echo "=== NEXT ==="
echo "This is tier 1 (never cut). Load modules per .ai/modules/INDEX.md; agentic-search tier 2+ on demand."
