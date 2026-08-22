#!/usr/bin/env bash
# Explicit local entry point for the provider-neutral AI-Kit harness.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export PYTHONDONTWRITEBYTECODE=1
exec python3 "$ROOT/.ai/harness/cli.py" --root "$ROOT" "$@"
