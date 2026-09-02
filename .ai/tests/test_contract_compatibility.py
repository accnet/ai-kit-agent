#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "harness"))
from compatibility import CompatibilityError, compare

def main():
    base = {"type":"object", "properties":{"id":{"type":"string"}}, "required":["id"]}
    assert compare(base, base)["classification"] == "unchanged"
    assert compare(base, {**base, "properties":{**base["properties"], "name":{"type":"string"}}})["classification"] == "additive"
    assert compare(base, {"type":"object", "properties":{}, "required":[]})["classification"] == "breaking"
    assert compare({"type":"object","additionalProperties":True},{"type":"object","additionalProperties":False})["classification"] == "breaking"
    assert compare({}, {"type":"string"})["classification"] == "breaking"
    assert compare({"enum":[{"a":1}]},{"enum":[{"a":1},{"a":2}]})["classification"] == "additive"
    assert compare({"type":"array"},{"type":"array","items":{"type":"string"}})["classification"] == "breaking"
    for malformed in ({"required":1},{"required":[{}]},{"properties":{"x":1}},
                      {"$ref":1},{"type":"banana"},{"enum":[]},{"enum":[1,1]}):
        try: compare(malformed, {})
        except CompatibilityError: pass
        else: raise AssertionError("malformed schema must fail with CompatibilityError")
    try: compare(base, {"type":"object", "patternProperties":{}})
    except CompatibilityError: pass
    else: raise AssertionError("unsupported keywords must fail closed")
    print("AI-Kit contract compatibility OK")

if __name__ == "__main__": main()
