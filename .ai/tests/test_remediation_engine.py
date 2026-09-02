#!/usr/bin/env python3
"""Coordinator remediation transition and linked replan mechanics."""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".ai/harness"))

from engine import EngineError, HarnessEngine  # noqa: E402
from cli import parser, status_view  # noqa: E402
from models import new_state  # noqa: E402
from policy import normalize_plan  # noqa: E402
from projection import render_plan  # noqa: E402
from store import RepositoryStore  # noqa: E402


def task(number, **extra):
    value = {
        "id": "T%d" % number,
        "title": "Task %d" % number,
        "description": "Bounded task %d" % number,
        "dependencies": [],
        "acceptance_criteria": ["task %d passes" % number],
        "owner": "backend",
        "scope": "S",
        "files": ["src/task%d.py" % number],
        "risks": [],
        "review_required": True,
    }
    value.update(extra)
    return value


def main():
    failures = []
    with tempfile.TemporaryDirectory(prefix="ai-kit-remediation-") as directory:
        root = Path(directory)
        (root / ".ai").mkdir()
        (root / "AGENTS.md").write_text("# fixture\n", encoding="utf-8")
        (root / ".project/demo").mkdir(parents=True)
        store = RepositoryStore(root)
        engine = HarnessEngine(store)
        state = new_state("demo", "remediation test")
        state["status"] = "planned"
        state["tasks"] = normalize_plan({"summary": "initial", "tasks": [task(1)]})
        store.save_state("demo", state)

        recorded = engine.record_remediation(
            "demo", "T1", source_gate="qa", severity="major",
            criterion="task 1 passes", summary="output is absent", retry=True,
        )
        record = recorded["remediations"][0]
        if record["id"] != "REM-1" or record["attempts"] != 1 or recorded["tasks"][0]["attempts"] != 1:
            failures.append("retry finding was not persisted with source attempt")
        try:
            engine.record_remediation(
                "demo", "T1", source_gate="qa", severity="major",
                criterion="task 1 passes", summary="duplicate", retry=False,
            )
            failures.append("duplicate open finding was accepted")
        except EngineError:
            pass

        plan = {
            "summary": "add linked fix",
            "tasks": [
                task(1),
                task(2, dependencies=["T1"], remediation_id="REM-1", remediation_of="T1"),
            ],
        }
        replanned = engine.apply_plan("demo", plan, replan=True)
        if replanned["remediations"][0]["fix_task"] != "T2":
            failures.append("replan did not bind the linked fix task")
        if "## Remediations" not in render_plan(replanned):
            failures.append("projection omitted remediation records")
        if status_view(replanned).get("remediations", [])[0]["id"] != "REM-1":
            failures.append("status omitted remediation records")
        parsed = parser().parse_args(["remediate", "demo", "T1", "--source-gate", "qa", "--severity", "major", "--criterion", "task 1 passes", "--summary", "output is absent"])
        if parsed.command != "remediate" or parsed.retry:
            failures.append("coordinator remediation CLI contract is incorrect")
        try:
            engine.resolve_remediation("demo", "REM-1")
            failures.append("finding resolved before fix task completion")
        except EngineError:
            pass

        state = store.load_state("demo")
        for item in state["tasks"]:
            item["state"] = "complete"
        state["status"] = "complete"
        store.save_state("demo", state)
        try:
            engine.resolve_remediation("demo", "REM-1")
            failures.append("finding resolved without approved G3 review")
        except EngineError:
            pass
        state = store.load_state("demo")
        for item in state["tasks"]:
            if item["id"] == "T2":
                item["reviews"] = [{"policy": "active-agent", "verdict": "approve"}]
        store.save_state("demo", state)
        resolved = engine.resolve_remediation("demo", "REM-1")
        if resolved["remediations"][0]["status"] != "resolved" or not resolved["remediations"][0]["resolved_at"]:
            failures.append("completed fix task did not resolve finding")
    if failures:
        print("AI-Kit remediation engine FAILED: " + "; ".join(failures))
        return 1
    print("AI-Kit remediation engine OK: record, retry, linked replan, and guarded resolution")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
