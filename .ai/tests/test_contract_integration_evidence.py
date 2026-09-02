#!/usr/bin/env python3
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "harness"))
from harness.policy import PolicyError, normalize_plan, validate_success
from harness.schemas import PLAN_SCHEMA, validate


REFERENCE = "orders.data@1.0.0"


def plan(owner="qa", contract_evidence=None):
    task = {"id": "T1", "title": "Validate contract evidence", "description": "Verify governed contract evidence",
            "dependencies": [], "acceptance_criteria": ["acceptance passes"], "owner": owner, "scope": "S",
            "files": ["tests/evidence.py"], "risks": [], "review_required": False,
            "contract_reads": [REFERENCE]}
    if contract_evidence is not None:
        task["contract_evidence"] = contract_evidence
    return {"summary": "evidence", "services": [
                {"id": "orders", "domain": "orders", "paths": ["services/orders"], "owns_data": ["order"],
                 "exposes": [REFERENCE], "consumes": [], "dependencies": [], "forbidden_dependencies": []},
                {"id": "reporting", "domain": "reporting", "paths": ["services/reporting"], "owns_data": [],
                 "exposes": [], "consumes": [REFERENCE], "dependencies": ["orders"], "forbidden_dependencies": []}],
            "contracts": [{"id": "orders.data", "kind": "data", "version": "1.0.0", "owner": "orders",
                           "status": "draft", "source": ".contracts/orders.data.json", "source_hash": "pending",
                           "producers": ["orders"], "consumers": ["reporting"], "compatibility": "backward",
                           "change_type": "additive", "invariants": ["single writer"],
                           "verification": ["integration passes"], "rollout": "orders then reporting",
                           "rollback": "restore previous readers"}], "tasks": [task]}


def must_reject(value, fragment):
    try:
        normalize_plan(value)
    except PolicyError as exc:
        assert fragment in str(exc), str(exc)
    else:
        raise AssertionError("plan must fail: " + fragment)


def main():
    validate(plan(contract_evidence={"integration": ["producer-consumer passes"],
                                     "reconciliation": ["row hashes match"]}), PLAN_SCHEMA)
    must_reject(plan(), "integration, reconciliation")
    must_reject(plan("release", {"rollout": ["staged rollout passes"]}), "rollback, reconciliation")

    normalized = normalize_plan(plan(contract_evidence={"integration": ["producer-consumer passes"],
                                                        "reconciliation": ["row hashes match"]}))[0]
    result = {"outcome": "success", "changed_files": [], "evidence": [
        {"criterion": "acceptance passes", "result": "pass"},
        {"criterion": "producer-consumer passes", "result": "pass"},
    ]}
    try:
        validate_success(normalized, result)
    except PolicyError as exc:
        assert "row hashes match" in str(exc)
    else:
        raise AssertionError("completion must require passing contract evidence")
    complete = copy.deepcopy(result)
    complete["evidence"].append({"criterion": "row hashes match", "result": "pass"})
    validate_success(normalized, complete)
    print("Contract integration evidence policy OK")


if __name__ == "__main__":
    main()
