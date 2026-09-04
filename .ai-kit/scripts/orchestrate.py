#!/usr/bin/env python3
"""Coordinator-only task transitions for the IDE-native orchestration contract."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Optional, Sequence

if os.name == "nt":
    import msvcrt
else:
    import fcntl

from dag import DagError, _normalize_scope, analyze, load_orchestration_policy, parse_tasks
from task_state import TaskStateError, resolve as resolve_task_state


ROOT = Path(__file__).resolve().parents[2]
TASK_ID = re.compile(r"^T\d+$")
TASK_LINE = re.compile(r"^- \[([ xX])\]\s*(T\d+)\b")


class CoordinatorError(ValueError):
    """Raised when the coordinator cannot safely transition a task."""


def _acquire_lock(handle) -> None:
    if os.name == "nt":
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
    else:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)


def _release_lock(handle) -> None:
    if os.name == "nt":
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def paths(root: Path, feature: str):
    project = (root / ".project" / feature).resolve()
    projects = (root / ".project").resolve()
    if projects not in project.parents:
        raise CoordinatorError("feature path escapes .project")
    tasks = project / "tasks.md"
    workspace = root / ".workspace" / "orchestration"
    return tasks, workspace / (feature.replace("/", "_") + ".json"), workspace / (feature.replace("/", "_") + ".lock")


def read_state(path: Path, feature: str) -> dict:
    if not path.exists():
        return {"contractVersion": 1, "feature": feature, "active": {}, "history": []}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CoordinatorError("invalid coordinator state: %s" % path) from exc
    if state.get("contractVersion") != 1 or state.get("feature") != feature:
        raise CoordinatorError("coordinator state does not match contract or feature")
    if not isinstance(state.get("active"), dict) or not isinstance(state.get("history"), list):
        raise CoordinatorError("coordinator state has invalid active/history fields")
    return state


def write_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def task_lines(path: Path):
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise CoordinatorError("cannot read tasks file: %s" % path) from exc


def rewrite_task(path: Path, task_id: str, transition: str, metadata: Optional[dict] = None) -> None:
    lines = task_lines(path)
    matches = [index for index, line in enumerate(lines) if (m := TASK_LINE.match(line)) and m.group(2) == task_id]
    if len(matches) != 1:
        raise CoordinatorError("%s must identify exactly one task" % task_id)
    index = matches[0]
    line = lines[index]
    # Preserve owner/scope/needs/files fields; remove only coordinator metadata from a prior claim.
    base = re.sub(r"\s*\|\s*(?:status|instance|lease):\s*[^|]*", "", line).rstrip()
    if transition == "claim":
        base = re.sub(r"^- \[[ xX]\]", "- [ ]", base, count=1)
        base += " | status: in-progress | instance: %s | lease: %s" % (
            metadata["instance"],
            metadata["lease"],
        )
    elif transition == "complete":
        base = re.sub(r"^- \[[ xX]\]", "- [x]", base, count=1)
    elif transition in {"retry", "reject"}:
        base = re.sub(r"^- \[[ xX]\]", "- [ ]", base, count=1)
        if transition == "reject":
            base += " | status: rejected"
    else:
        raise CoordinatorError("unsupported transition: %s" % transition)
    lines[index] = base
    content = "\n".join(lines) + "\n"
    temporary = path.with_name(path.name + ".tmp-%s" % os.getpid())
    try:
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def log_transition(root: Path, feature: str, task: str, actor: str, status: str, detail: str) -> None:
    script = root / ".ai-kit" / "scripts" / "log-event.sh"
    if script.exists():
        subprocess.run(
            ["bash", ".ai-kit/scripts/log-event.sh", status, feature, task, actor, detail],
            cwd=str(root),
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def locked_state(root: Path, feature: str):
    tasks, state_path, lock_path = paths(root, feature)
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = lock_path.open("a+b")
    except OSError as exc:
        raise CoordinatorError("cannot open coordinator lock") from exc
    try:
        _acquire_lock(handle)
    except OSError as exc:
        handle.close()
        raise CoordinatorError("cannot acquire coordinator lock") from exc
    return tasks, state_path, handle


def claim(root: Path, feature: str, task_id: str, lease: str, instance: str) -> dict:
    if not TASK_ID.fullmatch(task_id) or not lease.strip() or not instance.strip():
        raise CoordinatorError("task, lease, and instance must be non-empty contract values")
    tasks, state_path, lock = locked_state(root, feature)
    try:
        policy = load_orchestration_policy(root)
        if policy.get("enabled") is not True:
            raise CoordinatorError("orchestration.enabled is false; coordinator dispatch is disabled")
        report = analyze(root, feature)
        state = read_state(state_path, feature)
        if not report["valid"]:
            raise CoordinatorError("DAG is invalid; coordinator refuses dispatch")
        if task_id not in report["dispatchable"]:
            raise CoordinatorError("%s is not conflict-free and ready" % task_id)
        if len(state["active"]) >= report["max_workers"]:
            raise CoordinatorError("max_workers=%d already active" % report["max_workers"])
        if task_id in state["active"]:
            raise CoordinatorError("%s is already leased" % task_id)
        metadata = {
            "lease": lease,
            "instance": instance,
            "files": _task_files(root, feature, task_id),
        }
        rewrite_task(tasks, task_id, "claim", metadata)
        state["active"][task_id] = metadata
        state["history"].append({"task": task_id, "status": "claimed", "lease": lease, "instance": instance})
        write_state(state_path, state)
        log_transition(root, feature, task_id, instance, "claimed", "coordinator claim")
        return {"status": "claimed", "task": task_id, "lease": lease, "active": sorted(state["active"])}
    finally:
        _release_lock(lock)
        lock.close()


def _task_files(root: Path, feature: str, task_id: str):
    """Return the normalized declared scope for the task being leased."""
    tasks_path = root / ".project" / feature / "tasks.md"
    try:
        tasks = resolve_task_state(root, feature)["tasks"]
        errors = []
    except TaskStateError as exc:
        tasks, errors = parse_tasks(tasks_path)
        errors.append({"code": "state-resolution", "message": str(exc)})
    if errors or task_id not in tasks:
        raise CoordinatorError("cannot resolve declared file scope for %s" % task_id)
    return sorted({_normalize_scope(item) for item in tasks[task_id]["files"]})


def finish(root: Path, feature: str, task_id: str, lease: str, status: str, evidence: Sequence[str]) -> dict:
    if not evidence:
        raise CoordinatorError("%s requires at least one evidence item" % status)
    canonical_status = "completed" if status == "complete" else ("rejected" if status == "reject" else status)
    tasks, state_path, lock = locked_state(root, feature)
    try:
        state = read_state(state_path, feature)
        active = state["active"].get(task_id)
        if not active or active.get("lease") != lease:
            raise CoordinatorError("coordinator lease does not own %s" % task_id)
        rewrite_task(tasks, task_id, status)
        del state["active"][task_id]
        state["history"].append({"task": task_id, "status": canonical_status, "lease": lease, "evidence": list(evidence)})
        write_state(state_path, state)
        log_transition(root, feature, task_id, "coordinator", canonical_status, " ".join(" ".join(evidence).splitlines()))
        return {"status": canonical_status, "task": task_id, "active": sorted(state["active"])}
    finally:
        _release_lock(lock)
        lock.close()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("feature")
    parser.add_argument("action", choices=("status", "claim", "complete", "retry", "reject"))
    parser.add_argument("task", nargs="?")
    parser.add_argument("--lease", default="")
    parser.add_argument("--instance", default="")
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.action == "status":
            result = analyze(args.root.resolve(), args.feature)
        elif args.action == "claim":
            result = claim(args.root.resolve(), args.feature, args.task or "", args.lease, args.instance)
        else:
            if not args.task or not args.lease:
                raise CoordinatorError("%s requires task and --lease" % args.action)
            result = finish(args.root.resolve(), args.feature, args.task, args.lease, args.action, args.evidence)
    except (CoordinatorError, DagError) as error:
        if args.json:
            print(json.dumps({"valid": False, "error": str(error)}, sort_keys=True))
        else:
            print("ERROR: %s" % error, file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")) if args.json else result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
