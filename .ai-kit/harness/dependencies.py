"""Read-only, fail-closed resolution of cross-feature task barriers."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Iterable, List, Mapping, Optional, Sequence, Set, Tuple


FEATURE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
TASK_ID = re.compile(r"^T[1-9][0-9]*$")
LEGACY_DEPENDENCIES = re.compile(r"^Feature dependencies:\s*(.+?)\s*$", re.MULTILINE)
LEGACY_TASK = re.compile(r"^- \[([ xX])\]\s*(T[1-9][0-9]*)\b", re.MULTILINE)


@dataclass(frozen=True)
class DependencyResult:
    """The deterministic outcome for one cross-feature task target."""

    feature: str
    task: str
    satisfied: bool
    source: Optional[str]
    diagnostic: Optional[str] = None


class CrossFeatureDependencyResolver:
    """Resolve canonical or legacy feature targets without writing repository state."""

    def __init__(self, root: Path, current_feature: str) -> None:
        self.root = Path(root).resolve()
        self.current_feature = current_feature

    def resolve(self, dependencies: Iterable[Mapping[str, object]]) -> Tuple[DependencyResult, ...]:
        values = list(dependencies)
        results: List[DependencyResult] = []
        seen: Set[Tuple[str, str]] = set()
        for raw in values:
            feature, task, diagnostic = self._target(raw)
            if diagnostic:
                results.append(DependencyResult(feature, task, False, None, diagnostic))
                continue
            target = (feature, task)
            if target in seen:
                results.append(DependencyResult(feature, task, False, None, "duplicate feature dependency: %s:%s" % target))
                continue
            seen.add(target)
            results.append(self._resolve_target(feature, task, (self.current_feature,)))
        return tuple(results)

    def _target(self, raw: Mapping[str, object]) -> Tuple[str, str, Optional[str]]:
        if not isinstance(raw, Mapping):
            return "", "", "feature dependency must be an object"
        feature = raw.get("feature")
        task = raw.get("task")
        if set(raw) != {"feature", "task"}:
            return str(feature or ""), str(task or ""), "feature dependency must contain only feature and task"
        if not isinstance(feature, str) or not FEATURE_ID.fullmatch(feature):
            return str(feature or ""), str(task or ""), "invalid feature dependency feature"
        if not isinstance(task, str) or not TASK_ID.fullmatch(task):
            return feature, str(task or ""), "invalid feature dependency task"
        if feature == self.current_feature:
            return feature, task, "self-referencing feature dependency: %s:%s" % (feature, task)
        return feature, task, None

    def _resolve_target(self, feature: str, task: str, stack: Sequence[str]) -> DependencyResult:
        if feature in stack:
            return DependencyResult(feature, task, False, None, "cyclic feature dependency: %s" % " -> ".join((*stack, feature)))
        directory = self.root / ".project" / feature
        state_path = directory / "state.json"
        tasks_path = directory / "tasks.md"
        if state_path.exists():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                return DependencyResult(feature, task, False, "state.json", "malformed canonical state for %s: %s" % (feature, exc))
            return self._canonical(feature, task, state, (*stack, feature))
        if not tasks_path.is_file():
            return DependencyResult(feature, task, False, None, "missing feature dependency target: %s:%s" % (feature, task))
        try:
            text = tasks_path.read_text(encoding="utf-8")
        except OSError as exc:
            return DependencyResult(feature, task, False, "tasks.md", "cannot read legacy task target %s: %s" % (feature, exc))
        return self._legacy(feature, task, text, (*stack, feature))

    def _canonical(self, feature: str, task: str, state: object, stack: Sequence[str]) -> DependencyResult:
        if not isinstance(state, dict) or not isinstance(state.get("tasks"), list):
            return DependencyResult(feature, task, False, "state.json", "malformed canonical state for %s" % feature)
        if state.get("feature") != feature:
            return DependencyResult(feature, task, False, "state.json", "canonical state feature mismatch for %s" % feature)
        nested = state.get("feature_dependencies", [])
        if not isinstance(nested, list):
            return DependencyResult(feature, task, False, "state.json", "malformed canonical feature dependencies for %s" % feature)
        for result in self._resolve_nested(nested, stack):
            if not result.satisfied:
                return DependencyResult(feature, task, False, "state.json", result.diagnostic)
        matches = [item for item in state["tasks"] if isinstance(item, dict) and item.get("id") == task]
        if len(matches) != 1:
            return DependencyResult(feature, task, False, "state.json", "missing canonical task target: %s:%s" % (feature, task))
        if matches[0].get("state") != "complete":
            return DependencyResult(feature, task, False, "state.json", "unfinished canonical task target: %s:%s" % (feature, task))
        return DependencyResult(feature, task, True, "state.json")

    def _legacy(self, feature: str, task: str, text: str, stack: Sequence[str]) -> DependencyResult:
        declared = LEGACY_DEPENDENCIES.findall(text)
        if len(declared) > 1:
            return DependencyResult(feature, task, False, "tasks.md", "malformed legacy feature dependencies for %s" % feature)
        if declared:
            nested = []
            for value in declared[0].split(","):
                item = value.strip()
                parts = item.split(":", 1)
                if len(parts) != 2:
                    return DependencyResult(feature, task, False, "tasks.md", "malformed legacy feature dependency for %s" % feature)
                nested.append({"feature": parts[0].strip(), "task": parts[1].strip()})
            for result in self._resolve_nested(nested, stack):
                if not result.satisfied:
                    return DependencyResult(feature, task, False, "tasks.md", result.diagnostic)
        rows = [(checked.lower() == "x", task_id) for checked, task_id in LEGACY_TASK.findall(text)]
        matches = [checked for checked, task_id in rows if task_id == task]
        if len(matches) != 1:
            return DependencyResult(feature, task, False, "tasks.md", "missing legacy task target: %s:%s" % (feature, task))
        if not matches[0]:
            return DependencyResult(feature, task, False, "tasks.md", "unfinished legacy task target: %s:%s" % (feature, task))
        return DependencyResult(feature, task, True, "tasks.md")

    def _resolve_nested(self, dependencies: Iterable[Mapping[str, object]], stack: Sequence[str]) -> Tuple[DependencyResult, ...]:
        nested = CrossFeatureDependencyResolver(self.root, stack[-1])
        results = []
        for raw in dependencies:
            feature, task, diagnostic = nested._target(raw)
            if diagnostic:
                results.append(DependencyResult(feature, task, False, None, diagnostic))
            else:
                results.append(nested._resolve_target(feature, task, stack))
        return tuple(results)
