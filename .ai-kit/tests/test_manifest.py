#!/usr/bin/env python3
"""Validate the explicit reusable AI-Kit mechanics-suite manifest."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / ".ai-kit/tests/manifest.json"


def main() -> int:
    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: cannot read manifest: {exc}")
        return 1
    suites = data.get("suites")
    if data.get("schema_version") != 1 or not isinstance(suites, list) or not suites:
        print("FAIL: manifest must have schema_version 1 and a non-empty suites list")
        return 1
    errors = []
    seen = set()
    for suite in suites:
        path = ROOT / ".ai-kit/tests" / suite if isinstance(suite, str) else None
        if not isinstance(suite, str) or suite in seen:
            errors.append(f"duplicate or non-string suite: {suite!r}")
            continue
        seen.add(suite)
        if not suite.startswith("test_") or not suite.endswith(".py"):
            errors.append(f"suite is not a test module: {suite}")
        if "/" in suite or "\\" in suite or suite in {"test_harness.py", "test_manifest.py"}:
            errors.append(f"suite must be an AI-Kit suite, not a runner/helper: {suite}")
        if path is None or not path.is_file():
            errors.append(f"suite file is missing: {suite}")
    actual = {path.name for path in (ROOT / ".ai-kit/tests").glob("test_*.py") if path.name not in {"test_harness.py", "test_manifest.py"}}
    missing = sorted(actual - seen)
    stale = sorted(seen - actual)
    if missing:
        errors.append("unlisted test suites: " + ", ".join(missing))
    if stale:
        errors.append("manifest entries without files: " + ", ".join(stale))
    if errors:
        print("FAIL: " + "; ".join(errors))
        return 1
    print(f"PASS: explicit AI-Kit mechanics manifest ({len(suites)} suites)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
