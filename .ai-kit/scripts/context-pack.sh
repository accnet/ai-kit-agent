#!/usr/bin/env bash
# Stable wrapper; scope and knowledge handling use structured Python APIs.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$SCRIPT_DIR/context_pack.py" "$@"
