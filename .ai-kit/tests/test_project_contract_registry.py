#!/usr/bin/env python3
import json, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.project_contracts import ProjectContractError, load_registry, validate_contracts

def main():
    with tempfile.TemporaryDirectory() as d:
        root=Path(d); (root/".contracts").mkdir(); (root/".contracts/schema.json").write_text('{"type":"object"}', encoding="utf-8")
        data={"schema_version":1,"services":[{"id":"orders"}],"contracts":[{"id":"orders.schema","version":"1.0.0","kind":"schema","owner":"orders","producers":["orders"],"consumers":[],"source":".contracts/schema.json"}]}
        (root/".contracts/registry.json").write_text(json.dumps(data), encoding="utf-8")
        out=load_registry(root); assert out["contracts"][0]["source_hash"].startswith("sha256:")
        assert validate_contracts(root)["valid"] is True
        (root/".contracts/registry.json").write_text(json.dumps({**data,"contracts":[{**data["contracts"][0],"kind":"unknown"}]}), encoding="utf-8")
        try: load_registry(root)
        except ProjectContractError: pass
        else: raise AssertionError("unsupported kind must fail")
        (root/".ai-kit/contracts").mkdir(parents=True); (root/".ai-kit/contracts/runtime.json").write_text('{"type":"object"}', encoding="utf-8")
        bad_source={**data,"contracts":[{**data["contracts"][0],"source":".ai-kit/contracts/runtime.json"}]}
        (root/".contracts/registry.json").write_text(json.dumps(bad_source), encoding="utf-8")
        try: load_registry(root)
        except ProjectContractError: pass
        else: raise AssertionError("AI-Kit runtime source must be rejected")
        bad_case={"schema_version":1,"services":[{"id":"orders","contract_paths":[".AI-KIT/contracts"]}],"contracts":[]}
        (root/".contracts/registry.json").write_text(json.dumps(bad_case), encoding="utf-8")
        try: load_registry(root)
        except ProjectContractError: pass
        else: raise AssertionError("case-variant AI-Kit control root must be rejected")
        (root/".contracts/registry.json").write_text(json.dumps({"schema_version":1,"services":[{"id":None}],"contracts":[]}), encoding="utf-8")
        try: load_registry(root)
        except ProjectContractError: pass
        else: raise AssertionError("null service id must be rejected")
        for invalid in ("orders-", "orders--api"):
            (root/".contracts/registry.json").write_text(json.dumps({"schema_version":1,"services":[{"id":invalid}],"contracts":[]}), encoding="utf-8")
            try: load_registry(root)
            except ProjectContractError: pass
            else: raise AssertionError("invalid service id must be rejected")
        uppercase={**data,"contracts":[{**data["contracts"][0],"id":"Orders.schema"}]}
        (root/".contracts/registry.json").write_text(json.dumps(uppercase), encoding="utf-8")
        try: load_registry(root)
        except ProjectContractError: pass
        else: raise AssertionError("uppercase contract id must be rejected")
        (root/"services/orders/contracts").mkdir(parents=True)
        (root/"services/orders/contracts/schema.json").write_text('{"type":"object"}', encoding="utf-8")
        owned={"schema_version":1,"services":[{"id":"orders","contract_paths":["services/orders/contracts"]}],"contracts":[{**data["contracts"][0],"source":"services/orders/contracts/schema.json"}]}
        (root/".contracts/registry.json").write_text(json.dumps(owned), encoding="utf-8")
        assert load_registry(root)["contracts"][0]["source_hash"].startswith("sha256:")
    print("AI-Kit project contract registry OK")
if __name__ == "__main__": main()
