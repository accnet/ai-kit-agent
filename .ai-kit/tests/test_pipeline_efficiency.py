#!/usr/bin/env python3
"""Measured same-phase I/O reuse with source and artifact mutation safeguards."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "harness"))
from models import new_state
from policy import canonical_digest, snapshot_repository
from projection import write_projections
from prompt_evidence import EvidenceError, prepare_evidence
from store import RepositoryStore
from verification import run_verification
from test_prompt_evidence import fixture
import prompt_evidence


class PipelineEfficiencyCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_caller_snapshot_is_reused_but_every_actual_check_gets_after_snapshot(self):
        _, task = fixture(self.root)
        initial = snapshot_repository(self.root)
        snapshots = {"after": {"old": "must not survive"}}
        with patch("verification.snapshot_repository", wraps=snapshot_repository) as scan:
            records = run_verification(task, self.root, self.root, initial_snapshot=initial,
                                       snapshot_data=snapshots)
        self.assertEqual(scan.call_count, 3)
        self.assertEqual(snapshots["before"], initial)
        self.assertEqual(snapshots["after"], initial)
        self.assertTrue(all(record["passed"] for record in records))
        self.assertEqual(records[-1]["source_snapshot_after"], canonical_digest(snapshots["after"]))
        with patch("verification.snapshot_repository", wraps=snapshot_repository) as scan:
            repeated = run_verification(task, self.root, self.root)
        self.assertEqual(scan.call_count, 4)
        self.assertNotEqual(records[0]["artifact_manifest"], repeated[0]["artifact_manifest"])

    def test_reused_snapshot_still_detects_command_mutation(self):
        _, task = fixture(self.root)
        (self.root / "check.py").write_text("from pathlib import Path\nPath('unexpected.txt').write_text('mutation')\n")
        initial = snapshot_repository(self.root)
        snapshots = {}
        records = run_verification(task, self.root, self.root, initial_snapshot=initial,
                                   snapshot_data=snapshots)
        self.assertFalse(records[0]["passed"])
        self.assertEqual(records[0]["failure_kind"], "repository_mutation")
        self.assertNotEqual(snapshots["before"], snapshots["after"])

    def test_failed_artifact_write_clears_after_channel_for_caller_fallback(self):
        _, task = fixture(self.root)
        snapshots = {"after": {"stale": "old phase"}}
        with patch("verification.reporter.execute_profile", side_effect=OSError("disk full")):
            records = run_verification(task, self.root, self.root,
                                       initial_snapshot=snapshot_repository(self.root), snapshot_data=snapshots)
        self.assertNotIn("after", snapshots)
        self.assertFalse(records[0]["passed"])

    def test_duplicate_artifact_reads_are_unique_per_prepare_and_per_guard(self):
        state, task = fixture(self.root, "duplicates")
        with patch("prompt_evidence._read", wraps=prompt_evidence._read) as read:
            package = prepare_evidence(state, task, self.root, self.root, review=True)
        self.assertEqual(read.call_count, 3)
        self.assertEqual(len(package.originals), 3)
        with patch("prompt_evidence._read", wraps=prompt_evidence._read) as read:
            package.validate()
        self.assertEqual(read.call_count, 3)
        log = self.root / task["verification_evidence"][0]["artifacts"]["stdout"]["path"]
        log.write_text("tampered")
        with self.assertRaises(EvidenceError):
            package.validate()

    def test_inconsistent_duplicate_metadata_is_not_hidden_by_read_deduplication(self):
        state, task = fixture(self.root, "duplicates")
        task = copy.deepcopy(task)
        task["verification_evidence"][1]["artifacts"]["stdout"]["bytes"] += 1
        with self.assertRaises(EvidenceError):
            prepare_evidence(state, task, self.root, self.root)

    def test_unchanged_projection_skips_writes_and_stale_content_is_repaired(self):
        (self.root / ".ai-kit").mkdir()
        (self.root / "AGENTS.md").write_text("# Rules\n")
        store = RepositoryStore(self.root)
        state = new_state("demo", "goal")
        write_projections(store, state)
        with patch.object(store, "write_text_atomic", wraps=store.write_text_atomic) as write:
            write_projections(store, state)
        self.assertEqual(write.call_count, 0)
        (store.feature_dir("demo") / "tasks.md").write_text("stale")
        with patch.object(store, "write_text_atomic", wraps=store.write_text_atomic) as write:
            write_projections(store, state)
        self.assertEqual(write.call_count, 1)
        self.assertIn("# Tasks", (store.feature_dir("demo") / "tasks.md").read_text())


if __name__ == "__main__":
    unittest.main()
