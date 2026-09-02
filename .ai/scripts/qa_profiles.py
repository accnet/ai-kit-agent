#!/usr/bin/env python3
"""Fail-closed validation for repository-owned QA command profiles."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, List, Optional


PROFILE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
FEATURE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
TASK_ID = re.compile(r"^(?:T\d+|[a-z0-9][a-z0-9_-]*)$")
UNSAFE_TOKEN = re.compile(r"[;&|<>`$()]")


def _under_root(root: Path, value: str) -> bool:
    if not value or value.startswith(("/", "\\")) or ".." in Path(value).parts:
        return False
    candidate = (root / value).resolve()
    root = root.resolve()
    return candidate == root or root in candidate.parents


def validate(root: Path, path: Optional[Path] = None) -> List[str]:
    path = path or root / ".ai/qa-profiles.json"
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read QA profiles: {exc}"]
    errors: List[str] = []
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        return ["QA profiles must be an object with schema_version 1"]
    profiles = data.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        return ["QA profiles must contain a non-empty profiles object"]
    for name, profile in profiles.items():
        prefix = f"profile '{name}':"
        if not isinstance(name, str) or not PROFILE_ID.fullmatch(name):
            errors.append(f"{prefix} invalid profile identifier")
            continue
        if not isinstance(profile, dict):
            errors.append(f"{prefix} value must be an object")
            continue
        required = {"command", "cwd", "timeout_seconds", "evidence"}
        unknown = set(profile) - required
        missing = required - set(profile)
        if unknown:
            errors.append(f"{prefix} unknown field(s): {', '.join(sorted(unknown))}")
        if missing:
            errors.append(f"{prefix} missing field(s): {', '.join(sorted(missing))}")
            continue
        command = profile["command"]
        if (
            not isinstance(command, list)
            or not command
            or any(not isinstance(token, str) or not token or UNSAFE_TOKEN.search(token) for token in command)
        ):
            errors.append(f"{prefix} command must be a non-empty safe argument array")
        cwd = profile["cwd"]
        if not isinstance(cwd, str) or not _under_root(root, cwd) or not (root / cwd).resolve().is_dir():
            errors.append(f"{prefix} cwd must be an existing repository-relative directory")
        timeout = profile["timeout_seconds"]
        if isinstance(timeout, bool) or not isinstance(timeout, int) or not 30 <= timeout <= 3600:
            errors.append(f"{prefix} timeout_seconds must be an integer from 30 to 3600")
        evidence = profile["evidence"]
        if not isinstance(evidence, dict) or set(evidence) != {"feature", "task", "artifacts"}:
            errors.append(f"{prefix} evidence must contain exactly feature, task, and artifacts")
            continue
        if not isinstance(evidence["feature"], str) or not FEATURE_ID.fullmatch(evidence["feature"]):
            errors.append(f"{prefix} evidence.feature is invalid")
        if not isinstance(evidence["task"], str) or not TASK_ID.fullmatch(evidence["task"]):
            errors.append(f"{prefix} evidence.task is invalid")
        artifacts = evidence["artifacts"]
        if not isinstance(artifacts, list) or not artifacts or any(not isinstance(item, str) or not item for item in artifacts):
            errors.append(f"{prefix} evidence.artifacts must be a non-empty string list")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--file", type=Path, default=None)
    args = parser.parse_args()
    errors = validate(args.root.resolve(), args.file.resolve() if args.file else None)
    if errors:
        for error in errors:
            print(f"AI-Kit QA profiles FAIL: {error}")
        return 1
    print("AI-Kit QA profiles OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
