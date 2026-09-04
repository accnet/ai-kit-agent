#!/usr/bin/env bash
# knowledge-bootstrap.sh — safe, explicit bootstrap for .knowledge-index/
# Contract: .project/project-knowledge-index/architecture.md
# Policy:   .knowledge-index/README.md
#
# This is a separate, explicit, user-invoked step. install.sh never calls it
# and never performs semantic project scanning itself.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd -P)"
PROJECTOR="$SCRIPT_DIR/knowledge-projector.py"
README_TEMPLATE="$SCRIPT_DIR/../install/templates/knowledge-index-README.md"
KDIR="$ROOT/.knowledge-index"
MODE=""
fail=0

usage() {
  cat >&2 <<'EOF'
usage: bash .ai-kit/scripts/knowledge-bootstrap.sh --initial|--check|--refresh

  --initial   First-time bootstrap: create .knowledge-index/ and run the
              projector for the first time. Fails closed (writes nothing) if
              the directory already holds real projected content — use
              --refresh instead.
  --check     Read-only: validate .knowledge-index/ structure, and source
              hash freshness when the projector is available. Never writes.
  --refresh   Recompute an existing projection: updates only approved/stale
              knowledge outputs. Fails closed with no partial writes on any
              conflict, malformed source, or redaction reject.

Never installs dependencies, calls a model, or uses the network.
EOF
  exit 2
}

error() { echo "KNOWLEDGE-BOOTSTRAP FAIL: $*" >&2; fail=1; }

[ "$#" -eq 1 ] || usage
case "$1" in
  --initial) MODE=initial ;;
  --check) MODE=check ;;
  --refresh) MODE=refresh ;;
  -h|--help) usage ;;
  *) usage ;;
esac

[ -f "$ROOT/.ai-kit/ai.yaml" ] || {
  echo "KNOWLEDGE-BOOTSTRAP FAIL: expected an installed AI-Kit at $ROOT/.ai-kit (run .ai-kit/install/install.sh first)" >&2
  exit 2
}

# --- structural checks: no projector required -------------------------------

index_items_empty() {
  [ -f "$KDIR/index.json" ] || return 1
  python3 - "$KDIR/index.json" <<'PY' 2>/dev/null
import json, sys
try:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception:
    sys.exit(1)
sys.exit(0 if data.get("items") == [] else 1)
PY
}

validate_structure() {
  # read-only: reports every problem found, never writes
  [ -d "$KDIR" ] || { error "$KDIR does not exist; run --initial first"; return; }
  for f in README.md index.json project-map.md; do
    [ -f "$KDIR/$f" ] || error "$KDIR/$f is missing"
  done
  if [ -f "$KDIR/index.json" ]; then
    python3 - "$KDIR/index.json" <<'PY' || error "$KDIR/index.json is not a valid envelope (schema_version, generated_at, generator_version, items[])"
import json, sys
try:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
    assert data.get("schema_version") == 1
    assert isinstance(data.get("items"), list)
    for item in data["items"]:
        for key in ("id", "source_path", "source_hash", "status", "precedence", "keywords"):
            assert key in item, f"item missing {key}"
        assert item["status"] in ("approved", "stale", "superseded", "rejected")
except Exception:
    sys.exit(1)
PY
  fi
}

# --- dispatch -----------------------------------------------------------------

case "$MODE" in
  initial)
    if [ -d "$KDIR" ] && ! index_items_empty; then
      error "$KDIR already has projected content; use --refresh instead of --initial"
    fi
    if [ "$fail" -ne 0 ]; then
      echo "KNOWLEDGE-BOOTSTRAP FAIL: preflight found conflicts; no files were written" >&2
      exit 1
    fi
    mkdir -p "$KDIR"
    if [ ! -f "$PROJECTOR" ]; then
      echo "KNOWLEDGE-BOOTSTRAP FAIL: projector not found at $PROJECTOR (implemented in a later task); no files were written" >&2
      exit 1
    fi
    # Seed the policy README once; never overwrite a project's own copy.
    if [ ! -f "$KDIR/README.md" ] && [ -f "$README_TEMPLATE" ]; then
      cp "$README_TEMPLATE" "$KDIR/README.md"
    fi
    python3 "$PROJECTOR" --root "$ROOT" --write --mode initial
    ;;
  check)
    validate_structure
    if [ -f "$PROJECTOR" ] && [ "$fail" -eq 0 ]; then
      python3 "$PROJECTOR" --root "$ROOT" --check || fail=1
    elif [ ! -f "$PROJECTOR" ]; then
      echo "KNOWLEDGE-BOOTSTRAP note: projector not present yet; structural check only, hash freshness not verified" >&2
    fi
    [ "$fail" -eq 0 ] || exit 1
    echo "KNOWLEDGE-BOOTSTRAP check=pass"
    ;;
  refresh)
    [ -d "$KDIR" ] || { echo "KNOWLEDGE-BOOTSTRAP FAIL: $KDIR does not exist; run --initial first" >&2; exit 1; }
    if [ ! -f "$PROJECTOR" ]; then
      echo "KNOWLEDGE-BOOTSTRAP FAIL: projector not found at $PROJECTOR (implemented in a later task); no files were written" >&2
      exit 1
    fi
    python3 "$PROJECTOR" --root "$ROOT" --write --mode refresh
    ;;
esac
