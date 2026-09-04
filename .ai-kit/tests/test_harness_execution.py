#!/usr/bin/env python3
"""Profile-backed verification execution evidence and early-stop tests."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".ai-kit/harness"))
from engine import HarnessEngine
from store import RepositoryStore


class ProfileExecutionCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / ".ai-kit").mkdir()
        (self.root / "AGENTS.md").write_text("# fixture\n", encoding="utf-8")
        (self.root / "pass.py").write_text("print('pass')\n", encoding="utf-8")
        (self.root / "fail.py").write_text("raise SystemExit(1)\n", encoding="utf-8")
        (self.root / ".ai-kit" / "qa-profiles.json").write_text(json.dumps({
            "schema_version": 1,
            "profiles": {
                "pass": {"command": ["python3", "pass.py"], "cwd": ".", "timeout_seconds": 30,
                         "evidence": {"feature": "fixture", "task": "T1", "artifacts": ["stdout"]}},
                "fail": {"command": ["python3", "fail.py"], "cwd": ".", "timeout_seconds": 30,
                         "evidence": {"feature": "fixture", "task": "T1", "artifacts": ["stdout"]}},
            },
        }), encoding="utf-8")
        self.engine = HarnessEngine(RepositoryStore(self.root))

    def tearDown(self):
        self.temp.cleanup()

    def test_profile_evidence_is_durable_and_stops_after_failure(self):
        task = {"id": "T1", "verification_commands": [], "verification_profiles": ["pass", "fail"]}
        records = self.engine._run_verification_commands(task)
        self.assertEqual([record.get("profile_id") for record in records], ["pass", "fail"])
        self.assertTrue(records[0]["passed"])
        self.assertFalse(records[1]["passed"])
        self.assertEqual(records[0]["cwd"], ".")
        self.assertEqual(records[0]["timeout_seconds"], 30)
        self.assertIn("output_digest", records[0])
        self.assertEqual(records[0]["metadata"]["feature"], "fixture")


if __name__ == "__main__":
    unittest.main(verbosity=2)
