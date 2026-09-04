#!/usr/bin/env python3
"""Fail-closed checks for AI-Kit session pointers and worker isolation policy."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SESSION_FEATURE = re.compile(r"^feature:\s*(\S+)\s*$", re.MULTILINE)
SESSION_TASK = re.compile(r"^task:\s*(T\d+)\s*$", re.MULTILINE)
INDEX_ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", re.MULTILINE)
TASK_ROW = re.compile(r"^- \[([ xX])\]\s*(T\d+)\b", re.MULTILINE)
FEATURE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def check(root: Path) -> list[str]:
    errors: list[str] = []
    config_path = root / ".ai-kit/config.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read AI-Kit config: {exc}"]

    orchestration = config.get("orchestration")
    execution = config.get("execution")
    if not isinstance(orchestration, dict) or not isinstance(execution, dict):
        errors.append("orchestration and execution policies must be objects")
    else:
        isolated = execution.get("isolated_worktree")
        if orchestration.get("enabled") is True and orchestration.get("require_worktree_per_worker") is True:
            if not isinstance(isolated, dict) or isolated.get("required") is not True:
                errors.append("worker policy requires isolated_worktree.required=true")

    session_path = root / ".workspace/session.md"
    if not session_path.exists():
        return errors
    try:
        session = session_path.read_text(encoding="utf-8")
    except OSError as exc:
        return errors + [f"cannot read session pointer: {exc}"]
    feature_match = SESSION_FEATURE.search(session)
    task_match = SESSION_TASK.search(session)
    if not feature_match or not task_match:
        errors.append("session pointer must declare feature and task")
        return errors
    feature = feature_match.group(1)
    task = task_match.group(1)
    if not FEATURE_ID.fullmatch(feature):
        errors.append(f"session feature '{feature}' is not a safe project identifier")
        return errors
    index_path = root / ".project/INDEX.md"
    try:
        index = index_path.read_text(encoding="utf-8")
    except OSError as exc:
        return errors + [f"cannot read project index: {exc}"]
    states = {name.strip(): state.strip() for name, state in INDEX_ROW.findall(index)}
    if states.get(feature) != "active":
        errors.append(f"session feature '{feature}' is not active in .project/INDEX.md")
    tasks_path = root / ".project" / feature / "tasks.md"
    try:
        tasks = tasks_path.read_text(encoding="utf-8")
    except OSError:
        errors.append(f"session feature '{feature}' has no tasks.md")
        return errors
    task_rows = {task_id: checked.lower() == "x" for checked, task_id in TASK_ROW.findall(tasks)}
    if task not in task_rows:
        errors.append(f"session task '{task}' does not exist in {tasks_path}")
    elif task_rows[task]:
        errors.append(f"session task '{task}' is already complete")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    errors = check(args.root.resolve())
    if errors:
        for error in errors:
            print(f"AI-Kit consistency FAIL: {error}")
        return 1
    print("AI-Kit consistency OK: worker policy and session pointer")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
