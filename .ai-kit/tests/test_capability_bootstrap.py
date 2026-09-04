#!/usr/bin/env python3
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "harness"))
from harness.engine import HarnessEngine
from harness.store import RepositoryStore

def main():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d); (root / ".ai-kit").mkdir(); (root / "features" / "demo").mkdir(parents=True)
        (root / "AGENTS.md").write_text("# test\n", encoding="utf-8")
        (root / "features" / "demo" / "brief.md").write_text("# Demo\n", encoding="utf-8")
        store = RepositoryStore(root)
        HarnessEngine(store, independent_review_enabled=False).initialize(
            "demo", "test capability bootstrap", capabilities=["contract_graph"], capability_signals=[".contracts/registry.json"]
        )
        decision = store.feature_dir("demo") / "capabilities.json"
        assert decision.is_file()
        assert "contract_graph" in decision.read_text(encoding="utf-8")
        plan = {"summary":"minimal plan", "tasks":[{"id":"T1","title":"Build demo","description":"Implement demo task","dependencies":[],"acceptance_criteria":["demo passes"],"owner":"backend","scope":"S","files":["src/demo.py"],"risks":[],"review_required":True}]}
        planned = HarnessEngine(store, independent_review_enabled=False).apply_plan("demo", plan)
        assert "contract_graph" in planned["capability_decision"]["capabilities"]
    print("Capability bootstrap OK")
if __name__ == "__main__": main()
