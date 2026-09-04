#!/usr/bin/env bash
# Project contract tests; AI-Kit runtime tests remain under .ai-kit/tests.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

python3 tests/contracts/test_grid_first_contracts.py
