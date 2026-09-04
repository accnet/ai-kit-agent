#!/usr/bin/env bash
# context-pack.sh — emit the deterministic tier-1 context pack for a task
# Usage: context-pack.sh <feature> T<n>
# Pack = task line + acceptance criteria + brief + files: scope contents
#        + matching .ai-kit/knowledge/ entries. Same task → same pack.
# The agent starts from this pack, then agentic-searches the rest (tier 2+).
set -euo pipefail

FEATURE="${1:?usage: context-pack.sh <feature> T<n>}"
TID="${2:?usage: context-pack.sh <feature> T<n>}"
TASKS=".project/$FEATURE/tasks.md"
[ -f "$TASKS" ] || { echo "ERROR: $TASKS not found" >&2; exit 2; }
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f ".project/$FEATURE/state.json" ]; then
  python3 "$SCRIPT_DIR/task_state.py" "$FEATURE" --require-projection >/dev/null || {
    echo "ERROR: canonical task state is invalid or its projection is stale" >&2
    exit 1
  }
fi

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
# .knowledge-index/ present and non-empty -> deterministic index-first top-K
# (see .ai-kit/modules/context/knowledge-loader.md). Otherwise, byte-identical
# fallback to the original live grep over .ai-kit/knowledge/.
title=$(echo "$task_line" | sed -E 's/^- \[.\] T[0-9]+ //' | cut -d'|' -f1)
kw_list="$FEATURE $(echo "$title" | tr 'A-Z' 'a-z' | grep -oE '[a-z]{4,}' | head -4)"
KIDX=".knowledge-index/index.json"

use_index=0
if [ -f "$KIDX" ] && python3 -c "
import json
d = json.load(open('$KIDX', encoding='utf-8'))
raise SystemExit(0 if d.get('items') else 1)
" >/dev/null 2>&1; then
  use_index=1
fi

if [ "$use_index" -eq 1 ]; then
  python3 - "$KIDX" "$kw_list" <<'PY'
import json, re, sys

index_path, kw_line = sys.argv[1], sys.argv[2]
task_keywords = set(kw_line.lower().split())
data = json.load(open(index_path, encoding="utf-8"))
items = data.get("items", [])

def topic_slug(item):
    return re.sub(r"[^a-z0-9]+", "-", item.get("topic", "").lower()).strip("-")

approved = [it for it in items if it.get("status") == "approved"]
scored = []
for it in approved:
    score = len(task_keywords & set(it.get("keywords", [])))
    if score > 0:
        scored.append((score, it))
scored.sort(key=lambda pair: (-pair[0], pair[1].get("precedence", 99), pair[1].get("id", "")))

TOP_K = 5
top = [it for _, it in scored[:TOP_K]]

if not top:
    print("(no relevant approved .knowledge-index/ items for this task's keywords)")
else:
    by_topic = {}
    for it in top:
        by_topic.setdefault(topic_slug(it), []).append(it)
    for it in top:
        group = by_topic[topic_slug(it)]
        conflict = (len({g["source_path"] for g in group}) > 1
                    and len({g["summary"] for g in group}) > 1)
        tag = "CONFLICT: " if conflict else ""
        print(f"--- {tag}{it['topic']} (source: {it['source_path']}, status: approved) ---")
        print(it["summary"])
    if len(scored) > TOP_K:
        print(f"... ({len(scored) - TOP_K} more relevant item(s) not shown — top-{TOP_K} budget)")

# never silently prefer a stale summary: point at the source instead
stale_hits = [it for it in items
              if it.get("status") == "stale" and task_keywords & set(it.get("keywords", []))]
for it in stale_hits[:3]:
    print(f"--- stale: see {it['source_path']} directly (was: {it['topic']}) ---")
PY
else
  hits=0
  for kw in $kw_list; do
    found=$(grep -ri -A3 "$kw" .ai-kit/knowledge/ 2>/dev/null | head -12 || true)
    if [ -n "$found" ]; then echo "--- matches for '$kw' ---"; echo "$found"; hits=1; fi
  done
  [ "$hits" -eq 0 ] && echo "(none)"
fi

echo ""
echo "=== NEXT ==="
echo "This is tier 1 (never cut). Load modules per .ai-kit/modules/INDEX.md; agentic-search tier 2+ on demand."
