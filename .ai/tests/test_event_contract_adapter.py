#!/usr/bin/env python3
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.adapters.event import AdapterError, EventAdapter


def contract():
    return {
        "asyncapi": "2.6.0",
        "channels": {"orders": {
            "direction": "publish", "key": "order_id", "ordering": "key",
            "delivery": "at-least-once", "replay": True, "duplicates": "idempotent",
            "dlq": "orders.dlq", "message": {"payload": {
                "type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]
            }}
        }},
        "cloud_events": {"specversion": "1.0", "required_fields": ["specversion", "id", "source", "type"]},
    }


def main():
    adapter = EventAdapter()
    old = contract()
    for field, value in (("key", "customer_id"), ("ordering", "global"), ("delivery", "exactly-once")):
        changed = copy.deepcopy(old)
        changed["channels"]["orders"][field] = value
        assert adapter.compare(old, changed)["classification"] == "breaking"
    changed = copy.deepcopy(old)
    changed["channels"]["orders"]["message"]["payload"]["properties"]["id"]["type"] = "integer"
    assert adapter.compare(old, changed)["classification"] == "breaking"
    incomplete = contract()
    incomplete["cloud_events"]["required_fields"] = ["id"]
    try:
        adapter.validate(incomplete)
    except AdapterError:
        pass
    else:
        raise AssertionError("incomplete CloudEvents metadata must fail")
    unsupported = contract()
    unsupported["channels"]["orders"]["bindings"] = {}
    try:
        adapter.validate(unsupported)
    except AdapterError:
        pass
    else:
        raise AssertionError("unsupported event semantics must fail closed")
    malformed = contract()
    malformed["channels"]["orders"]["delivery"] = []
    try:
        adapter.validate(malformed)
    except AdapterError:
        pass
    else:
        raise AssertionError("malformed event enum must raise AdapterError")
    print("Event adapter OK")


if __name__ == "__main__":
    main()
