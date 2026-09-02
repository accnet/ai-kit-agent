#!/usr/bin/env python3
"""Cross-component barrier checks for native-worker orchestration."""

import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".ai" / "scripts"))

from dag import analyze  # noqa: E402
from orchestrate import claim, finish, CoordinatorError  # noqa: E402


def line(task_id, checked=False, needs="-", files="-"):
    mark = "x" if checked else " "
    return "- [%s] %s Task | owner: backend | scope: M | needs: %s | files: %s" % (
        mark, task_id, needs, files
    )


def config(max_workers=4):
    return {
        "schema_version": 1,
        "orchestration": {
            "mode": "ide-native-workers",
            "enabled": True,
            "max_workers": max_workers,
            "require_dag": True,
            "require_disjoint_files": True,
            "coordinator_owns_task_state": True,
            "require_worktree_per_worker": True,
        },
    }


def main():
    failures = []
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / ".project" / "fixture").mkdir(parents=True)
        (root / ".ai").mkdir()
        (root / ".ai" / "config.json").write_text(json.dumps(config()), encoding="utf-8")
        tasks = root / ".project" / "fixture" / "tasks.md"
        tasks.write_text(
            "# Tasks\n"
            + "\n".join(
                [
                    line("T1", checked=True, files="contracts/v1.json"),
                    line("T4", needs="T1", files="inc/t4.php"),
                    line("T5", needs="T1", files="inc/t5.php"),
                    line("T14", needs="T1", files="assets/t14.js"),
                    line("T96", needs="T4,T5,T14", files="tests/qa.py"),
                    line("T97", needs="T96", files="-"),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        report = analyze(root, "fixture")
        if report["ready"] != ["T4", "T5", "T14"]:
            failures.append("barrier fixture did not expose T4/T5/T14 as ready")
        blocked = {entry["task"] for entry in report["blocked"]}
        if blocked != {"T96", "T97"}:
            failures.append("QA/G3 tasks were not blocked before implementation barrier")

        # A coordinator can claim all independent tasks, but QA remains blocked while any lease exists.
        for task_id in ("T4", "T5", "T14"):
            claim(root, "fixture", task_id, "lease-" + task_id, "worker-" + task_id)
        report = analyze(root, "fixture")
        if any(item["task"] == "T96" and "needs incomplete" in item["reasons"][0] for item in report["blocked"]):
            pass
        else:
            failures.append("QA barrier opened while implementation tasks were active")
        try:
            claim(root, "fixture", "T96", "lease-qa", "worker-qa")
        except CoordinatorError:
            pass
        else:
            failures.append("coordinator dispatched QA before implementation completion")

        for task_id in ("T4", "T5", "T14"):
            finish(root, "fixture", task_id, "lease-" + task_id, "complete", ["unit pass"])
        report = analyze(root, "fixture")
        if report["ready"] != ["T96"]:
            failures.append("QA did not become ready after the implementation barrier")
        try:
            claim(root, "fixture", "T96", "lease-qa", "worker-qa")
        except CoordinatorError as error:
            failures.append("QA claim failed after barrier: %s" % error)

        # A cycle is still rejected even when all other checks are satisfiable.
        tasks.write_text(
            "# Tasks\n" + line("T1", needs="T2", files="one.php") + "\n" + line("T2", needs="T1", files="two.php") + "\n",
            encoding="utf-8",
        )
        if analyze(root, "fixture")["valid"]:
            failures.append("cycle was accepted by the cross-component barrier")

    if failures:
        print("AI-Kit orchestration barrier FAILED: " + "; ".join(failures))
        return 1
    print("AI-Kit orchestration barrier OK: ready set, ownership, QA/G3 barrier, and cycle fail-closed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
