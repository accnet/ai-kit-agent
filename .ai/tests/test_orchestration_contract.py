#!/usr/bin/env python3
"""Offline contract fixtures for the AI-Kit native orchestration v1 schema."""

from copy import deepcopy
import sys

from support.contract_validator import ContractError, VALIDATOR


def policy():
    return {
        "kind": "policy",
        "contractVersion": 1,
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


def dag_report():
    return {
        "kind": "dag-report",
        "contractVersion": 1,
        "feature": "fixture",
        "valid": True,
        "ready": ["T4", "T5", "T14"],
        "blocked": [{"task": "T7", "reasons": ["needs T4"]}],
        "active": [],
        "done": ["T1"],
        "conflicts": [],
        "errors": [],
        "max_workers": 4,
        "dispatchable": ["T4", "T5", "T14"],
    }


def worker_manifest():
    return {
        "kind": "worker-manifest",
        "contractVersion": 1,
        "coordinator_lease": "fixture:T4:1",
        "task": "T4",
        "files": ["inc/example.php"],
        "worktree": {"path": "/tmp/fixture-worker-t4", "isolated": True, "clean": True},
        "worker": {"id": "worker-t4", "scheduler": "codex-ide"},
    }


def transition():
    return {
        "kind": "transition",
        "contractVersion": 1,
        "coordinator_lease": "fixture:T4:1",
        "actor": "coordinator",
        "task": "T4",
        "status": "completed",
        "evidence": ["python3 .ai/tests/test_dag.py"],
        "barrier": {"satisfied": False, "dependencies": ["T1"]},
    }


def expect_valid(value):
    VALIDATOR.validate(value, "ai-kit-orchestration.v1.schema.json")


def expect_invalid(value):
    try:
        expect_valid(value)
    except (ContractError, OSError, ValueError):
        return True
    return False


def main():
    valid = [policy(), dag_report(), worker_manifest(), transition()]
    failures = []
    for name, fixture in zip(("policy", "DAG report", "worker manifest", "transition"), valid):
        try:
            expect_valid(fixture)
        except Exception as error:  # pragma: no cover - assertion reporting
            failures.append("%s: %s" % (name, error))

    invalid_cases = []
    broken = policy()
    broken["orchestration"]["max_workers"] = 5
    invalid_cases.append(("worker cap above four", broken))
    broken = policy()
    broken["orchestration"]["provider"] = "grok"
    invalid_cases.append(("provider leakage", broken))
    broken = dag_report()
    broken["ready"] = ["T4", "T4"]
    invalid_cases.append(("duplicate ready task", broken))
    broken = worker_manifest()
    broken["worker"]["scheduler"] = "custom-api"
    invalid_cases.append(("non-IDE scheduler", broken))
    broken = worker_manifest()
    broken["worktree"]["isolated"] = False
    invalid_cases.append(("shared worktree", broken))
    broken = transition()
    broken["actor"] = "worker"
    invalid_cases.append(("worker-owned transition", broken))
    for name, fixture in invalid_cases:
        if not expect_invalid(fixture):
            failures.append(name + " unexpectedly accepted")

    if failures:
        print("AI-Kit orchestration contract FAILED: " + "; ".join(failures))
        return 1
    print("AI-Kit orchestration contract OK: %d valid + %d invalid fixtures" % (len(valid), len(invalid_cases)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
