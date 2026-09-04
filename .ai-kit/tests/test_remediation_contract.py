#!/usr/bin/env python3
"""Remediation record and linked fix-task contract mechanics."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".ai-kit/harness"))

from models import new_state, validate_state  # noqa: E402
from policy import PolicyError, normalize_plan, validate_remediation_links  # noqa: E402


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


def remediation(**overrides):
    value = {
        "id": "REM-1",
        "source_gate": "qa",
        "source_task": "T1",
        "severity": "major",
        "criterion": "task 1 passes",
        "summary": "Expected output is missing",
        "status": "open",
        "fix_task": "T2",
        "attempts": 0,
        "created_at": "2026-08-30T00:00:00Z",
        "resolved_at": None,
    }
    value.update(overrides)
    return value


def main():
    failures = []
    state = new_state("demo", "remediation")
    state["tasks"] = [
        {**task(1), "state": "complete", "attempts": 0, "evidence": [], "reviews": []},
        {**task(2, remediation_id="REM-1", remediation_of="T1"), "state": "ready", "attempts": 0, "evidence": [], "reviews": []},
    ]
    state["remediations"] = [remediation()]
    try:
        validate_state(state)
    except ValueError as exc:
        failures.append("valid remediation state rejected: %s" % exc)
    try:
        validate_remediation_links(state, state["tasks"])
    except PolicyError as exc:
        failures.append("valid remediation link rejected: %s" % exc)

    invalid = dict(state)
    invalid["remediations"] = [remediation(fix_task="T9")]
    try:
        validate_state(invalid)
        failures.append("unknown fix task accepted")
    except ValueError:
        pass

    incomplete = task(2, remediation_id="REM-1")
    try:
        normalize_plan({"summary": "invalid link", "tasks": [task(1), incomplete]})
        failures.append("incomplete remediation link accepted")
    except PolicyError:
        pass

    legacy = new_state("legacy", "backward compatibility")
    legacy["tasks"] = [{**task(1), "state": "ready", "attempts": 0, "evidence": [], "reviews": []}]
    try:
        validate_state(legacy)
    except ValueError as exc:
        failures.append("state without remediation fields rejected: %s" % exc)

    if failures:
        print("AI-Kit remediation contract FAILED: " + "; ".join(failures))
        return 1
    print("AI-Kit remediation contract OK: records, links, rejection, and compatibility")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
