#!/usr/bin/env python3
"""Cross-feature barrier mechanics for the native-worker DAG."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".ai-kit/scripts"))

from dag import analyze  # noqa: E402


CONFIG = {
    "schema_version": 1,
    "orchestration": {
        "mode": "ide-native-workers",
        "enabled": True,
        "max_workers": 4,
        "require_dag": True,
        "require_disjoint_files": True,
        "coordinator_owns_task_state": True,
        "require_worktree_per_worker": True,
    },
}


def task(task_id, checked=False):
    return "- [%s] %s Task | owner: backend | scope: S | needs: - | files: %s.php" % (
        "x" if checked else " ", task_id, task_id.lower()
    )


def fixture(target_checked=True, dependency_line="Feature dependencies: baseline:T1"):
    temporary = tempfile.TemporaryDirectory()
    root = Path(temporary.name)
    (root / ".ai-kit").mkdir()
    (root / ".ai-kit/config.json").write_text(json.dumps(CONFIG), encoding="utf-8")
    (root / ".project" / "baseline").mkdir(parents=True)
    (root / ".project" / "fixture").mkdir()
    (root / ".project" / "baseline" / "tasks.md").write_text(
        "# Baseline\n\n" + task("T1", target_checked) + "\n", encoding="utf-8"
    )
    (root / ".project" / "fixture" / "tasks.md").write_text(
        "# Feature\n\n" + dependency_line + "\n\n" + task("T2") + "\n", encoding="utf-8"
    )
    (root / ".ai-kit" / "scripts").mkdir()
    shutil.copy(ROOT / ".ai-kit/scripts/dag.py", root / ".ai-kit/scripts/dag.py")
    shutil.copy(ROOT / ".ai-kit/scripts/task_state.py", root / ".ai-kit/scripts/task_state.py")
    shutil.copy(ROOT / ".ai-kit/scripts/next-task.sh", root / ".ai-kit/scripts/next-task.sh")
    return temporary, root


def main():
    failures = []
    temporary, root = fixture()
    try:
        report = analyze(root, "fixture")
        if report["ready"] != ["T2"] or report["dispatchable"] != ["T2"]:
            failures.append("checked cross-feature target did not permit dispatch")
        if report["featureDependencies"] != [{"feature": "baseline", "task": "T1", "satisfied": True}]:
            failures.append("satisfied dependency was not reported deterministically")
        result = subprocess.run(
            ["bash", str(root / ".ai-kit/scripts/next-task.sh"), "fixture"],
            cwd=str(root), capture_output=True, text=True,
        )
        if result.returncode != 0 or "T2" not in result.stdout:
            failures.append("next-task did not expose a DAG-dispatchable task")
    finally:
        temporary.cleanup()

    temporary, root = fixture(target_checked=False)
    try:
        report = analyze(root, "fixture")
        if report["ready"] or report["dispatchable"]:
            failures.append("incomplete cross-feature target was dispatched")
        if report["blocked"] != [{"task": "T2", "reasons": ["feature dependency incomplete: baseline:T1"]}]:
            failures.append("incomplete barrier diagnostic was not deterministic")
        if not report["valid"]:
            failures.append("an incomplete (but well-formed) barrier should remain a valid blocked graph")
        result = subprocess.run(
            ["bash", str(root / ".ai-kit/scripts/next-task.sh"), "fixture"],
            cwd=str(root), capture_output=True, text=True,
        )
        if result.returncode == 0 or "No claimable tasks" not in result.stderr:
            failures.append("next-task bypassed an incomplete cross-feature barrier")
    finally:
        temporary.cleanup()

    temporary, root = fixture(dependency_line="Feature dependencies: missing:T1")
    try:
        report = analyze(root, "fixture")
        codes = {error["code"] for error in report["errors"]}
        if report["valid"] or report["dispatchable"] or "missing-feature-dependency" not in codes:
            failures.append("missing feature target did not fail closed")
    finally:
        temporary.cleanup()

    temporary, root = fixture(dependency_line="Feature dependencies: baseline:T1, baseline:T1, bad token")
    try:
        report = analyze(root, "fixture")
        codes = {error["code"] for error in report["errors"]}
        if not {"duplicate-feature-dependency", "malformed-feature-dependency"}.issubset(codes):
            failures.append("duplicate or malformed feature metadata was accepted")
    finally:
        temporary.cleanup()

    if failures:
        print("AI-Kit cross-feature mechanics FAILED: " + "; ".join(failures))
        return 1
    print("AI-Kit cross-feature mechanics OK: barriers, diagnostics, and fail-closed dispatch")
    return 0


if __name__ == "__main__":
    sys.exit(main())
