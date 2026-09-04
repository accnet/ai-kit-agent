#!/usr/bin/env python3
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.adapters.data import AdapterError, DataAdapter


def contract():
    return {"writer": "orders", "readers": ["billing"],
            "entities": [{"name": "orders", "type": "record", "nullable": False}],
            "integrity": ["orders.id unique"],
            "migration": {"phases": ["expand", "backfill", "switch", "contract"],
                          "reconciliation": {"check": "row-count"}, "rollback": {"action": "restore-reader"}}}


def main():
    adapter = DataAdapter()
    old = contract()
    removed = copy.deepcopy(old)
    removed["entities"] = []
    assert adapter.compare(old, removed)["classification"] == "breaking"
    changed = copy.deepcopy(old)
    changed["writer"] = "billing"
    assert adapter.compare(old, changed)["classification"] == "breaking"
    try:
        adapter.validate({"writer": "orders", "readers": [], "entities": [],
                          "migration": {"phases": ["expand"], "reconciliation": {}, "rollback": {}}})
    except AdapterError:
        pass
    else:
        raise AssertionError("incomplete migration metadata must fail")
    unsupported = contract()
    unsupported["entities"][0]["precision"] = 10
    try:
        adapter.validate(unsupported)
    except AdapterError:
        pass
    else:
        raise AssertionError("unsupported data semantics must fail closed")
    print("Data adapter OK")


if __name__ == "__main__":
    main()
