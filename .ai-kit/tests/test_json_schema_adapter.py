#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.adapters.json_schema import JsonSchemaAdapter
def main():
    result = JsonSchemaAdapter().compare({"type":"object","required":["id"]},{"type":"object","required":["id","name"]})
    assert result["classification"] == "breaking"
    print("JSON Schema adapter OK")
if __name__ == "__main__": main()
