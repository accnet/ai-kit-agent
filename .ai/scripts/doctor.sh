#!/usr/bin/env bash
# Diagnose the local AI-Kit checkout. Use --full to include mechanics tests.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

case "${1:-}" in
  '') .ai/scripts/validate-kit.sh; python3 .ai/scripts/consistency.py; python3 .ai/scripts/qa_profiles.py; bash .ai/scripts/git-qa.sh status ;;
  --full)
    .ai/scripts/validate-kit.sh
    python3 .ai/scripts/consistency.py
    python3 .ai/scripts/qa_profiles.py
    bash .ai/scripts/git-qa.sh status
    bash .ai/tests/run.sh
    bash .ai/scripts/git-qa.sh check worktree
    ;;
  *) echo "usage: $0 [--full]" >&2; exit 2 ;;
esac
