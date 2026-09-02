#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.adapters.json_schema import JsonSchemaAdapter
from harness.adapters.api import ApiAdapter
from harness.adapters.event import EventAdapter
from harness.adapters.data import DataAdapter
from harness.adapters.workflow import WorkflowAdapter

def main():
    assert JsonSchemaAdapter().analyze({"type":"object"},{"type":"object","properties":{"x":{"type":"string"}}})["verification"]["writes"] is False
    assert ApiAdapter().validate({"openapi":"3.0.0","paths":{}})["valid"]
    assert EventAdapter().validate({"asyncapi":"2.6.0","channels":{},"cloud_events":{"specversion":"1.0","required_fields":["specversion","id","source","type"]}})["cloud_events"]
    assert DataAdapter().validate({"writer":"orders","readers":[],"entities":[],"migration":{"phases":["expand","backfill","switch","contract"],"reconciliation":{"check":"count"},"rollback":{"action":"restore"}}})["valid"]
    assert WorkflowAdapter().validate({"states":["new","done"],"terminal_states":["done"],"transitions":[{"from":"new","to":"done"}],"source_of_truth":"db","timeout":{"seconds":30},"retry":{"maximum":3},"idempotency":{"key":"id"},"compensation":{"action":"undo"}})["valid"]
    print("AI-Kit contract adapter interface OK")
if __name__ == "__main__": main()
