#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.capability_config import CapabilityError, infer_minimum, resolve, resolve_plan

def rejected(call, message):
    try: call()
    except CapabilityError: return
    raise AssertionError(message)

def main():
    # Correct LLM proposal with repository evidence.
    correct = resolve(["contract_graph"], [".contracts/registry.json"])
    assert "service_ownership" in correct["capabilities"]
    # Unsupported and evidence-free proposals fail closed.
    rejected(lambda: resolve(["invented"], ["task:api"]), "unknown proposal accepted")
    rejected(lambda: resolve(["contract_graph"], []), "evidence-free proposal accepted")
    # Mandatory gates cannot be disabled, while an audited optional override works.
    rejected(lambda: resolve([], ["task:test"], {"testing": False}), "testing floor disabled")
    overridden = resolve([], ["task:release"], {"release_ordering": True})
    assert "release_ordering" in overridden["capabilities"]
    # Legacy/small plan keeps only core; declarations activate mandatory governance.
    legacy = resolve_plan({"tasks": []})
    assert "contract_graph" not in legacy["capabilities"]
    cross_service = resolve_plan({"services":[{"id":"web"},{"id":"api"}], "contracts":[{"id":"public.api"}], "tasks":[]})
    assert {"contract_graph", "contract_compatibility", "integration_qa"}.issubset(cross_service["capabilities"])
    database = resolve_plan({"tasks":[{"risks":["database"], "data_entities":["orders"]}]})
    assert "database_safety" in database["capabilities"]
    assert "database_safety" not in infer_minimum([".contracts/public.schema.json"])["capabilities"]
    print("Capability QA matrix OK")
if __name__ == "__main__": main()
