#!/usr/bin/env python3
"""Regression tests for read-only cross-feature completion barriers."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "harness"))
from dependencies import CrossFeatureDependencyResolver


class DependencyResolverCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / ".project").mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def feature(self, name, state=None, tasks=None):
        directory = self.root / ".project" / name
        directory.mkdir()
        if state is not None:
            (directory / "state.json").write_text(json.dumps(state), encoding="utf-8")
        if tasks is not None:
            (directory / "tasks.md").write_text(tasks, encoding="utf-8")

    def resolve(self, dependencies):
        return CrossFeatureDependencyResolver(self.root, "current").resolve(dependencies)

    def test_canonical_and_legacy_completed_targets_are_satisfied(self):
        self.feature("canonical", {"feature": "canonical", "tasks": [{"id": "T1", "state": "complete"}]})
        self.feature("legacy", tasks="- [x] T2 completed\n")
        results = self.resolve([{"feature": "canonical", "task": "T1"}, {"feature": "legacy", "task": "T2"}])
        self.assertEqual([(item.satisfied, item.source) for item in results], [(True, "state.json"), (True, "tasks.md")])

    def test_canonical_state_precedence_and_invalid_targets_fail_closed_without_writes(self):
        self.feature("precedence", {"feature": "precedence", "tasks": [{"id": "T1", "state": "ready"}]}, "- [x] T1 stale projection\n")
        self.feature("malformed", state="not-json")
        before = {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        results = self.resolve([
            {"feature": "precedence", "task": "T1"},
            {"feature": "malformed", "task": "T1"},
            {"feature": "missing", "task": "T1"},
            {"feature": "current", "task": "T1"},
        ])
        self.assertTrue(all(not item.satisfied for item in results))
        self.assertIn("unfinished canonical", results[0].diagnostic)
        self.assertIn("malformed canonical", results[1].diagnostic)
        self.assertIn("missing feature", results[2].diagnostic)
        self.assertIn("self-referencing", results[3].diagnostic)
        self.assertEqual(before, {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()})

    def test_duplicate_and_cyclic_targets_fail_closed(self):
        self.feature("a", {"feature": "a", "feature_dependencies": [{"feature": "b", "task": "T1"}], "tasks": [{"id": "T1", "state": "complete"}]})
        self.feature("b", {"feature": "b", "feature_dependencies": [{"feature": "a", "task": "T1"}], "tasks": [{"id": "T1", "state": "complete"}]})
        cycle = self.resolve([{"feature": "a", "task": "T1"}])[0]
        duplicate = self.resolve([{"feature": "a", "task": "T1"}, {"feature": "a", "task": "T1"}])[1]
        self.assertFalse(cycle.satisfied)
        self.assertIn("cyclic", cycle.diagnostic)
        self.assertFalse(duplicate.satisfied)
        self.assertIn("duplicate", duplicate.diagnostic)


if __name__ == "__main__":
    unittest.main(verbosity=2)
