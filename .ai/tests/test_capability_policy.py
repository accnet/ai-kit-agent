#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.capability_config import infer_minimum, resolve_plan
def main():
    value = infer_minimum([".contracts/registry.json", "db/migrations"])
    assert "contract_graph" in value["capabilities"] and "database_safety" in value["capabilities"]
    schema_only = infer_minimum([".contracts/order.schema.json"])
    assert "contract_graph" in schema_only["capabilities"] and "database_safety" not in schema_only["capabilities"]
    database = infer_minimum(["services/orders/db/schema.sql"])
    assert "database_safety" in database["capabilities"]
    small = resolve_plan({"tasks": []})
    assert "contract_graph" not in small["capabilities"]
    governed = resolve_plan({"services": [{"id":"orders"}], "contracts": [{"id":"orders.api"}], "tasks": []})
    assert {"service_ownership", "contract_graph", "contract_compatibility", "integration_qa"}.issubset(governed["capabilities"])
    release = resolve_plan({"tasks": [{"risks": ["production"]}]})
    assert "release_ordering" in release["capabilities"]
    print("Capability policy inference OK")
if __name__ == "__main__": main()
