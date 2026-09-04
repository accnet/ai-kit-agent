#!/usr/bin/env python3
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.adapters.workflow import AdapterError, WorkflowAdapter


def contract():
    return {"states": ["new", "done"], "terminal_states": ["done"],
            "transitions": [{"from": "new", "to": "done"}], "source_of_truth": "orders-db",
            "timeout": {"seconds": 30}, "retry": {"maximum": 3},
            "idempotency": {"key": "order_id"}, "compensation": {"action": "cancel-order"}}


def main():
    adapter = WorkflowAdapter()
    old = contract()
    removed = copy.deepcopy(old)
    removed["states"] = ["new"]
    removed["terminal_states"] = ["new"]
    removed["transitions"] = []
    assert adapter.compare(old, removed)["classification"] == "breaking"
    changed = copy.deepcopy(old)
    changed["retry"] = {"maximum": 5}
    assert adapter.compare(old, changed)["classification"] == "breaking"
    malformed = contract()
    malformed["transitions"] = [{"from": "new", "to": "missing"}]
    try:
        adapter.validate(malformed)
    except AdapterError:
        pass
    else:
        raise AssertionError("unknown transition state must fail")
    unsupported = contract()
    unsupported["transitions"][0]["guard"] = "paid"
    try:
        adapter.validate(unsupported)
    except AdapterError:
        pass
    else:
        raise AssertionError("unsupported workflow semantics must fail closed")
    malformed = contract()
    malformed["terminal_states"] = [{}]
    try:
        adapter.validate(malformed)
    except AdapterError:
        pass
    else:
        raise AssertionError("malformed workflow state must raise AdapterError")
    print("Workflow adapter OK")


if __name__ == "__main__":
    main()
