#!/usr/bin/env python3
import json, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.capability_config import CapabilityError, load_catalog, resolve
def main():
    result = resolve({"contract_compatibility"}, [".contracts/registry.json"])
    assert "contract_graph" in result["capabilities"] and "approval" in result["capabilities"]
    try: resolve(overrides={"testing": False})
    except CapabilityError: pass
    else: raise AssertionError("safety floor must be immutable")
    try: resolve(["contract_graph"])
    except CapabilityError: pass
    else: raise AssertionError("evidence-free proposal must fail")
    try: resolve([], ["task"], {"release_ordering": "yes"})
    except CapabilityError: pass
    else: raise AssertionError("non-boolean override must fail")
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "catalog.json"
        path.write_text(json.dumps({"schema_version":1,"safety_floor":sorted({"planning","file_scope","approval","testing","review","credential_restrictions","destructive_approval"}),"capabilities":{"broken":{"requires":["missing"],"conflicts":[]}}}), encoding="utf-8")
        try: load_catalog(path)
        except CapabilityError: pass
        else: raise AssertionError("unknown dependency must fail")
    print("Capability config OK")
if __name__ == "__main__": main()
