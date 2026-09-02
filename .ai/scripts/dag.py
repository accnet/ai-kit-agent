#!/usr/bin/env python3
"""Read-only dependency and file-scope analysis for AI-Kit task plans."""

from __future__ import annotations

import argparse
import fnmatch
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from task_state import TaskStateError, resolve as resolve_task_state  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
TASK_LINE = re.compile(
    r"^- \[([ xX])\]\s*(T\d+)\s+(.*?)\s*\|\s*owner:\s*([^|]+?)\s*"
    r"\|\s*scope:\s*([^|]+?)\s*\|\s*needs:\s*([^|]+?)\s*"
    r"\|\s*files:\s*([^|]+?)(?:\s*\|\s*(.*))?$"
)
TASK_ID = re.compile(r"^T\d+$")
FEATURE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
FEATURE_DEPENDENCY_LINE = re.compile(r"^Feature dependencies:\s*(.*?)\s*$", re.MULTILINE)
MAGIC = re.compile(r"[*?[]")


class DagError(ValueError):
    """Raised for an unreadable feature or malformed policy input."""


def _task_sort_key(task_id: str) -> Tuple[int, str]:
    """Sort T4 before T14 rather than using lexicographic Markdown order."""
    return (int(task_id[1:]), task_id)


def _task_path(root: Path, feature: str) -> Path:
    if not feature or feature in {".", ".."}:
        raise DagError("feature must be a project directory name")
    path = (root / ".project" / feature / "tasks.md").resolve()
    projects = (root / ".project").resolve()
    if projects not in path.parents or path == projects:
        raise DagError("feature path escapes .project")
    return path


def load_orchestration_policy(root: Path) -> dict:
    path = root / ".ai" / "config.json"
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DagError("cannot read AI-Kit config: %s" % path) from exc
    policy = config.get("orchestration")
    if not isinstance(policy, dict):
        raise DagError("AI-Kit config orchestration must be an object")
    value = policy.get("max_workers")
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 4:
        raise DagError("AI-Kit config orchestration.max_workers must be an integer from 1 to 4")
    return policy


def _load_max_workers(root: Path) -> int:
    return load_orchestration_policy(root)["max_workers"]


def _parse_needs(raw: str, task_id: str, errors: List[dict]) -> List[str]:
    value = raw.strip()
    if value in {"", "-"}:
        return []
    tokens = [token.strip() for token in value.split(",") if token.strip()]
    invalid = [token for token in tokens if not TASK_ID.fullmatch(token)]
    if invalid:
        errors.append(
            {
                "code": "malformed-dependency",
                "task": task_id,
                "message": "invalid dependency ID(s): %s" % ", ".join(invalid),
            }
        )
    return [token for token in tokens if TASK_ID.fullmatch(token)]


def _parse_files(raw: str) -> List[str]:
    value = raw.strip()
    if value in {"", "-"}:
        return []
    # Task scopes conventionally use comma-separated paths. Preserve spaces inside a path.
    return [item.strip() for item in value.split(",") if item.strip() and item.strip() != "-"]


def parse_tasks(path: Path) -> Tuple[Dict[str, dict], List[dict]]:
    tasks: Dict[str, dict] = {}
    errors: List[dict] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise DagError("cannot read tasks file: %s" % path) from exc
    for line_number, line in enumerate(lines, 1):
        if not line.startswith("- ["):
            continue
        match = TASK_LINE.match(line)
        if not match:
            errors.append(
                {
                    "code": "malformed-task",
                    "message": "line %d does not match the task contract" % line_number,
                }
            )
            continue
        checked, task_id, title, owner, scope, needs, files, extra = match.groups()
        if task_id in tasks:
            errors.append(
                {
                    "code": "duplicate-task-id",
                    "task": task_id,
                    "message": "task ID appears more than once",
                }
            )
            continue
        extra = extra or ""
        status_match = re.search(r"(?:^|\|)\s*status:\s*([^|]+)", extra)
        status = status_match.group(1).strip() if status_match else ""
        tasks[task_id] = {
            "id": task_id,
            "title": title.strip(),
            "owner": owner.strip(),
            "scope": scope.strip(),
            "needs": _parse_needs(needs, task_id, errors),
            "files": _parse_files(files),
            "checked": checked.lower() == "x",
            "status": status,
            "line": line_number,
        }
    if not tasks:
        errors.append({"code": "no-tasks", "message": "no task lines found"})
    for task in tasks.values():
        for dependency in task["needs"]:
            if dependency not in tasks:
                errors.append(
                    {
                        "code": "missing-dependency",
                        "task": task["id"],
                        "message": "dependency %s does not exist" % dependency,
                    }
                )
    return tasks, errors


def parse_feature_dependencies(path: Path) -> Tuple[List[dict], List[dict]]:
    """Parse optional cross-workstream task barriers from a tasks.md file."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DagError("cannot read tasks file: %s" % path) from exc
    declarations = FEATURE_DEPENDENCY_LINE.findall(text)
    if not declarations:
        return [], []
    errors: List[dict] = []
    if len(declarations) > 1:
        errors.append(
            {
                "code": "duplicate-feature-dependency-declaration",
                "message": "tasks.md may declare Feature dependencies only once",
            }
        )
    raw = declarations[0].strip()
    if raw in {"", "-"}:
        return [], errors
    dependencies: List[dict] = []
    seen = set()
    for token in (item.strip() for item in raw.split(",")):
        match = re.fullmatch(r"([^:\s]+)\s*:\s*(T\d+)", token)
        if not match or not FEATURE_ID.fullmatch(match.group(1)):
            errors.append(
                {
                    "code": "malformed-feature-dependency",
                    "message": "invalid feature dependency: %s" % token,
                }
            )
            continue
        feature, task_id = match.groups()
        key = (feature, task_id)
        if key in seen:
            errors.append(
                {
                    "code": "duplicate-feature-dependency",
                    "message": "feature dependency appears more than once: %s:%s" % key,
                }
            )
            continue
        seen.add(key)
        dependencies.append({"feature": feature, "task": task_id})
    return dependencies, errors


def resolve_feature_dependencies(root: Path, path: Path) -> Tuple[List[dict], List[dict], List[str]]:
    """Resolve cross-feature barriers and return records, hard errors, and incomplete reasons."""
    dependencies, errors = parse_feature_dependencies(path)
    resolved: List[dict] = []
    incomplete: List[str] = []
    for dependency in dependencies:
        target_path = _task_path(root, dependency["feature"])
        record = dict(dependency)
        record["satisfied"] = False
        if not target_path.exists():
            errors.append(
                {
                    "code": "missing-feature-dependency",
                    "feature": dependency["feature"],
                    "task": dependency["task"],
                    "message": "feature dependency target does not exist: %s:%s"
                    % (dependency["feature"], dependency["task"]),
                }
            )
            resolved.append(record)
            continue
        try:
            target_result = resolve_task_state(root, dependency["feature"])
            target_tasks = target_result["tasks"]
            target_errors = []
        except TaskStateError as exc:
            target_tasks, target_errors = parse_tasks(target_path)
            target_errors.append({"code": "state-resolution", "message": str(exc)})
        if target_errors:
            errors.append(
                {
                    "code": "invalid-feature-dependency-target",
                    "feature": dependency["feature"],
                    "task": dependency["task"],
                    "message": "feature dependency target is not a valid task plan: %s"
                    % dependency["feature"],
                }
            )
        target = target_tasks.get(dependency["task"])
        if target is None:
            errors.append(
                {
                    "code": "missing-feature-task",
                    "feature": dependency["feature"],
                    "task": dependency["task"],
                    "message": "feature dependency task does not exist: %s:%s"
                    % (dependency["feature"], dependency["task"]),
                }
            )
        elif target["checked"]:
            record["satisfied"] = True
        else:
            incomplete.append("%s:%s" % (dependency["feature"], dependency["task"]))
        resolved.append(record)
    return resolved, errors, incomplete


def _cycle_errors(tasks: Dict[str, dict]) -> Tuple[List[dict], set]:
    state: Dict[str, int] = {}
    stack: List[str] = []
    cycles: List[dict] = []
    cyclic: set = set()

    def visit(task_id: str) -> None:
        state[task_id] = 1
        stack.append(task_id)
        for dependency in tasks[task_id]["needs"]:
            if dependency not in tasks:
                continue
            if state.get(dependency, 0) == 0:
                visit(dependency)
            elif state.get(dependency) == 1:
                start = stack.index(dependency)
                members = stack[start:] + [dependency]
                cyclic.update(members)
                cycles.append(
                    {
                        "code": "dependency-cycle",
                        "task": task_id,
                        "message": "cycle detected: %s" % " -> ".join(members),
                    }
                )
        stack.pop()
        state[task_id] = 2

    for task_id in sorted(tasks, key=_task_sort_key):
        if state.get(task_id, 0) == 0:
            visit(task_id)
    return cycles, cyclic


def _normalize_scope(value: str) -> str:
    normalized = value.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return str(PurePosixPath(normalized))


def _literal_prefix(pattern: str) -> str:
    prefix = MAGIC.split(pattern, maxsplit=1)[0]
    return prefix.rstrip("/")


def scopes_overlap(left: str, right: str) -> bool:
    """Conservative overlap check for repository-relative path/glob scopes."""
    left = _normalize_scope(left)
    right = _normalize_scope(right)
    if left == right:
        return True
    left_glob = bool(MAGIC.search(left))
    right_glob = bool(MAGIC.search(right))
    if not left_glob and not right_glob:
        return left.startswith(right + "/") or right.startswith(left + "/")
    left_prefix = _literal_prefix(left)
    right_prefix = _literal_prefix(right)
    if not left_prefix or not right_prefix:
        return True
    if left_prefix == right_prefix:
        return True
    if left_prefix.startswith(right_prefix + "/") or right_prefix.startswith(left_prefix + "/"):
        return True
    # fnmatch can prove a concrete path is covered by a glob; otherwise different roots are disjoint.
    if not left_glob and fnmatch.fnmatchcase(left, right):
        return True
    if not right_glob and fnmatch.fnmatchcase(right, left):
        return True
    return False


def _scope_conflicts(tasks: Dict[str, dict], candidate_ids: Sequence[str]) -> List[dict]:
    conflicts: List[dict] = []
    for index, left_id in enumerate(candidate_ids):
        for right_id in candidate_ids[index + 1 :]:
            left_files = tasks[left_id]["files"]
            right_files = tasks[right_id]["files"]
            overlap = [
                (left, right)
                for left in left_files
                for right in right_files
                if scopes_overlap(left, right)
            ]
            if overlap:
                paths = sorted({item for pair in overlap for item in pair})
                conflicts.append(
                    {
                        "tasks": sorted([left_id, right_id]),
                        "paths": paths,
                        "reason": "declared file scopes may overlap",
                    }
                )
    return conflicts


def analyze(root: Path, feature: str) -> dict:
    tasks_path = _task_path(root, feature)
    max_workers = _load_max_workers(root)
    try:
        resolved = resolve_task_state(root, feature)
        tasks = resolved["tasks"]
        errors: List[dict] = []
    except TaskStateError as exc:
        tasks, errors = parse_tasks(tasks_path)
        errors.append({"code": "state-resolution", "message": str(exc)})
        resolved = {"state": None}
    capability_decision = None
    if isinstance(resolved.get("state"), dict):
        capability_decision = resolved["state"].get("capability_decision")
    if capability_decision is None:
        decision_path = tasks_path.parent / "capabilities.json"
        if decision_path.is_file():
            try:
                capability_decision = json.loads(decision_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                errors.append({"code": "capability-decision", "message": "invalid capabilities.json"})
    feature_dependencies, dependency_errors, incomplete_feature_dependencies = resolve_feature_dependencies(
        root, tasks_path
    )
    errors.extend(dependency_errors)
    cycle_errors, cyclic = _cycle_errors(tasks)
    errors.extend(cycle_errors)
    done = sorted(
        (task_id for task_id, task in tasks.items() if task["checked"]),
        key=_task_sort_key,
    )
    active = sorted(
        [
            task_id
            for task_id, task in tasks.items()
            if not task["checked"]
            and task["status"] in {"in-progress", "claimed", "active"}
        ],
        key=_task_sort_key,
    )
    pending = sorted(
        [
            task_id
            for task_id, task in tasks.items()
            if not task["checked"] and task_id not in active
        ],
        key=_task_sort_key,
    )
    blocked: List[dict] = []
    ready: List[str] = []
    for task_id in pending:
        task = tasks[task_id]
        reasons = []
        unresolved = [dependency for dependency in task["needs"] if dependency not in done]
        if unresolved:
            reasons.append("needs incomplete: %s" % ", ".join(sorted(unresolved)))
        if incomplete_feature_dependencies:
            reasons.append(
                "feature dependency incomplete: %s"
                % ", ".join(sorted(incomplete_feature_dependencies))
            )
        if task_id in cyclic:
            reasons.append("dependency cycle")
        if reasons:
            blocked.append({"task": task_id, "reasons": reasons})
        else:
            ready.append(task_id)
    candidates = sorted(set(ready + active), key=_task_sort_key)
    conflicts = _scope_conflicts(tasks, candidates)
    conflict_tasks = {task_id for conflict in conflicts for task_id in conflict["tasks"]}
    dispatchable = [] if errors or conflicts else [
        task_id for task_id in ready if task_id not in conflict_tasks
    ][:max_workers]
    valid = not errors and not conflicts
    return {
        "kind": "dag-report",
        "contractVersion": 1,
        "feature": feature,
        "feature_dependencies": feature_dependencies,
        "featureDependencies": feature_dependencies,
        "capabilityDecision": capability_decision,
        "valid": valid,
        "ready": ready,
        "blocked": blocked,
        "active": active,
        "done": done,
        "conflicts": conflicts,
        "errors": errors,
        "max_workers": max_workers,
        "dispatchable": dispatchable,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("feature", help="feature directory under .project")
    parser.add_argument("--json", action="store_true", dest="as_json", help="emit the v1 JSON report")
    args = parser.parse_args(argv)
    try:
        report = analyze(ROOT, args.feature)
    except DagError as error:
        if args.as_json:
            print(json.dumps({"kind": "dag-report", "contractVersion": 1, "valid": False, "errors": [{"code": "input", "message": str(error)}]}, sort_keys=True))
        else:
            print("ERROR: %s" % error, file=sys.stderr)
        return 2
    if args.as_json:
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    else:
        print("ready: %s" % (", ".join(report["ready"]) or "-"))
        print("dispatchable: %s" % (", ".join(report["dispatchable"]) or "-"))
        if report["errors"] or report["conflicts"]:
            print("invalid: errors=%d conflicts=%d" % (len(report["errors"]), len(report["conflicts"])), file=sys.stderr)
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
