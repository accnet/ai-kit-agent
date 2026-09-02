#!/usr/bin/env python3
"""Validate a Codex IDE worker handoff without creating workers or worktrees."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Optional, Sequence

from dag import DagError, _normalize_scope, analyze, parse_tasks


ROOT = Path(__file__).resolve().parents[2]
TASK_ID = re.compile(r"^T[0-9]{1,15}$")
LEASE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class ManifestError(ValueError):
    """Raised when a worker handoff violates orchestration v1."""


def _state_path(root: Path, feature: str) -> Path:
    return root / ".workspace" / "orchestration" / (feature.replace("/", "_") + ".json")


def _load_state(root: Path, feature: str) -> dict:
    path = _state_path(root, feature)
    if not path.exists():
        return {"active": {}}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError("invalid coordinator state: %s" % path) from exc
    if not isinstance(state.get("active"), dict):
        raise ManifestError("coordinator state active field must be an object")
    return state


def _worktree_is_clean(path: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "status", "--porcelain", "--untracked-files=all"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return False
    return result.returncode == 0 and not result.stdout.strip()


def validate(root: Path, feature: str, manifest: dict) -> dict:
    if not isinstance(manifest, dict):
        raise ManifestError("worker manifest must be an object")
    required = {"kind", "contractVersion", "coordinator_lease", "task", "files", "worktree", "worker"}
    if set(manifest) != required:
        raise ManifestError("worker manifest must contain exactly the v1 fields")
    if manifest["kind"] != "worker-manifest" or manifest["contractVersion"] != 1:
        raise ManifestError("worker manifest kind/version is not orchestration v1")
    lease = manifest["coordinator_lease"]
    task_id = manifest["task"]
    files = manifest["files"]
    worker = manifest["worker"]
    worktree = manifest["worktree"]
    if not isinstance(lease, str) or not LEASE.fullmatch(lease):
        raise ManifestError("coordinator_lease must be non-empty")
    if not isinstance(task_id, str) or not TASK_ID.fullmatch(task_id):
        raise ManifestError("task must be a task ID")
    if not isinstance(files, list) or not files or len(files) != len(set(files)) or not all(isinstance(item, str) and 0 < len(item) <= 512 and "\n" not in item and "\r" not in item and item.strip() for item in files):
        raise ManifestError("files must be a unique non-empty string list")
    if not isinstance(worker, dict) or set(worker) != {"id", "scheduler"} or not isinstance(worker.get("id"), str) or not 0 < len(worker["id"]) <= 512 or "\n" in worker["id"] or "\r" in worker["id"] or worker.get("scheduler") != "codex-ide":
        raise ManifestError("worker must identify the codex-ide scheduler")
    if not isinstance(worktree, dict) or set(worktree) != {"path", "isolated", "clean"} or not isinstance(worktree.get("path"), str) or not 0 < len(worktree["path"]) <= 512 or "\n" in worktree["path"] or "\r" in worktree["path"]:
        raise ManifestError("worktree must contain path, isolated, and clean")
    if worktree.get("isolated") is not True or worktree.get("clean") is not True:
        raise ManifestError("worktree must be marked isolated and clean")

    report = analyze(root, feature)
    tasks_path = root / ".project" / feature / "tasks.md"
    tasks, parse_errors = parse_tasks(tasks_path)
    if parse_errors or not report["valid"]:
        raise ManifestError("DAG is invalid; worker handoff is refused")
    task = tasks.get(task_id)
    if task is None:
        raise ManifestError("manifest task does not exist")
    state = _load_state(root, feature)
    active = state["active"].get(task_id)
    if active is None:
        if task_id not in report["ready"]:
            raise ManifestError("manifest task is neither ready nor owned by a lease")
    elif active.get("lease") != lease:
        raise ManifestError("manifest lease does not own the task")
    elif active.get("instance") != worker["id"]:
        raise ManifestError("manifest worker does not match the coordinator lease instance")
    expected_files = {_normalize_scope(item) for item in task["files"]}
    actual_files = {_normalize_scope(item) for item in files}
    if expected_files != actual_files:
        raise ManifestError("manifest files do not exactly match the task scope")

    worktree_path = Path(worktree["path"]).expanduser().resolve()
    coordinator_root = root.resolve()
    if worktree_path == coordinator_root:
        raise ManifestError("worker worktree must differ from the coordinator checkout")
    if not worktree_path.is_dir():
        raise ManifestError("worker worktree does not exist: %s" % worktree_path)
    if not _worktree_is_clean(worktree_path):
        raise ManifestError("worker worktree is missing Git metadata or is dirty")
    for other_task, other in state["active"].items():
        if other_task == task_id:
            continue
        other_path = other.get("worktree") or other.get("worktree_path")
        if other_path and Path(other_path).expanduser().resolve() == worktree_path:
            raise ManifestError("worker worktree is already assigned to another active task")
    return {
        "valid": True,
        "feature": feature,
        "task": task_id,
        "lease": lease,
        "worktree": str(worktree_path),
        "files": sorted(actual_files),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("feature")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        result = validate(args.root.resolve(), args.feature, manifest)
    except (ManifestError, DagError, OSError, json.JSONDecodeError) as error:
        print(json.dumps({"valid": False, "error": str(error)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
