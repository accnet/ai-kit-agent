#!/usr/bin/env python3
"""Rendered context bounds, relevance, freshness and shared knowledge tests."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "harness"))
from memory import MemoryStore
from store import RepositoryStore
from knowledge_retrieval import projector, retrieve_knowledge


class RetrievalCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / ".ai-kit/knowledge").mkdir(parents=True)
        (self.root / "AGENTS.md").write_text("# Rules\nPreserve criteria.\n")
        (self.root / "features/demo").mkdir(parents=True)
        (self.root / "features/demo/brief.md").write_text("# Brief\nVerify scheduler.\n")
        self.memory = MemoryStore(RepositoryStore(self.root))

    def tearDown(self):
        self.temp.cleanup()

    def test_actual_rendered_characters_include_headers_and_separators(self):
        for index in range(8):
            self.memory.add("demo", "working", "scheduler " + "x" * 200, tags=[str(index)])
        for cap in (256, 512, 1000):
            result = self.memory.retrieve("demo", "scheduler", max_chars=cap)
            rendered = self.memory.render_context(result)
            self.assertLessEqual(len(rendered), cap)
            self.assertEqual(result["used_chars"], len(rendered))

    def test_zero_overlap_background_is_not_sent(self):
        self.memory.add("demo", "working", "billing and invoice", importance=5)
        self.memory.add("demo", "semantic", "scheduler approval")
        result = self.memory.retrieve("demo", "scheduler", include_project_sources=False)
        rendered = self.memory.render_context(result)
        self.assertNotIn("billing", rendered)
        self.assertIn("scheduler approval", rendered)

    def test_stale_memory_is_pointer_only(self):
        (self.root / "source.txt").write_text("original")
        self.memory.add("demo", "working", "scheduler OLD-RULE", source="source.txt")
        (self.root / "source.txt").write_text("changed")
        result = self.memory.retrieve("demo", "scheduler", include_project_sources=False)
        self.assertNotIn("OLD-RULE", self.memory.render_context(result))
        self.assertIn("source.txt", result["stale_sources"])
        self.assertIn("old summary excluded", self.memory.render_context(result))

    def test_pack_and_harness_share_verified_knowledge(self):
        path = self.root / ".ai-kit/knowledge/conventions.md"
        path.write_text("## Scheduler policy\nUse bounded queues.\n")
        (self.root / ".knowledge-index").mkdir()
        (self.root / ".knowledge-index/index.json").write_text(json.dumps({
            "schema_version": 1, "items": projector.scan_all(self.root)}))
        selected = retrieve_knowledge(self.root, "scheduler")
        result = self.memory.retrieve("demo", "scheduler")
        self.assertTrue(selected["entries"])
        self.assertIn(selected["entries"][0]["summary"], self.memory.render_context(result))
        path.write_text("## Scheduler policy\nUse new policy.\n")
        result = self.memory.retrieve("demo", "scheduler")
        self.assertNotIn("bounded queues", self.memory.render_context(result))
        self.assertIn(".ai-kit/knowledge/conventions.md", result["stale_sources"])

    def test_shared_file_provenance_is_read_once(self):
        path = self.root / "source.txt"
        path.write_text("scheduler current source")
        for _ in range(3):
            self.memory.add("demo", "working", "scheduler data", source="source.txt")
        reads = []
        original = Path.read_bytes

        def counted(target):
            reads.append(target)
            return original(target)

        with patch.object(Path, "read_bytes", counted):
            self.memory.retrieve("demo", "scheduler", include_project_sources=False)
        self.assertEqual(reads.count(path), 1)

    def test_pinned_architecture_takes_priority_over_background(self):
        path = self.root / ".project/demo"
        path.mkdir(parents=True)
        architecture = "required architecture detail " * 20
        (path / "architecture.md").write_text(architecture)
        self.memory.add("demo", "working", "scheduler " + "noise " * 150, importance=5)
        result = self.memory.retrieve("demo", "scheduler", max_chars=1000, include_project_instructions=False)
        entry = next(item for item in result["entries"] if item["provenance"]["ref"].endswith("architecture.md"))
        self.assertEqual(entry["content"], architecture)
        self.assertFalse(entry.get("truncated"))
        self.assertLessEqual(len(self.memory.render_context(result)), 1000)

    def test_unicode_counts_chars_separately_from_bytes(self):
        self.memory.add("demo", "working", "scheduler " + "\u03b1" * 500)
        result = self.memory.retrieve("demo", "scheduler", max_chars=256, include_project_sources=False)
        rendered = self.memory.render_context(result)
        self.assertLessEqual(len(rendered), 256)
        self.assertGreater(len(rendered.encode("utf-8")), len(rendered))

    def test_contract_provenance_and_knowledge_share_one_source_read(self):
        (self.root / ".contracts").mkdir()
        path = self.root / ".contracts/billing.schema.json"
        path.write_text(json.dumps({"title": "Billing schema", "description": "Billing invariants"}))
        self.memory.add("demo", "semantic", "billing contract", source=".contracts/billing.schema.json")
        (self.root / ".knowledge-index").mkdir()
        (self.root / ".knowledge-index/index.json").write_text(json.dumps({
            "schema_version": 1, "items": projector.scan_all(self.root)}))
        reads = []
        original = Path.read_bytes

        def counted(target):
            reads.append(target)
            return original(target)

        with patch.object(Path, "read_bytes", counted):
            result = self.memory.retrieve("demo", "billing")
        self.assertIn("Billing invariants", self.memory.render_context(result))
        self.assertEqual(reads.count(path), 1)


if __name__ == "__main__":
    unittest.main()
