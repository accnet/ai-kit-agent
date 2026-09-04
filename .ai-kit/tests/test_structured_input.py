#!/usr/bin/env python3
"""Mechanics tests for structured input_requests over the existing needs_input
run state. Contract: .project/structured-user-input/architecture.md
"""

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "harness"))
from engine import EngineError, HarnessEngine
from store import RepositoryStore


def question(
    q_id="scope", *, required=True, allow_freeform=True, qtype="single_select",
    options=(("a", "A", True), ("b", "B", False)),
):
    return {
        "id": q_id,
        "prompt": "%s?" % q_id,
        "type": qtype,
        "options": [{"id": oid, "label": label, "recommended": rec} for oid, label, rec in options],
        "allow_freeform": allow_freeform,
        "required": required,
    }


class StructuredInputCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / ".ai-kit").mkdir()
        (self.root / "AGENTS.md").write_text("# fixture\n", encoding="utf-8")
        (self.root / "features" / "demo").mkdir(parents=True)
        (self.root / "features" / "demo" / "brief.md").write_text("# brief\n", encoding="utf-8")
        self.engine = HarnessEngine(RepositoryStore(self.root))
        self.engine.initialize("demo", "goal")
        self.engine.apply_plan("demo", {"summary": "initial plan", "tasks": [self._task(1)]})

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def _task(number):
        return {
            "id": "T%d" % number, "title": "Build", "description": "Implement",
            "dependencies": [], "acceptance_criteria": ["criterion passes"],
            "owner": "backend", "scope": "S", "files": ["src/%d.py" % number],
            "risks": [], "review_required": True,
        }

    def start(self):
        return self.engine.start_run("demo")

    # --- structured request creation -----------------------------------------

    def test_structured_request_creates_pending_entry_and_pauses_run(self):
        self.start()
        state = self.engine.request_structured_input("demo", reason="need scope", questions=[question()])
        self.assertEqual(state["run"]["state"], "needs_input")
        self.assertEqual(state["run"]["input_request_id"], "IN-1")
        record = state["input_requests"][0]
        self.assertEqual(record["id"], "IN-1")
        self.assertEqual(record["status"], "pending")
        self.assertEqual(record["plan_revision"], state["plan_revision"])
        self.assertTrue(record["schema_hash"].startswith("sha256:"))

    def test_ids_increment_and_never_collide(self):
        self.start()
        self.engine.request_structured_input("demo", reason="r1", questions=[question("q1")])
        state = self.engine.answer_input(
            "demo", "IN-1", actor="user", answers={"q1": {"selected": ["a"], "freeform": ""}}
        )
        self.engine.request_structured_input("demo", reason="r2", questions=[question("q2")])
        state = self.engine.store.load_state("demo")
        self.assertEqual([r["id"] for r in state["input_requests"]], ["IN-1", "IN-2"])

    def test_empty_questions_rejected(self):
        self.start()
        with self.assertRaises(EngineError):
            self.engine.request_structured_input("demo", reason="x", questions=[])

    def test_empty_reason_rejected(self):
        self.start()
        with self.assertRaises(EngineError):
            self.engine.request_structured_input("demo", reason="  ", questions=[question()])

    # --- valid answer resumes the run -----------------------------------------

    def test_valid_answer_resumes_run_with_provenance(self):
        self.start()
        self.engine.request_structured_input("demo", reason="need scope", questions=[question()])
        state = self.engine.answer_input(
            "demo", "IN-1", actor="reviewer", answers={"scope": {"selected": ["a"], "freeform": ""}}
        )
        self.assertEqual(state["run"]["state"], "running")
        self.assertIsNone(state["run"]["input_request_id"])
        record = state["input_requests"][0]
        self.assertEqual(record["status"], "answered")
        self.assertEqual(record["answered_by"], "reviewer")
        self.assertIsNotNone(record["answered_at"])
        self.assertEqual(record["answers"]["scope"]["selected"], ["a"])

    def test_multi_select_allows_multiple_options(self):
        self.start()
        self.engine.request_structured_input(
            "demo", reason="pick many",
            questions=[question("multi", qtype="multi_select", options=(("a", "A", True), ("b", "B", False), ("c", "C", False)))],
        )
        state = self.engine.answer_input(
            "demo", "IN-1", actor="user", answers={"multi": {"selected": ["a", "b"], "freeform": ""}}
        )
        self.assertEqual(state["run"]["state"], "running")

    def test_freeform_only_answer_satisfies_required_question(self):
        self.start()
        self.engine.request_structured_input("demo", reason="need scope", questions=[question()])
        state = self.engine.answer_input(
            "demo", "IN-1", actor="user", answers={"scope": {"selected": [], "freeform": "custom text"}}
        )
        self.assertEqual(state["run"]["state"], "running")

    # --- missing-required-answer rejected --------------------------------------

    def test_missing_required_answer_rejected(self):
        self.start()
        self.engine.request_structured_input("demo", reason="need scope", questions=[question()])
        with self.assertRaises(EngineError):
            self.engine.answer_input("demo", "IN-1", actor="user", answers={})
        state = self.engine.store.load_state("demo")
        self.assertEqual(state["run"]["state"], "needs_input")
        self.assertEqual(state["input_requests"][0]["status"], "pending")

    def test_optional_question_may_be_left_unanswered(self):
        self.start()
        self.engine.request_structured_input(
            "demo", reason="mixed",
            questions=[question("req", required=True), question("opt", required=False)],
        )
        state = self.engine.answer_input(
            "demo", "IN-1", actor="user", answers={"req": {"selected": ["a"], "freeform": ""}}
        )
        self.assertEqual(state["run"]["state"], "running")

    # --- invalid-option-id rejected ---------------------------------------------

    def test_unknown_option_id_rejected(self):
        self.start()
        self.engine.request_structured_input("demo", reason="need scope", questions=[question()])
        with self.assertRaises(EngineError):
            self.engine.answer_input(
                "demo", "IN-1", actor="user", answers={"scope": {"selected": ["zzz"], "freeform": ""}}
            )

    def test_single_select_rejects_multiple_selections(self):
        self.start()
        self.engine.request_structured_input("demo", reason="need scope", questions=[question()])
        with self.assertRaises(EngineError):
            self.engine.answer_input(
                "demo", "IN-1", actor="user", answers={"scope": {"selected": ["a", "b"], "freeform": ""}}
            )

    def test_freeform_rejected_when_not_allowed(self):
        self.start()
        self.engine.request_structured_input(
            "demo", reason="need scope", questions=[question(allow_freeform=False)]
        )
        with self.assertRaises(EngineError):
            self.engine.answer_input(
                "demo", "IN-1", actor="user", answers={"scope": {"selected": [], "freeform": "sneaky"}}
            )

    def test_unknown_request_id_rejected(self):
        self.start()
        with self.assertRaises(EngineError):
            self.engine.answer_input("demo", "IN-999", actor="user", answers={})

    def test_already_answered_request_rejected(self):
        self.start()
        self.engine.request_structured_input("demo", reason="need scope", questions=[question()])
        self.engine.answer_input("demo", "IN-1", actor="user", answers={"scope": {"selected": ["a"], "freeform": ""}})
        with self.assertRaises(EngineError):
            self.engine.answer_input("demo", "IN-1", actor="user", answers={"scope": {"selected": ["a"], "freeform": ""}})

    # --- stale plan_revision rejected --------------------------------------------

    def test_stale_plan_revision_rejected_and_named(self):
        self.start()
        self.engine.request_structured_input("demo", reason="need scope", questions=[question()])
        state = self.engine.store.load_state("demo")
        state["plan_revision"] += 1
        self.engine.store.save_state("demo", state)
        with self.assertRaises(EngineError) as ctx:
            self.engine.answer_input("demo", "IN-1", actor="user", answers={"scope": {"selected": ["a"], "freeform": ""}})
        self.assertIn("stale", str(ctx.exception))
        after = self.engine.store.load_state("demo")
        self.assertEqual(after["run"]["state"], "needs_input")
        self.assertEqual(after["input_requests"][0]["status"], "pending")

    def test_tampered_schema_hash_rejected(self):
        self.start()
        self.engine.request_structured_input("demo", reason="need scope", questions=[question()])
        state = self.engine.store.load_state("demo")
        state["input_requests"][0]["questions"][0]["prompt"] = "tampered?"
        self.engine.store.save_state("demo", state)
        with self.assertRaises(EngineError) as ctx:
            self.engine.answer_input("demo", "IN-1", actor="user", answers={"scope": {"selected": ["a"], "freeform": ""}})
        self.assertIn("schema_hash", str(ctx.exception))

    # --- cancel from needs_input still works -------------------------------------

    def test_cancel_from_needs_input_leaves_request_pending(self):
        self.start()
        self.engine.request_structured_input("demo", reason="need scope", questions=[question()])
        state = self.engine.cancel_run("demo")
        self.assertEqual(state["run"]["state"], "cancelled")
        self.assertEqual(state["input_requests"][0]["status"], "pending")

    def test_answer_after_cancel_rejected_without_partial_write(self):
        self.start()
        self.engine.request_structured_input("demo", reason="need scope", questions=[question()])
        self.engine.cancel_run("demo")
        before = self.engine.store.load_state("demo")
        with self.assertRaises(EngineError) as ctx:
            self.engine.answer_input("demo", "IN-1", actor="user", answers={"scope": {"selected": ["a"], "freeform": ""}})
        self.assertIn("cancelled -> running", str(ctx.exception))
        after = self.engine.store.load_state("demo")
        self.assertEqual(after, before)
        self.assertEqual(after["input_requests"][0]["status"], "pending")

    # --- backward compatibility: plain-reason path unchanged ----------------------

    def test_plain_request_input_and_resume_unchanged(self):
        self.start()
        state = self.engine.request_input("demo", reason="plain reason still works")
        self.assertEqual(state["run"]["state"], "needs_input")
        self.assertEqual(state["run"]["reason"], "plain reason still works")
        self.assertIsNone(state["run"].get("input_request_id"))
        self.assertEqual(state["input_requests"], [])
        state = self.engine.resume_run("demo")
        self.assertEqual(state["run"]["state"], "running")

    def test_new_state_has_empty_input_requests_and_null_run_request_id(self):
        state = self.engine.store.load_state("demo")
        self.assertEqual(state["input_requests"], [])
        self.assertIsNone(state["run"]["input_request_id"])

    # --- validate_state rejects a malformed input_request ---------------------

    def test_validate_state_rejects_malformed_input_request(self):
        from models import validate_state

        self.start()
        self.engine.request_structured_input("demo", reason="need scope", questions=[question()])
        state = self.engine.store.load_state("demo")
        del state["input_requests"][0]["schema_hash"]
        with self.assertRaises(ValueError):
            validate_state(state)


if __name__ == "__main__":
    unittest.main(verbosity=2)
