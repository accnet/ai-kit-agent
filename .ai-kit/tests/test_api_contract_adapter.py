#!/usr/bin/env python3
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.adapters.api import AdapterError, ApiAdapter


def contract():
    return {
        "openapi": "3.0.0",
        "paths": {
            "/orders": {
                "summary": "Orders",
                "get": {
                    "security": [{"bearer": []}],
                    "x-idempotency-key": "request-id",
                    "responses": {
                        "200": {"content": {"application/json": {"schema": {
                            "type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]
                        }}}}
                    },
                },
            }
        },
    }


def main():
    adapter = ApiAdapter()
    old = contract()
    removed_method = copy.deepcopy(old)
    del removed_method["paths"]["/orders"]["get"]
    assert adapter.compare(old, removed_method)["classification"] == "breaking"

    changed_auth = copy.deepcopy(old)
    changed_auth["paths"]["/orders"]["get"]["security"] = []
    assert adapter.compare(old, changed_auth)["classification"] == "breaking"

    root_auth_old = {"openapi": "3.0.0", "security": [{"bearer": []}], "paths": {}}
    root_auth_new = {"openapi": "3.0.0", "security": [], "paths": {}}
    assert adapter.compare(root_auth_old, root_auth_new)["classification"] == "breaking"

    changed_payload = copy.deepcopy(old)
    changed_payload["paths"]["/orders"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["properties"]["id"]["type"] = "integer"
    assert adapter.compare(old, changed_payload)["classification"] == "breaking"

    try:
        adapter.validate({"openapi": "3.0.0", "paths": {"/orders": {"get": {"security": {}}}}})
    except AdapterError:
        pass
    else:
        raise AssertionError("malformed security must fail with AdapterError")
    try:
        adapter.validate({"openapi": "3.0.0", "paths": {"/orders": {"parameters": []}}})
    except AdapterError:
        pass
    else:
        raise AssertionError("unsupported path semantics must fail closed")

    component_old = {"openapi": "3.0.0", "paths": {}, "components": {"schemas": {"Order": {"type": "string"}}}}
    component_new = copy.deepcopy(component_old)
    component_new["components"]["schemas"]["Order"]["type"] = "integer"
    assert adapter.compare(component_old, component_new)["classification"] == "breaking"
    print("API adapter OK")


if __name__ == "__main__":
    main()
