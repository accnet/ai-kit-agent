#!/usr/bin/env python3
"""Canonical-first task state resolution shared by AI-Kit operators."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Tuple


TASK_LINE = re.compile(
    r"^- \[([ xX])\]\s*(T\d+)\s+(.*?)\s*\|\s*owner:\s*([^|]+?)\s*"
    r"\|\s*scope:\s*([^|]+?)\s*\|\s*needs:\s*([^|]+?)\s*"
    r"\|\s*files:\s*([^|]+?)(?:\s*\|\s*(.*))?$"
)
TASK_ID = re.compile(r"^T\d+$")


class TaskStateError(ValueError):
    """A deterministic, fail-closed state resolution error."""


def _paths(root: Path, feature: str) -> Tuple[Path, Path]:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", feature):
        raise TaskStateError("invalid feature identifier")
    project = (root / ".project").resolve()
    directory = (project / feature).resolve()
    if project not in directory.parents:
        raise TaskStateError("feature path escapes .project")
    return directory / "state.json", directory / "tasks.md"


def _needs(raw: Any) -> List[str]:
    if isinstance(raw, list):
        values = raw
    elif isinstance(raw, str):
        values = [] if raw.strip() in {"", "-"} else raw.split(",")
    else:
        raise TaskStateError("task dependencies must be an array or legacy string")
    result = [str(item).strip() for item in values if str(item).strip() and str(item).strip() != "-"]
    if any(not TASK_ID.fullmatch(item) for item in result) or len(result) != len(set(result)):
        raise TaskStateError("invalid or duplicate task dependency")
    return result


def _files(raw: Any) -> List[str]:
    if isinstance(raw, list):
        values = raw
    elif isinstance(raw, str):
        values = [] if raw.strip() in {"", "-"} else raw.split(",")
    else:
        raise TaskStateError("task files must be an array or legacy string")
    return [str(item).strip() for item in values if str(item).strip() and str(item).strip() != "-"]


def _canonical(path: Path, tasks_path: Path, feature: str) -> Dict[str, Any]:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TaskStateError("malformed canonical state: %s" % path) from exc
    if not isinstance(state, dict) or state.get("feature") != feature or not isinstance(state.get("tasks"), list):
        raise TaskStateError("canonical state has invalid feature or tasks")
    tasks: Dict[str, dict] = {}
    for raw in state["tasks"]:
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str) or not TASK_ID.fullmatch(raw["id"]):
            raise TaskStateError("canonical state contains an invalid task")
        task_id = raw["id"]
        if task_id in tasks:
            raise TaskStateError("canonical state contains duplicate task IDs")
        status = str(raw.get("state", "proposed"))
        tasks[task_id] = {
            "id": task_id,
            "title": str(raw.get("title", "")),
            "owner": str(raw.get("owner", "implementer")),
            "scope": str(raw.get("scope", "S")),
            "needs": _needs(raw.get("dependencies", [])),
            "files": _files(raw.get("files", [])),
            "checked": status == "complete",
            "status": status,
            "canonical_status": status,
            "attempts": int(raw.get("attempts", 0)),
            "instance": "",
        }
    if not tasks:
        raise TaskStateError("canonical state contains no tasks")
    known = set(tasks)
    for task in tasks.values():
        if any(dep not in known for dep in task["needs"]):
            raise TaskStateError("canonical state contains an unknown task dependency")
    projection_matches = False
    if tasks_path.exists():
        try:
            # Import the canonical renderer without making it a dependency of legacy scripts.
            harness = path.parents[2] / ".ai-kit" / "harness"
            sys.path.insert(0, str(harness))
            from projection import render_tasks  # type: ignore
            projection_matches = tasks_path.read_text(encoding="utf-8") == render_tasks(state)
        except (OSError, ValueError, KeyError, ImportError):
            projection_matches = False
    return {"feature": feature, "tasks": tasks, "source": "state.json", "canonical": True,
            "projection_matches": projection_matches, "projection_exists": tasks_path.exists(),
            "state": state}


def _legacy(path: Path, feature: str) -> Dict[str, Any]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise TaskStateError("cannot read legacy tasks file: %s" % path) from exc
    tasks: Dict[str, dict] = {}
    for number, line in enumerate(lines, 1):
        if not line.startswith("- ["):
            continue
        match = TASK_LINE.match(line)
        if not match:
            raise TaskStateError("malformed legacy task line %d" % number)
        checked, task_id, title, owner, scope, needs, files, extra = match.groups()
        if task_id in tasks:
            raise TaskStateError("duplicate legacy task ID: %s" % task_id)
        status_match = re.search(r"(?:^|\|)\s*status:\s*([^|]+)", extra or "")
        status = status_match.group(1).strip() if status_match else ("done" if checked.lower() == "x" else "")
        tasks[task_id] = {"id": task_id, "title": title.strip(), "owner": owner.strip(),
                          "scope": scope.strip(), "needs": _needs(needs), "files": _files(files),
                          "checked": checked.lower() == "x", "status": status,
                          "canonical_status": None, "attempts": 0, "instance": ""}
    if not tasks:
        raise TaskStateError("legacy tasks file contains no tasks")
    known = set(tasks)
    for task in tasks.values():
        if any(dep not in known for dep in task["needs"]):
            raise TaskStateError("legacy task contains an unknown dependency")
    return {"feature": feature, "tasks": tasks, "source": "tasks.md", "canonical": False,
            "projection_matches": None, "projection_exists": True, "state": None}


def resolve(root: Path, feature: str, *, require_projection: bool = False) -> Dict[str, Any]:
    state_path, tasks_path = _paths(root, feature)
    if state_path.exists():
        result = _canonical(state_path, tasks_path, feature)
        if require_projection and not result["projection_matches"]:
            raise TaskStateError("canonical tasks.md projection is missing or stale; run harness repair")
        return result
    if tasks_path.exists():
        return _legacy(tasks_path, feature)
    raise TaskStateError("no canonical state.json or legacy tasks.md exists")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("feature")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--require-projection", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = resolve(args.root.resolve(), args.feature, require_projection=args.require_projection)
    except TaskStateError as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, sort_keys=True))
        return 1
    result["tasks"] = list(result["tasks"].values())
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
