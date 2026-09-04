#!/usr/bin/env python3
"""Deterministic DAG and file-scope mechanics for the native-worker contract."""

import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".ai-kit" / "scripts"))

from dag import analyze, scopes_overlap  # noqa: E402


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


def task(task_id, *, checked=False, needs="-", files="-"):
    mark = "x" if checked else " "
    return "- [%s] %s Task %s | owner: backend | scope: S | needs: %s | files: %s" % (
        mark,
        task_id,
        task_id,
        needs,
        files,
    )


def fixture_root(lines):
    temporary = tempfile.TemporaryDirectory()
    root = Path(temporary.name)
    (root / ".project" / "fixture").mkdir(parents=True)
    (root / ".ai-kit").mkdir()
    (root / ".ai-kit" / "config.json").write_text(json.dumps(CONFIG), encoding="utf-8")
    (root / ".project" / "fixture" / "tasks.md").write_text(
        "# Tasks\n\n" + "\n".join(lines) + "\n", encoding="utf-8"
    )
    return temporary, root


def main():
    failures = []

    temporary, root = fixture_root(
        [
            task("T1", checked=True, files="contracts/one.json"),
            task("T4", needs="T1", files="inc/t4.php"),
            task("T5", needs="T1", files="inc/t5.php"),
            task("T14", needs="T1", files="assets/t14.js"),
            task("T7", needs="T4,T5", files="assets/t7.js"),
        ]
    )
    try:
        report = analyze(root, "fixture")
        if report["ready"] != ["T4", "T5", "T14"]:
            failures.append("independent T4/T5/T14 tasks were not ready")
        if report["dispatchable"] != ["T4", "T5", "T14"]:
            failures.append("dispatchable list did not preserve all three ready tasks")
        if report["blocked"] != [{"task": "T7", "reasons": ["needs incomplete: T4, T5"]}]:
            failures.append("dependent task was not blocked with deterministic reason")
    finally:
        temporary.cleanup()

    temporary, root = fixture_root(
        [
            task("T1", needs="T9", files="one.php"),
            task("T9", needs="T1", files="nine.php"),
            task("T3", needs="T404", files="three.php"),
        ]
    )
    try:
        report = analyze(root, "fixture")
        codes = {error["code"] for error in report["errors"]}
        if report["valid"] or not {"dependency-cycle", "missing-dependency"}.issubset(codes):
            failures.append("cycle or missing dependency was accepted")
    finally:
        temporary.cleanup()

    temporary, root = fixture_root(
        [
            task("T1", checked=True, files="shared/file.php"),
            task("T2", needs="T1", files="shared/file.php"),
            task("T3", needs="T1", files="shared/"),
            task("T4", needs="T1", files="assets/*.js"),
            task("T5", needs="T1", files="assets/app.js"),
        ]
    )
    try:
        report = analyze(root, "fixture")
        pairs = {tuple(conflict["tasks"]) for conflict in report["conflicts"]}
        if ("T2", "T3") not in pairs or ("T4", "T5") not in pairs:
            failures.append("exact/parent or glob overlap was not reported")
        if report["valid"]:
            failures.append("overlapping scopes were accepted as a valid graph")
    finally:
        temporary.cleanup()

    temporary, root = fixture_root(
        [task("T%d" % number, files="root/%d.php" % number) for number in range(1, 7)]
    )
    try:
        report = analyze(root, "fixture")
        if len(report["ready"]) != 6 or len(report["dispatchable"]) != 4:
            failures.append("max_workers did not cap dispatchable tasks at four")
    finally:
        temporary.cleanup()

    if not scopes_overlap("src/*.php", "src/plugin.php"):
        failures.append("glob should conservatively overlap a matching concrete path")
    if scopes_overlap("src/", "assets/app.js"):
        failures.append("disjoint top-level scopes were incorrectly marked overlapping")

    if failures:
        print("AI-Kit DAG mechanics FAILED: " + "; ".join(failures))
        return 1
    print("AI-Kit DAG mechanics OK: readiness, dependency errors, cycles, overlap, and worker cap")
    return 0


if __name__ == "__main__":
    sys.exit(main())
