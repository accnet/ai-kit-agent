#!/usr/bin/env bash
# Compact, artifact-backed reporting wrapper. Existing QA runners remain intact.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
exec python3 "$ROOT/.ai-kit/scripts/qa_report.py" "$@"
