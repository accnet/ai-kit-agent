#!/usr/bin/env python3
"""Offline coverage, integrity, and reproducible compact-prompt fixtures."""

import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "harness"))
from prompt_evidence import (EvidenceError, compact_task, prepare_evidence,
                             evidence_payload, source_identity, verification_binding)
from policy import canonical_digest
from verification import run_verification


def fixture(root, shape="distinct"):
    (root / "check.py").write_text("print('verified offline')\n", encoding="utf-8")
    commands = [[sys.executable, "check.py", str(index)] for index in range(3)]
    if shape == "duplicates":
        commands = [commands[0]] * 3
    task = {"id": "T1", "title": "Verify bounded feature", "description": "Preserve acceptance",
            "owner": "backend", "scope": "M", "files": ["check.py"], "dependencies": [],
            "risks": [], "acceptance_criteria": ["criterion %d passes" % index for index in range(3)],
            "verification_commands": commands, "state": "review", "attempts": 0, "reviews": []}
    state = {"feature": "fixture", "goal": "Keep coverage", "plan_revision": 1, "tasks": [task]}
    if shape == "duplicates":
        task["verification_commands"] = commands[:2]
        task["verification_profiles"] = ["same"]
        (root / ".ai-kit").mkdir()
        (root / ".ai-kit/qa-profiles.json").write_text(json.dumps({"schema_version": 1,
            "profiles": {"same": {"command": commands[0], "cwd": ".", "timeout_seconds": 120,
                                  "evidence": {"feature": "fixture", "task": "T1", "artifacts": ["stdout"]}}}}))
    task["verification_evidence"] = run_verification(task, root, root)
    task["evidence"] = [{"criterion": criterion, "result": "pass", "detail": "verified offline",
                         "command": command} for criterion, command in
                        zip(task["acceptance_criteria"], commands)]
    if shape == "cycles":
        task["attempts"] = 2
        task["reviews"] = [{"provider": "scripted", "policy": "active-agent", "verdict": "revise",
                            "at": "2026-10-04T00:00:00Z", "summary": "inspect criterion",
                            "findings": [{"severity": "minor", "criterion": task["acceptance_criteria"][0],
                                          "detail": "retain review history"}]} for _ in range(3)]
    task["verification_binding"] = verification_binding(state, task, root)
    return state, task


def benchmark():
    from engine import HarnessEngine

    rows = []
    for shape in ("distinct", "duplicates", "cycles", "empty", "tiny-manual", "failed"):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state, task = fixture(root, shape)
            if shape in {"empty", "tiny-manual"}:
                task.pop("verification_evidence")
                task.pop("verification_binding")
                task["verification_commands"] = []
                task["evidence"] = [] if shape == "empty" else [
                    {"criterion": task["acceptance_criteria"][0], "result": "pass", "detail": "manual inspection"}]
            if shape == "failed":
                (root / "check.py").write_text("raise SystemExit(7)\n", encoding="utf-8")
                task["verification_evidence"] = run_verification(task, root, root)
                task["verification_binding"] = verification_binding(state, task, root)
                task["evidence"] = []
                task["last_failure"] = "verification failed; remaining checks not run"
            calls = []
            for phase in ("execution", "execution", "review"):
                package = prepare_evidence(state, task, root, root, review=phase == "review" and shape != "failed")
                builder = HarnessEngine._execution_prompt if phase == "execution" else HarnessEngine._review_prompt
                marker = "Task: " if phase == "execution" else "Task and evidence: "
                compact = builder(state, task, "fixed fixture context", evidence_view=package.view)
                old_task = copy.deepcopy(task)
                old_task.pop("verification_binding", None)  # Added by Fix 1, absent from baseline.
                baseline = compact.rsplit(marker, 1)[0] + marker + json.dumps(old_task, ensure_ascii=False, indent=2)
                package.validate()
                full_evidence = json.dumps(evidence_payload(old_task), ensure_ascii=False, indent=2)
                projected = json.dumps({"evidence_view": package.view["evidence_view"],
                                        "evidence": package.view.get("evidence", [])},
                                       ensure_ascii=False, separators=(",", ":"))
                calls.append({"phase": phase, "baseline_bytes": len(baseline.encode()),
                              "compact_bytes": len(compact.encode()), "baseline_chars": len(baseline),
                              "compact_chars": len(compact), "baseline_evidence_bytes": len(full_evidence.encode()),
                              "compact_evidence_bytes": len(projected.encode()),
                              "package_bytes": sum(path.stat().st_size for path in package.roots[0][1].iterdir())
                              if package.roots else 0})
            spec = {"shape": shape, "criteria": 3, "calls": ["execution", "execution", "review"],
                    "declared_checks": len(task["verification_commands"]) + len(task.get("verification_profiles", [])),
                    "history_records": len(task["reviews"])}
            rows.append({"shape": shape, "fixture_spec": spec, "fixture_digest": canonical_digest(spec),
                         "calls": calls,
                         "baseline_bytes": sum(item["baseline_bytes"] for item in calls),
                         "compact_bytes": sum(item["compact_bytes"] for item in calls),
                         "baseline_repeated_evidence_bytes": sum(item["baseline_evidence_bytes"] for item in calls[1:]),
                         "compact_repeated_evidence_bytes": sum(item["compact_evidence_bytes"] for item in calls[1:])})
    return {"baseline_commit": "0348762fcde646f1ca7f3e3dbb8c408b79716535",
            "baseline_method": "unchanged prefix/schema/context plus original indent=2 full task; excludes new binding",
            "repetition_method": "evidence payload bytes re-sent on the second and third calls of fixed-evidence fixtures",
            "runtime": sys.version, "tokens": None, "quota": None, "cache_hits": None, "rows": rows}


class PromptEvidenceCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_fresh_view_preserves_scope_criteria_unknown_fields_and_manual_coverage(self):
        state, task = fixture(self.root)
        task["new_owner_requirement"] = {"must": "preserve me"}
        task["contract_evidence"] = {"api@1": ["contract remains compatible"]}
        task["evidence"].append({"criterion": "contract remains compatible", "result": "pass",
                                 "detail": "manual schema inspection"})
        task["verification_binding"] = verification_binding(state, task, self.root)
        before = copy.deepcopy(task)
        package = prepare_evidence(state, task, self.root, self.root, review=True)
        view = package.view
        self.assertEqual(task, before)
        for key in ("files", "acceptance_criteria", "verification_commands", "new_owner_requirement"):
            self.assertEqual(view[key], task[key])
        self.assertEqual(view["evidence_view"]["coverage"][-1]["reported"][0]["linkage"], "manual")
        self.assertEqual(view["evidence_view"]["coverage"][0]["reported"][0]["checks"], ["V1"])
        self.assertEqual(view["evidence_view"]["freshness"], "current")
        package.validate()

    def test_duplicate_declarations_share_metadata_and_ambiguous_command_is_unverified(self):
        state, task = fixture(self.root, "duplicates")
        view = prepare_evidence(state, task, self.root, self.root, review=True).view["evidence_view"]
        self.assertEqual(len(view["checks"]), 1)
        self.assertEqual(len(view["declarations"]), 3)
        self.assertEqual([item["check"] for item in view["declarations"]], ["V1"] * 3)
        task["verification_evidence"][1] = dict(task["verification_evidence"][1], cwd="other")
        projected = compact_task(task)["evidence_view"]
        self.assertEqual(projected["coverage"][0]["reported"][0]["linkage"], "unverified")

    def test_exact_criterion_matching_never_infers_coverage_from_suite_pass(self):
        _, task = fixture(self.root)
        task["evidence"][0]["criterion"] = "different criterion"
        coverage = compact_task(task)["evidence_view"]["coverage"]
        self.assertEqual(coverage[0]["reported"], [{"result": "unavailable"}])

    def test_requirement_literals_and_digest_references_survive_projection(self):
        state, task = fixture(self.root)
        task["acceptance_criteria"][0] = "token=example must be rejected"
        task["description"] = "Check token=example input literally"
        task["verification_binding"] = verification_binding(state, task, self.root)
        package = prepare_evidence(state, task, self.root, self.root, review=True)
        self.assertEqual(package.view["acceptance_criteria"], task["acceptance_criteria"])
        self.assertEqual(package.view["description"], task["description"])
        reference = package.view["evidence_view"]["package"]
        manifest_path = self.root / reference["manifest"]
        manifest = json.loads(manifest_path.read_text())
        full = json.loads((manifest_path.parent / "task.json").read_text())
        self.assertEqual(full["acceptance_criteria"], task["acceptance_criteria"])
        self.assertEqual(reference["source"], manifest["source"])
        self.assertEqual(reference["evidence_digest"], manifest["evidence_digest"])
        self.assertEqual(package.view["evidence_view"]["checks"][0]["digest"],
                         task["verification_evidence"][0]["check_digest"])

    def test_failures_timeout_not_run_and_reviews_survive_retries(self):
        state, task = fixture(self.root, "cycles")
        task["verification_evidence"] = [{"command": task["verification_commands"][0],
            "passed": False, "failure_kind": "timeout", "timed_out": True,
            "failure_excerpt": "still failing token=fixture-secret"}]
        task["last_failure"] = "unresolved timeout"
        for attempt in (1, 2):
            task["attempts"] = attempt
            view = compact_task(task)["evidence_view"]
            self.assertEqual(view["checks"][0]["failure_kind"], "timeout")
            self.assertEqual(sum(item.get("status") == "not-run" for item in view["declarations"]), 2)
            self.assertEqual(len(view["reviews"]), 3)
            self.assertNotIn("fixture-secret", json.dumps(view))

    def test_empty_and_legacy_evidence_are_explicit(self):
        state, task = fixture(self.root)
        task["verification_evidence"] = []
        view = compact_task(task)["evidence_view"]
        self.assertEqual(view["freshness"], "unavailable")
        task.pop("verification_binding")
        view = compact_task(task)["evidence_view"]
        self.assertEqual(view["mode"], "inline")
        self.assertTrue(view["not_run"])
        task["verification_evidence"] = [{"command": task["verification_commands"][0], "passed": True}]
        package = prepare_evidence(state, task, self.root, self.root)
        self.assertEqual(package.view["evidence_view"]["checks"][0]["attribution"], "unavailable")
        with self.assertRaisesRegex(EvidenceError, "stale or unavailable"):
            prepare_evidence(state, task, self.root, self.root, review=True)

    def test_manual_detail_is_bounded_redacted_and_fully_inspectable(self):
        state, task = fixture(self.root)
        detail = "manual assertion " * 400 + " token=fixture-secret"
        task["evidence"][0] = {"criterion": task["acceptance_criteria"][0], "result": "pass",
                                "detail": detail, "stdout": "RAW-LOG-MARKER"}
        package = prepare_evidence(state, task, self.root, self.root, review=True)
        prompt = json.dumps(package.view)
        self.assertNotIn("fixture-secret", prompt)
        self.assertNotIn("RAW-LOG-MARKER", prompt)
        reported = package.view["evidence_view"]["coverage"][0]["reported"][0]
        self.assertLessEqual(len(reported["detail"].encode()), 2048)
        manifest_path = self.root / package.view["evidence_view"]["package"]["manifest"]
        full = json.loads((manifest_path.parent / "task.json").read_text())
        self.assertGreater(len(full["evidence"][0]["detail"]), len(reported["detail"]))
        self.assertNotIn("fixture-secret", json.dumps(full))

    def test_corrupt_missing_escaping_and_symlinked_artifacts_block(self):
        for mode in ("corrupt", "missing", "escaping", "symlink", "manifest"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                state, task = fixture(root)
                record = task["verification_evidence"][0]
                log = root / record["artifacts"]["stdout"]["path"]
                if mode == "corrupt":
                    log.write_bytes(b"changed")
                elif mode == "missing":
                    log.unlink()
                elif mode == "escaping":
                    record["artifact_manifest"] = "../outside.json"
                elif mode == "symlink":
                    target = root / "outside.log"
                    target.write_bytes(log.read_bytes())
                    log.unlink()
                    try:
                        log.symlink_to(target)
                    except OSError:
                        self.skipTest("symlink permission unavailable")
                else:
                    (root / record["artifact_manifest"]).write_text("{}")
                with self.assertRaises(EvidenceError):
                    prepare_evidence(state, task, root, root)

    def test_changed_source_plan_or_canonical_record_blocks_review_but_retry_is_historical(self):
        state, task = fixture(self.root)
        original = copy.deepcopy(task["verification_binding"])
        for change in ("source", "plan", "record"):
            with self.subTest(change=change):
                task["verification_binding"] = dict(original)
                task["verification_binding"][change if change != "record" else "evidence"] = "changed"
                with self.assertRaisesRegex(EvidenceError, "stale or unavailable"):
                    prepare_evidence(state, task, self.root, self.root, review=True)
                package = prepare_evidence(state, task, self.root, self.root)
                self.assertEqual(package.view["evidence_view"]["freshness"], "historical")
        task["verification_binding"] = original
        (self.root / "check.py").write_text("print('changed source')")
        with self.assertRaises(EvidenceError):
            prepare_evidence(state, task, self.root, self.root, review=True)

    def test_coordinator_state_and_staging_do_not_change_source_identity(self):
        state, task = fixture(self.root)
        before = source_identity(self.root)
        (self.root / ".project").mkdir()
        (self.root / ".project/state.json").write_text("changed coordinator state")
        self.assertEqual(before, source_identity(self.root))
        prepare_evidence(state, task, self.root, self.root, review=True).validate()

    def test_isolated_reader_reconstructs_all_artifacts_and_mutation_is_detected(self):
        state, task = fixture(self.root)
        with tempfile.TemporaryDirectory() as directory:
            isolated = Path(directory)
            (isolated / "check.py").write_bytes((self.root / "check.py").read_bytes())
            package = prepare_evidence(state, task, self.root, isolated, review=True)
            reference = package.view["evidence_view"]["package"]
            path = isolated / reference["manifest"]
            manifest = json.loads(path.read_text())
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), reference["sha256"])
            for name, info in manifest["files"].items():
                data = (path.parent / name).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), info["sha256"])
                self.assertEqual(len(data), info["bytes"])
            package.validate()
            (path.parent / "injected.txt").write_text("unexpected")
            with self.assertRaisesRegex(EvidenceError, "mutated"):
                package.validate()
            (path.parent / "injected.txt").unlink()
            package.cleanup_projection()
            self.assertFalse(path.exists())
        self.assertTrue(package.roots[0][1].exists())

    def test_guard_rejects_canonical_artifact_mutation_and_package_deletion(self):
        state, task = fixture(self.root)
        package = prepare_evidence(state, task, self.root, self.root, review=True)
        log = self.root / task["verification_evidence"][0]["artifacts"]["stdout"]["path"]
        log.write_bytes(b"tampered")
        with self.assertRaisesRegex(EvidenceError, "changed"):
            package.validate()
        manifest = package.roots[0][1] / "manifest.json"
        manifest.unlink()
        with self.assertRaisesRegex(EvidenceError, "mutated"):
            package.validate()

    def test_changed_manifest_metadata_blocks_retry_even_when_results_match(self):
        state, task = fixture(self.root)
        manifest = self.root / task["verification_evidence"][0]["artifact_manifest"]
        data = json.loads(manifest.read_text())
        data["metrics"]["executed_checks"] = 999
        manifest.write_text(json.dumps(data))
        with self.assertRaisesRegex(EvidenceError, "manifest hash changed"):
            prepare_evidence(state, task, self.root, self.root)

    def test_previous_attempt_or_run_is_historical_and_cannot_certify_review(self):
        state, task = fixture(self.root)
        view = prepare_evidence(state, task, self.root, self.root).view
        self.assertEqual(view["evidence_view"]["freshness"], "historical")
        task["attempts"] += 1
        with self.assertRaisesRegex(EvidenceError, "stale or unavailable"):
            prepare_evidence(state, task, self.root, self.root, review=True)
        task["attempts"] -= 1
        state["run"] = {"id": "new-run"}
        with self.assertRaisesRegex(EvidenceError, "stale or unavailable"):
            prepare_evidence(state, task, self.root, self.root, review=True)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX special-file check")
    def test_guard_rejects_special_files_without_blocking_on_read(self):
        state, task = fixture(self.root)
        package = prepare_evidence(state, task, self.root, self.root, review=True)
        os.mkfifo(package.roots[0][1] / "injected-fifo")
        with self.assertRaisesRegex(EvidenceError, "special file"):
            package.validate()

    def test_frozen_benchmarks_reduce_complete_prompts_and_repeated_evidence(self):
        result = benchmark()
        for row in result["rows"]:
            with self.subTest(shape=row["shape"]):
                self.assertLess(row["compact_bytes"], row["baseline_bytes"])
                self.assertLess(row["compact_repeated_evidence_bytes"], row["baseline_repeated_evidence_bytes"])
                for call in row["calls"]:
                    self.assertLess(call["compact_bytes"], call["baseline_bytes"])

    def test_inline_views_are_bounded_self_contained_and_need_no_artifacts(self):
        state, task = fixture(self.root)
        task["verification_commands"] = []
        task["verification_evidence"] = []
        task.pop("verification_binding")
        task["evidence"] = [{"criterion": task["acceptance_criteria"][0], "result": "pass",
                              "detail": "manual inspection token=fixture-secret", "stdout": "RAW-LOG"}]
        package = prepare_evidence(state, task, self.root, self.root, review=True)
        self.assertEqual(package.roots, [])
        self.assertEqual(package.view["evidence_view"]["mode"], "inline")
        self.assertIsNone(package.view["evidence_view"]["freshness"])
        self.assertEqual(package.view["acceptance_criteria"], task["acceptance_criteria"])
        self.assertNotIn("fixture-secret", json.dumps(package.view))
        self.assertNotIn("RAW-LOG", json.dumps(package.view))
        package.validate()

    def test_coverage_references_reconstruct_exact_task_and_contract_criteria(self):
        state, task = fixture(self.root)
        task["contract_evidence"] = {"api@1": ["contract remains compatible"]}
        task["verification_binding"] = verification_binding(state, task, self.root)
        view = prepare_evidence(state, task, self.root, self.root, review=True).view
        reconstructed = []
        for item in view["evidence_view"]["coverage"]:
            value = view
            reference = item["criterion_ref"]
            for part in ["acceptance_criteria", reference] if isinstance(reference, int) else reference:
                value = value[part]
            reconstructed.append(value)
            self.assertNotIn("criterion", item)
        self.assertEqual(reconstructed, task["acceptance_criteria"] + ["contract remains compatible"])


if __name__ == "__main__":
    if "--benchmark" in sys.argv:
        print(json.dumps(benchmark(), indent=2))
    else:
        unittest.main()
