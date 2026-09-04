#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.capability_config import resolve
def main():
    legacy = resolve()
    assert legacy["capabilities"] == sorted(legacy["capabilities"])
    assert legacy["provenance"]["source"] == "ide-llm"
    print("Capability resolver OK")
if __name__ == "__main__": main()
