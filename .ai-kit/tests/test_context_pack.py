#!/usr/bin/env python3
"""Scope parsing and read-time knowledge freshness regressions."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from context_pack import build_pack
from knowledge_retrieval import projector, render_knowledge, retrieve_knowledge


class ContextPackCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / ".project/demo").mkdir(parents=True)
        (self.root / ".ai-kit/knowledge").mkdir(parents=True)

    def tearDown(self):
        self.temp.cleanup()

    def task(self, files):
        (self.root / ".project/demo/tasks.md").write_text(
            "- [ ] T1 Test timeout policy | owner: backend | scope: S | needs: - | files: " + files +
            "\n  - Accept: token=example must be rejected\n", encoding="utf-8")

    def indexed(self, text="## Timeout policy\nUse 30 seconds.\n"):
        path = self.root / ".ai-kit/knowledge/decisions.md"
        path.write_text(text, encoding="utf-8")
        items = projector.scan_all(self.root)
        (self.root / ".knowledge-index").mkdir(exist_ok=True)
        (self.root / ".knowledge-index/index.json").write_text(json.dumps({"schema_version": 1, "items": items}))
        return path, items

    def test_comma_space_glob_and_missing_scopes(self):
        (self.root / "src").mkdir()
        (self.root / "src/first.py").write_text("FIRST-FILE")
        (self.root / "src/with spaces.py").write_text("SPACE-FILE")
        self.task("src/first.py, src/with spaces.py,src/*.py,src/missing.py")
        pack = build_pack(self.root, "demo", "T1")
        self.assertEqual(pack.count("FIRST-FILE"), 1)
        self.assertEqual(pack.count("SPACE-FILE"), 1)
        self.assertIn("--- src/missing.py (not created yet)", pack)
        self.assertNotIn("src/first.py (not created yet)", pack)
        self.assertIn("token=example must be rejected", pack)

    def test_scope_escape_and_symlink_fail_closed(self):
        for scope in ("../outside", "/tmp/outside", "C:/outside"):
            self.task(scope)
            with self.assertRaises(ValueError):
                build_pack(self.root, "demo", "T1")
        link = self.root / "linked"
        try:
            link.symlink_to(self.root / ".ai-kit", target_is_directory=True)
        except OSError:
            self.skipTest("symlink permission unavailable")
        self.task("linked/knowledge")
        with self.assertRaisesRegex(ValueError, "symlink"):
            build_pack(self.root, "demo", "T1")

    def test_live_hash_drift_without_refresh_is_pointer_only(self):
        path, _ = self.indexed()
        self.assertIn("30 seconds", render_knowledge(retrieve_knowledge(self.root, "timeout policy")))
        path.write_text("## Timeout policy\nUse 60 seconds.\n")
        result = retrieve_knowledge(self.root, "timeout policy")
        self.assertEqual(result["entries"], [])
        self.assertIn("stale: see .ai-kit/knowledge/decisions.md directly", render_knowledge(result))
        self.assertNotIn("30 seconds", render_knowledge(result))

    def test_absent_invalid_empty_and_disabled_index_use_live_fallback(self):
        self.indexed()
        index = self.root / ".knowledge-index/index.json"
        for content in (None, "not json", "{}", '{"schema_version":1,"items":[]}',
                        '{"schema_version":1,"disabled":true,"items":[]}'):
            if content is None:
                index.unlink()
            else:
                index.write_text(content)
            result = retrieve_knowledge(self.root, "timeout policy")
            self.assertEqual(result["mode"], "fallback")
            self.assertIn("30 seconds", render_knowledge(result))

    def test_summary_tampering_and_unsafe_source_never_served(self):
        _, items = self.indexed()
        items[0]["summary"] = "FORGED-RULE"
        index = self.root / ".knowledge-index/index.json"
        index.write_text(json.dumps({"schema_version": 1, "items": items}))
        self.assertNotIn("FORGED-RULE", render_knowledge(retrieve_knowledge(self.root, "timeout policy")))
        items[0]["source_path"] = "../outside.md"
        index.write_text(json.dumps({"schema_version": 1, "items": items}))
        result = retrieve_knowledge(self.root, "timeout policy")
        self.assertEqual(result["mode"], "fallback")
        self.assertNotIn("FORGED-RULE", render_knowledge(result))
        self.assertEqual(result["pointers"], [])

    def test_malformed_hash_uses_live_fallback(self):
        _, items = self.indexed()
        items[0]["source_hash"] = "not-a-hash"
        (self.root / ".knowledge-index/index.json").write_text(json.dumps({"schema_version": 1, "items": items}))
        result = retrieve_knowledge(self.root, "timeout policy")
        self.assertEqual(result["mode"], "fallback")
        self.assertIn("30 seconds", render_knowledge(result))

    def test_conflicts_and_supersession_are_explicit(self):
        path, _ = self.indexed()
        (path.parent / "conventions.md").write_text("## Timeout policy\nUse 60 seconds.\n")
        items = projector.scan_all(self.root)
        index = self.root / ".knowledge-index/index.json"
        index.write_text(json.dumps({"schema_version": 1, "items": items}))
        self.assertEqual(render_knowledge(retrieve_knowledge(self.root, "timeout policy")).count("CONFLICT:"), 2)
        items[0]["superseded_by"] = items[1]["id"]
        index.write_text(json.dumps({"schema_version": 1, "items": items}))
        self.assertEqual(len(retrieve_knowledge(self.root, "timeout policy")["entries"]), 1)

    def test_secret_changed_source_and_missing_source_do_not_leak(self):
        path, _ = self.indexed()
        path.write_text("## Timeout policy\napi_key: EXAMPLE_VALUE_123456\n")
        result = render_knowledge(retrieve_knowledge(self.root, "timeout policy"))
        self.assertNotIn("EXAMPLE_VALUE_123456", result)
        self.assertNotIn("30 seconds", result)
        path.unlink()
        self.assertEqual(retrieve_knowledge(self.root, "timeout policy")["entries"], [])

    def test_malformed_contract_json_is_pointer_only(self):
        (self.root / ".contracts").mkdir()
        path = self.root / ".contracts/timeout.schema.json"
        path.write_text(json.dumps({"title": "Timeout policy", "description": "Original timeout rule"}))
        (self.root / ".knowledge-index").mkdir()
        (self.root / ".knowledge-index/index.json").write_text(json.dumps({
            "schema_version": 1, "items": projector.scan_all(self.root)}))
        path.write_text("[]")
        result = retrieve_knowledge(self.root, "timeout policy")
        self.assertEqual(result["entries"], [])
        self.assertIn("stale: see .contracts/timeout.schema.json", render_knowledge(result))
        self.assertNotIn("Original timeout rule", render_knowledge(result))


if __name__ == "__main__":
    unittest.main()
