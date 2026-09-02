#!/usr/bin/env python3
"""Integration smoke checks for the native orchestration command boundary."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]


POLICY = {
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
    "execution": {"task_cli": {"enabled": False}},
}


def command(root, script, *args):
    return subprocess.run(
        [sys.executable, str(root / ".ai" / "scripts" / script), *args],
        cwd=str(root),
        text=True,
        capture_output=True,
    )


def write_fixture(root, feature, tasks):
    (root / ".project" / feature).mkdir(parents=True)
    (root / ".project" / feature / "tasks.md").write_text(tasks, encoding="utf-8")


def fixture_root():
    temporary = tempfile.TemporaryDirectory()
    root = Path(temporary.name)
    scripts = root / ".ai" / "scripts"
    scripts.mkdir(parents=True)
    for name in ("dag.py", "orchestrate.py", "task_state.py"):
        shutil.copy(ROOT / ".ai" / "scripts" / name, scripts / name)
    (root / ".ai" / "config.json").write_text(json.dumps(POLICY), encoding="utf-8")
    write_fixture(
        root,
        "fixture",
        "# Tasks\n\n"
        "- [x] T1 Completed task | owner: backend | scope: S | needs: - | files: one.php\n"
        "- [x] T2 Completed task | owner: qa | scope: S | needs: T1 | files: two.php\n"
        "- [ ] T3 Ready barrier | owner: reviewer | scope: S | needs: T1,T2 | files: three.php\n",
    )
    write_fixture(
        root,
        "invalid",
        "# Tasks\n\n"
        "- [ ] T1 Broken task | owner: backend | scope: S | needs: T99 | files: broken.php\n",
    )
    return temporary, root


def main():
    failures = []
    temporary, root = fixture_root()
    try:
        dag = command(root, "dag.py", "fixture", "--json")
        if dag.returncode != 0:
            failures.append("DAG command returned non-zero for the valid fixture")
        else:
            report = json.loads(dag.stdout)
            if not report["valid"] or report["ready"] != ["T3"] or report["done"] != ["T1", "T2"]:
                failures.append("valid fixture DAG did not expose the expected ready barrier")

        status = command(root, "orchestrate.py", "fixture", "status", "--json")
        if status.returncode != 0:
            failures.append("coordinator status command failed for the valid fixture")
        else:
            result = json.loads(status.stdout)
            if result.get("kind") != "dag-report" or result.get("contractVersion") != 1:
                failures.append("coordinator status did not return orchestration v1 report")

        missing = command(root, "dag.py", "missing", "--json")
        if missing.returncode == 0:
            failures.append("missing fixture feature was accepted")

        invalid = command(root, "dag.py", "invalid", "--json")
        if invalid.returncode == 0:
            failures.append("invalid fixture DAG was accepted")
    finally:
        temporary.cleanup()

    config = json.loads((ROOT / ".ai" / "config.json").read_text(encoding="utf-8"))
    policy = config.get("orchestration", {})
    if policy.get("mode") != "ide-native-workers" or policy.get("max_workers") != 4:
        failures.append("repository orchestration policy drifted")
    if config.get("execution", {}).get("task_cli", {}).get("enabled") is not False:
        failures.append("orchestration unexpectedly enabled task_cli")

    if failures:
        print("AI-Kit orchestration integration FAILED: " + "; ".join(failures))
        return 1
    print("AI-Kit orchestration integration OK: CLI boundary, DAG report, policy, and routing isolation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
