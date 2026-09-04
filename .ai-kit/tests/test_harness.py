#!/usr/bin/env python3
"""Offline integration and failure-path tests for the v0.7 harness."""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".ai-kit" / "harness"))

from cli import (  # noqa: E402
    ConfiguredProvider,
    load_config,
    main as cli_main,
    parser as cli_parser,
    review_provider_from_args,
    status_view,
    task_provider_from_args,
)
from engine import EngineError, HarnessEngine  # noqa: E402
from memory import MemoryStore  # noqa: E402
from models import validate_state  # noqa: E402
from policy import (  # noqa: E402
    ApprovalRequired,
    ContractApprovalRequired,
    ContractStale,
    PlanApprovalRequired,
    PolicyError,
    changed_files_in_scope,
    normalize_plan,
    plan_revision_digest,
    task_action_digest,
)
from projection import render_plan, render_tasks  # noqa: E402
from providers import (  # noqa: E402
    ClaudeProvider,
    CodexProvider,
    GrokProvider,
    ProviderError,
    ProviderRequest,
    ScriptedProvider,
)
from schemas import EXECUTION_SCHEMA, PLAN_SCHEMA, REVIEW_SCHEMA  # noqa: E402
from store import LockError, RepositoryStore, StoreError  # noqa: E402
from worktrees import GitWorkspaceManager, WorkspaceError, WorkspaceRecord  # noqa: E402


def task(
    number: int,
    *,
    dependencies=None,
    risks=None,
    files=None,
    criterion=None,
    owner="backend",
    **extra,
):
    result = {
        "id": "T%d" % number,
        "title": "Build task %d" % number,
        "description": "Implement bounded task %d" % number,
        "dependencies": dependencies or [],
        "acceptance_criteria": [criterion or "criterion %d passes" % number],
        "owner": owner,
        "scope": "S",
        "files": files or ["src/%d.py" % number],
        "risks": risks or [],
        "review_required": True,
    }
    result.update(extra)
    return result


def multi_service_plan(*tasks):
    reference = "checkout.api@1.0.0"
    return {
        "summary": "versioned checkout contract",
        "program_id": "commerce",
        "workstream_id": "checkout",
        "services": [
            {
                "id": "order-service",
                "domain": "orders",
                "paths": ["services/order"],
                "owns_data": ["order"],
                "exposes": [reference],
                "consumes": [],
                "dependencies": [],
                "forbidden_dependencies": [],
            },
            {
                "id": "checkout-bff",
                "domain": "checkout",
                "paths": ["services/checkout-bff"],
                "owns_data": [],
                "exposes": [],
                "consumes": [reference],
                "dependencies": ["order-service"],
                "forbidden_dependencies": [],
            },
        ],
        "contracts": [
            {
                "id": "checkout.api",
                "kind": "api",
                "version": "1.0.0",
                "owner": "order-service",
                "status": "draft",
                "source": ".contracts/checkout.yaml",
                "source_hash": "pending",
                "producers": ["order-service"],
                "consumers": ["checkout-bff"],
                "compatibility": "backward",
                "change_type": "additive",
                "invariants": ["create order is idempotent"],
                "verification": ["provider and consumer contract tests pass"],
                "rollout": "deploy provider before consumer",
                "rollback": "continue serving version 1",
            }
        ],
        "tasks": list(tasks),
    }


def named_provider(responses, name):
    provider = ScriptedProvider(responses)
    provider.name = name
    return provider


def quality_policy():
    return {
        "providers": {
            "codex-cli": {
                "provider": "codex",
                "model": "gpt-5.6-sol",
            },
            "claude-cli": {
                "provider": "claude",
                "model": "claude-sonnet-5",
            },
        },
        "qa": {"enabled": False, "provider": "codex-cli"},
        "review": {"enabled": False, "provider": "claude-cli"},
    }


class HarnessCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / ".ai-kit" / "knowledge").mkdir(parents=True)
        (self.root / "features" / "demo").mkdir(parents=True)
        (self.root / "AGENTS.md").write_text("# fixture rules\n", encoding="utf-8")
        (self.root / "features" / "demo" / "brief.md").write_text(
            "# fixture intent\nBuild a controlled loop.\n", encoding="utf-8"
        )
        (self.root / ".ai-kit" / "knowledge" / "conventions.md").write_text(
            "Use standard library.\n", encoding="utf-8"
        )
        (self.root / ".contracts").mkdir()
        (self.root / ".contracts" / "checkout.yaml").write_text(
            "openapi: 3.1.0\ninfo:\n  title: Checkout\n  version: 1.0.0\n",
            encoding="utf-8",
        )
        self.store = RepositoryStore(self.root)
        self.engine = HarnessEngine(self.store, context_budget=1200)

    def tearDown(self):
        self.temp.cleanup()

    def initialize(self):
        return self.engine.initialize(
            "demo",
            "Build controlled loop",
            constraints=["offline tests"],
            verification=["all checks pass"],
        )

    def execute_success(self, task_id="T1", criterion="criterion 1 passes", path="src/1.py"):
        result = {
            "outcome": "success",
            "summary": "implementation verified",
            "evidence": [{"criterion": criterion, "result": "pass", "detail": "offline test passed"}],
            "changed_files": [path],
            "memory": [{"kind": "episodic", "content": "pattern verified", "tags": [task_id]}],
        }
        return self.engine.execute_with_provider("demo", named_provider([result], "codex"), task_id=task_id)

    def approve_review(self, task_id="T1", criterion="criterion 1 passes"):
        review = {
            "verdict": "approve",
            "summary": "evidence accepted",
            "findings": [],
            "evidence_checked": [criterion],
        }
        return self.engine.review_with_provider("demo", task_id, named_provider([review], "claude"))

    def test_success_with_no_changed_files_is_rejected(self):
        self.initialize()
        self.engine.apply_plan(
            "demo",
            {"summary": "empty mutation", "tasks": [task(1)]},
        )
        result = {
            "outcome": "success",
            "summary": "did nothing",
            "evidence": [
                {"criterion": "criterion 1 passes", "result": "pass", "detail": "ok"}
            ],
            "changed_files": [],
            "memory": [],
        }
        with self.assertRaises(PolicyError):
            self.engine.execute_with_provider(
                "demo", named_provider([result], "codex"), task_id="T1"
            )
        state = self.store.load_state("demo")
        self.assertEqual(state["tasks"][0]["state"], "ready")
        self.assertEqual(state["tasks"][0]["attempts"], 1)

    def test_full_lifecycle_approval_resume_events_and_projections(self):
        self.initialize()
        plan = {
            "summary": "safe then approved external work",
            "tasks": [task(1), task(2, dependencies=["T1"], risks=["external-write"])],
        }
        with patch("providers.subprocess.run", side_effect=AssertionError("external provider called")):
            self.engine.apply_plan("demo", plan)
            self.assertEqual(self.engine.next_task("demo")["id"], "T1")
            self.assertEqual(self.execute_success()["tasks"][0]["state"], "review")
            state = self.approve_review()
        self.assertEqual(state["tasks"][0]["state"], "complete")
        with self.assertRaises(ApprovalRequired):
            self.engine.next_task("demo")
        self.engine.approve_task("demo", "T2", approved_by="fixture-user")
        resumed = HarnessEngine(RepositoryStore(self.root), context_budget=1200)
        self.assertEqual(resumed.next_task("demo")["id"], "T2")
        state = resumed.execute_with_provider(
            "demo",
            named_provider(
                [
                    {
                        "outcome": "success",
                        "summary": "external work verified",
                        "evidence": [
                            {
                                "criterion": "criterion 2 passes",
                                "result": "pass",
                                "detail": "offline test passed",
                            }
                        ],
                        "changed_files": ["src/2.py"],
                        "memory": [],
                    }
                ],
                "codex",
            ),
            task_id="T2",
        )
        self.assertEqual(state["tasks"][1]["state"], "review")
        state = resumed.review_with_provider(
            "demo",
            "T2",
            named_provider(
                [
                    {
                        "verdict": "approve",
                        "summary": "final review passed",
                        "findings": [],
                        "evidence_checked": ["criterion 2 passes"],
                    }
                ],
                "claude",
            ),
        )
        self.assertEqual(state["status"], "complete")
        self.assertEqual(render_plan(state), render_plan(self.store.load_state("demo")))
        self.assertEqual(render_tasks(state), (self.root / ".project/demo/tasks.md").read_text())
        events = self.store.read_records("demo", "events.jsonl")
        self.assertIn("task_approved", [event["event"] for event in events])
        self.assertEqual([event["event"] for event in events][-1], "task_completed")

    def test_replan_and_resume(self):
        self.initialize()
        self.engine.apply_plan("demo", {"summary": "initial plan", "tasks": [task(1)]})
        result = {
            "outcome": "needs_replan",
            "summary": "task needs decomposition",
            "evidence": [],
            "changed_files": [],
            "memory": [],
        }
        state = self.engine.execute_with_provider("demo", ScriptedProvider([result]))
        self.assertEqual(state["status"], "needs_replan")
        state = self.engine.apply_plan(
            "demo", {"summary": "decomposed plan", "tasks": [task(2)]}, replan=True
        )
        self.assertEqual(state["plan_revision"], 2)
        self.assertEqual(HarnessEngine(RepositoryStore(self.root)).next_task("demo")["id"], "T2")

    def test_feature_dependency_blocks_canonical_readiness_until_target_completes(self):
        self.initialize()
        target = self.root / ".project" / "baseline"
        target.mkdir(parents=True)
        (target / "state.json").write_text(
            json.dumps({"feature": "baseline", "tasks": [{"id": "T9", "state": "ready"}]}),
            encoding="utf-8",
        )
        state = self.engine.apply_plan(
            "demo",
            {"summary": "wait for baseline", "feature_dependencies": [{"feature": "baseline", "task": "T9"}], "tasks": [task(1)]},
        )
        self.assertEqual(state["tasks"][0]["state"], "proposed")
        self.assertIn("unfinished canonical", state["tasks"][0]["feature_dependency_block"])
        self.assertIsNone(self.engine.next_task("demo"))
        (target / "state.json").write_text(
            json.dumps({"feature": "baseline", "tasks": [{"id": "T9", "state": "complete"}]}),
            encoding="utf-8",
        )
        self.assertEqual(self.engine.next_task("demo")["id"], "T1")

    def test_optional_v016_fields_preserve_legacy_digests_when_empty(self):
        self.initialize()
        state = self.engine.apply_plan("demo", {"summary": "legacy digest", "tasks": [task(1)]})
        baseline_plan = plan_revision_digest(state)
        baseline_task = task_action_digest(state, state["tasks"][0])
        state["feature_dependencies"] = []
        state["tasks"][0]["verification_profiles"] = []
        self.assertEqual(plan_revision_digest(state), baseline_plan)
        self.assertEqual(task_action_digest(state, state["tasks"][0]), baseline_task)
        state["feature_dependencies"] = [{"feature": "baseline", "task": "T1"}]
        state["tasks"][0]["verification_profiles"] = ["ai-kit"]
        self.assertNotEqual(plan_revision_digest(state), baseline_plan)
        self.assertNotEqual(task_action_digest(state, state["tasks"][0]), baseline_task)

    def test_requirement_traceability_rejects_gaps_and_unknown_refs(self):
        self.engine.initialize(
            "demo",
            "Trace every requirement",
            requirements=[
                {"id": "R1", "text": "Persist lifecycle state"},
                {"id": "R2", "text": "Run independent verification"},
            ],
        )
        with self.assertRaisesRegex(PolicyError, "leaves requirements uncovered: R2"):
            self.engine.apply_plan(
                "demo",
                {
                    "summary": "incomplete coverage",
                    "tasks": [task(1, requirement_refs=["R1"])],
                },
            )
        with self.assertRaisesRegex(PolicyError, "references unknown requirements: R3"):
            self.engine.apply_plan(
                "demo",
                {
                    "summary": "unknown coverage",
                    "tasks": [task(1, requirement_refs=["R1", "R2", "R3"])],
                },
            )
        state = self.engine.apply_plan(
            "demo",
            {
                "summary": "complete coverage",
                "tasks": [task(1, requirement_refs=["R1", "R2"])],
            },
        )
        self.assertEqual(state["tasks"][0]["requirement_refs"], ["R1", "R2"])
        self.assertIn("R1 [covered]", render_plan(state))
        self.assertIn("Requirements: R1, R2", render_tasks(state))

    def test_approval_digest_invalidates_changed_risky_action(self):
        self.initialize()
        state = self.engine.apply_plan(
            "demo",
            {
                "summary": "bounded external action",
                "tasks": [task(1, risks=["external-write"])],
            },
        )
        self.engine.approve_task("demo", "T1", approved_by="fixture-user")
        approved = self.store.load_state("demo")
        self.assertTrue(approved["approvals"][-1]["action_digest"].startswith("sha256:"))
        self.assertEqual(self.engine.next_task("demo")["id"], "T1")

        approved["tasks"][0]["environments"] = ["production"]
        self.store.save_state("demo", approved)
        with self.assertRaises(ApprovalRequired):
            self.engine.next_task("demo")

    def test_independent_verification_records_pass_and_fails_closed(self):
        (self.root / "verify-pass.py").write_text("print('verified')\n", encoding="utf-8")
        self.initialize()
        self.engine.apply_plan(
            "demo",
            {
                "summary": "verify independently",
                "tasks": [
                    task(
                        1,
                        verification_commands=[[sys.executable, "verify-pass.py"]],
                    )
                ],
            },
        )
        state = self.execute_success()
        evidence = state["tasks"][0]["verification_evidence"][0]
        self.assertEqual(evidence["exit_code"], 0)
        self.assertTrue(evidence["passed"])
        self.assertIsInstance(evidence["duration_ms"], int)
        self.assertTrue(evidence["output_digest"].startswith("sha256:"))
        self.assertEqual(evidence["command"][0], sys.executable)
        self.assertNotIn("stdout", evidence)
        self.assertNotIn("stderr", evidence)
        self.assertGreater(evidence["output_bytes"], 0)

    def test_independent_verification_failure_and_timeout_are_durable(self):
        (self.root / "verify-fail.py").write_text(
            "raise SystemExit(7)\n", encoding="utf-8"
        )
        self.initialize()
        self.engine.apply_plan(
            "demo",
            {
                "summary": "reject failed verification",
                "tasks": [
                    task(
                        1,
                        verification_commands=[[sys.executable, "verify-fail.py"]],
                    )
                ],
            },
        )
        with self.assertRaisesRegex(PolicyError, "independent verification failed"):
            self.execute_success()
        failed = self.store.load_state("demo")["tasks"][0]
        self.assertEqual(failed["verification_evidence"][0]["exit_code"], 7)
        self.assertEqual(failed["state"], "ready")

        with patch(
            "engine.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=[sys.executable], timeout=120),
        ):
            with self.assertRaisesRegex(PolicyError, "independent verification failed"):
                self.execute_success()
        timed_out = self.store.load_state("demo")["tasks"][0]
        self.assertTrue(timed_out["verification_evidence"][0]["timed_out"])
        self.assertIsNone(timed_out["verification_evidence"][0]["exit_code"])

    def test_verification_command_policy_rejects_inline_and_unknown_execution(self):
        rejected = (
            ["bash", "-c", "pytest"],
            [sys.executable, "-c", "print('unsafe')"],
            ["/tmp/python", "tests/check.py"],
            ["/tmp/pytest", "-q"],
            ["curl", "https://example.test"],
            ["npm", "publish"],
        )
        for command in rejected:
            with self.subTest(command=command):
                with self.assertRaises(PolicyError):
                    normalize_plan(
                        {
                            "summary": "reject unsafe verifier",
                            "tasks": [task(1, verification_commands=[command])],
                        }
                    )
        for command in (
            [sys.executable, "tests/check.py"],
            ["bash", ".ai-kit/tests/run.sh"],
            ["pytest", "-q"],
            ["npm", "run", "typecheck"],
        ):
            with self.subTest(command=command):
                normalized = normalize_plan(
                    {
                        "summary": "accept bounded verifier",
                        "tasks": [task(1, verification_commands=[command])],
                    }
                )
                self.assertEqual(normalized[0]["verification_commands"], [command])

    def test_verification_interpreter_rejects_symlink_before_subprocess(self):
        with tempfile.TemporaryDirectory() as external_directory:
            external = Path(external_directory) / "outside.py"
            external.write_text("print('outside')\n", encoding="utf-8")
            (self.root / "verify-link.py").symlink_to(external)
            self.initialize()
            self.engine.apply_plan(
                "demo",
                {
                    "summary": "reject linked verifier",
                    "tasks": [
                        task(
                            1,
                            verification_commands=[[sys.executable, "verify-link.py"]],
                        )
                    ],
                },
            )
            with patch(
                "engine.subprocess.run",
                side_effect=AssertionError("verification subprocess executed"),
            ):
                with self.assertRaisesRegex(PolicyError, "independent verification failed"):
                    self.execute_success()
            evidence = self.store.load_state("demo")["tasks"][0][
                "verification_evidence"
            ][0]
            self.assertFalse(evidence["passed"])
            self.assertIn("traverses a symlink", evidence["policy_error"])

    def test_durable_run_pause_input_resume_and_cancel(self):
        self.initialize()
        self.engine.apply_plan("demo", {"summary": "durable run", "tasks": [task(1)]})
        started = self.engine.start_run("demo", actor="fixture-user")
        run_id = started["run"]["id"]
        self.assertEqual(started["run"]["state"], "running")

        paused = self.engine.pause_run("demo", reason="operator check")
        self.assertEqual(paused["run"]["state"], "paused")
        resumed_engine = HarnessEngine(RepositoryStore(self.root), context_budget=1200)
        self.assertEqual(resumed_engine.resume_run("demo")["run"]["id"], run_id)
        waiting = resumed_engine.request_input("demo", reason="choose rollout")
        self.assertEqual(waiting["run"]["state"], "needs_input")
        self.assertEqual(waiting["run"]["reason"], "choose rollout")
        resumed_engine.resume_run("demo")
        resumed_engine.pause_run("demo")
        cancelled = resumed_engine.cancel_run("demo", reason="operator stopped")
        self.assertEqual(cancelled["run"]["state"], "cancelled")
        with self.assertRaisesRegex(EngineError, "cancelled -> running"):
            resumed_engine.resume_run("demo")

    def test_lifecycle_blocks_steps_allows_contract_approval_and_direct_cancel(self):
        self.initialize()
        reference = "checkout.api@1.0.0"
        self.engine.apply_plan(
            "demo", multi_service_plan(task(1, owner="qa", files=["tests/smoke.py"]))
        )

        class NeverInvoke:
            name = "codex"

            def invoke(inner_self, request):
                del inner_self, request
                raise AssertionError("provider invoked while run was blocked")

        self.engine.start_run("demo")
        self.engine.pause_run("demo")
        with self.assertRaisesRegex(EngineError, "run is paused"):
            self.engine.execute_with_provider("demo", NeverInvoke(), task_id="T1")

        self.engine.resume_run("demo")
        self.engine.request_input("demo", reason="approve contract")
        approved = self.engine.approve_contract(
            "demo", reference, approved_by="fixture-user"
        )
        self.assertEqual(approved["contracts"][0]["status"], "approved")
        with self.assertRaisesRegex(EngineError, "run is needs_input"):
            self.engine.execute_with_provider("demo", NeverInvoke(), task_id="T1")

        self.engine.resume_run("demo")
        cancelled = self.engine.cancel_run("demo", reason="direct stop")
        self.assertEqual(cancelled["run"]["state"], "cancelled")
        with self.assertRaisesRegex(EngineError, "run is cancelled"):
            self.engine.execute_with_provider("demo", NeverInvoke(), task_id="T1")

    def test_plan_policy_rejects_invalid_graphs_and_scopes(self):
        valid = {"summary": "valid plan", "tasks": [task(1)]}
        self.assertEqual(normalize_plan(valid)[0]["state"], "ready")
        cases = [
            {"summary": "duplicate ids", "tasks": [task(1), task(1)]},
            {"summary": "unknown dependency", "tasks": [task(1, dependencies=["T9"])]},
            {"summary": "cycle graph", "tasks": [task(1, dependencies=["T2"]), task(2, dependencies=["T1"])]},
            {"summary": "scope escape", "tasks": [task(1, files=["../secret"])]},
            {"summary": "intent write", "tasks": [task(1, files=["features/demo/brief.md"])]},
            {"summary": "control write", "tasks": [task(1, files=[".project/demo/state.json"])]},
        ]
        missing_acceptance = task(1)
        missing_acceptance["acceptance_criteria"] = []
        cases.append({"summary": "no acceptance", "tasks": [missing_acceptance]})
        for candidate in cases:
            with self.subTest(candidate=candidate["summary"]):
                with self.assertRaises(PolicyError):
                    normalize_plan(candidate)
        self.assertTrue(changed_files_in_scope({"files": ["src/*.py"]}, ["src/one.py"]))
        self.assertFalse(changed_files_in_scope({"files": ["src/*.py"]}, ["src/deep/one.py"]))

    def test_multi_service_contract_approval_unblocks_and_projects(self):
        self.initialize()
        reference = "checkout.api@1.0.0"
        plan = multi_service_plan(
            task(
                1,
                files=["services/order/app.py"],
                service="order-service",
                layer="api",
                contract_reads=[reference],
                produces=[reference],
                rollback="serve previous handler",
            ),
            task(
                2,
                files=["services/checkout-bff/client.py"],
                service="checkout-bff",
                layer="backend",
                contract_reads=[reference],
                integration_tests=["checkout-order-consumer"],
            ),
        )
        state = self.engine.apply_plan("demo", plan)
        validate_state(state)
        self.assertEqual(state["contracts"][0]["status"], "draft")
        with self.assertRaises(ContractApprovalRequired):
            self.engine.next_task("demo")
        state = self.engine.approve_contract(
            "demo", reference, approved_by="fixture-user", note="schema reviewed"
        )
        self.assertEqual(state["contracts"][0]["status"], "approved")
        self.assertTrue(state["contracts"][0]["source_hash"].startswith("sha256:"))
        self.assertEqual(self.engine.next_task("demo")["id"], "T1")
        projected = render_plan(state) + render_tasks(state)
        self.assertIn("Program: commerce", projected)
        self.assertIn("checkout.api@1.0.0", projected)
        self.assertIn("service: order-service | layer: api", projected)
        self.assertEqual(
            self.store.read_records("demo", "events.jsonl")[-1]["event"],
            "contract_approved",
        )

    def test_contract_source_staleness_blocks_scheduling(self):
        self.initialize()
        reference = "checkout.api@1.0.0"
        self.engine.apply_plan(
            "demo",
            multi_service_plan(
                task(
                    1,
                    files=["services/order/app.py"],
                    service="order-service",
                    contract_reads=[reference],
                    produces=[reference],
                )
            ),
        )
        self.engine.approve_contract("demo", reference, approved_by="fixture-user")
        (self.root / ".contracts" / "checkout.yaml").write_text(
            "openapi: 3.1.0\ninfo:\n  title: Changed\n  version: 1.0.0\n",
            encoding="utf-8",
        )
        with self.assertRaises(ContractStale):
            self.engine.next_task("demo")

    def test_contract_writer_invalidates_prior_approval(self):
        self.initialize()
        reference = "checkout.api@1.0.0"
        initial = multi_service_plan(task(9, owner="qa", files=["tests/smoke.py"]))
        self.engine.apply_plan("demo", initial)
        self.engine.approve_contract("demo", reference, approved_by="fixture-user")
        revised = multi_service_plan(
            task(
                1,
                owner="architect",
                files=[".contracts/checkout.yaml"],
                risks=["public-contract"],
                layer="api",
                contract_writes=[reference],
                criterion="contract source is reviewed",
            ),
            task(
                2,
                dependencies=["T1"],
                files=["services/checkout-bff/client.py"],
                service="checkout-bff",
                contract_reads=[reference],
            ),
        )
        state = self.engine.apply_plan("demo", revised, replan=True)
        self.assertEqual(state["contracts"][0]["status"], "approved")
        result = {
            "outcome": "success",
            "summary": "contract source reviewed",
            "evidence": [
                {
                    "criterion": "contract source is reviewed",
                    "result": "pass",
                    "detail": "schema check passed",
                }
            ],
            "changed_files": [".contracts/checkout.yaml"],
            "memory": [],
        }

        class ContractWriter:
            name = "codex"

            def invoke(inner_self, request):
                del inner_self, request
                (self.root / ".contracts" / "checkout.yaml").write_text(
                    "openapi: 3.1.0\ninfo:\n  title: Checkout v1\n  version: 1.0.0\n",
                    encoding="utf-8",
                )
                return result

        state = self.engine.execute_with_provider("demo", ContractWriter(), task_id="T1")
        self.assertEqual(state["contracts"][0]["status"], "draft")
        self.assertEqual(state["contracts"][0]["source_hash"], "pending")
        review = {
            "verdict": "approve",
            "summary": "contract task accepted",
            "findings": [],
            "evidence_checked": ["contract source is reviewed"],
        }
        self.engine.review_with_provider("demo", "T1", named_provider([review], "claude"))
        with self.assertRaises(ContractApprovalRequired):
            self.engine.next_task("demo")

    def test_contract_writer_success_requires_actual_source_mutation(self):
        self.initialize()
        reference = "checkout.api@1.0.0"
        self.engine.apply_plan(
            "demo",
            multi_service_plan(
                task(
                    1,
                    owner="architect",
                    files=[".contracts/checkout.yaml"],
                    risks=["public-contract"],
                    contract_writes=[reference],
                    criterion="contract source changes",
                )
            ),
        )
        result = {
            "outcome": "success",
            "summary": "claimed a contract change",
            "evidence": [
                {
                    "criterion": "contract source changes",
                    "result": "pass",
                    "detail": "claimed",
                }
            ],
            "changed_files": [".contracts/checkout.yaml"],
            "memory": [],
        }
        with self.assertRaises(PolicyError):
            self.engine.execute_with_provider(
                "demo", named_provider([result], "codex"), task_id="T1"
            )
        state = self.store.load_state("demo")
        self.assertIn("did not mutate", state["tasks"][0]["last_failure"])

    def test_contract_deprecation_blocks_new_consumers(self):
        self.initialize()
        reference = "checkout.api@1.0.0"
        self.engine.apply_plan(
            "demo",
            multi_service_plan(
                task(
                    1,
                    files=["services/checkout-bff/client.py"],
                    service="checkout-bff",
                    contract_reads=[reference],
                )
            ),
        )
        self.engine.approve_contract("demo", reference, approved_by="fixture-user")
        state = self.engine.deprecate_contract(
            "demo", reference, deprecated_by="fixture-user", note="migration complete"
        )
        self.assertEqual(state["contracts"][0]["status"], "deprecated")
        self.assertEqual(
            self.store.read_records("demo", "events.jsonl")[-1]["event"],
            "contract_deprecated",
        )
        with self.assertRaises(ContractStale):
            self.engine.next_task("demo")

    def test_replan_preserves_contracts_referenced_by_completed_tasks(self):
        self.initialize()
        reference = "checkout.api@1.0.0"
        criterion = "consumer implementation passes"
        self.engine.apply_plan(
            "demo",
            multi_service_plan(
                task(
                    1,
                    files=["services/checkout-bff/client.py"],
                    service="checkout-bff",
                    contract_reads=[reference],
                    criterion=criterion,
                ),
                task(
                    2,
                    dependencies=["T1"],
                    owner="qa",
                    files=["tests/integration.py"],
                ),
            ),
        )
        self.engine.approve_contract("demo", reference, approved_by="fixture-user")
        self.execute_success(
            task_id="T1", criterion=criterion, path="services/checkout-bff/client.py"
        )
        self.approve_review(task_id="T1", criterion=criterion)
        without_registry = {
            "summary": "try to discard historical contract",
            "services": [
                {
                    "id": "order-service",
                    "domain": "orders",
                    "paths": ["services/order"],
                    "owns_data": ["order"],
                    "exposes": [],
                    "consumes": [],
                    "dependencies": [],
                    "forbidden_dependencies": [],
                }
            ],
            "contracts": [],
            "tasks": [task(2, owner="qa", files=["tests/integration.py"])],
        }
        with self.assertRaises(PolicyError):
            self.engine.apply_plan("demo", without_registry, replan=True)

    def test_contract_source_rejects_internal_symlink_component(self):
        self.initialize()
        reference = "checkout.api@1.0.0"
        (self.root / ".contracts" / "contract-link").symlink_to(self.root / ".contracts", target_is_directory=True)
        plan = multi_service_plan(
            task(
                1,
                files=["services/checkout-bff/client.py"],
                service="checkout-bff",
                contract_reads=[reference],
            )
        )
        plan["contracts"][0]["source"] = ".contracts/contract-link/checkout.yaml"
        self.engine.apply_plan("demo", plan)
        with self.assertRaises(ContractStale):
            self.engine.approve_contract("demo", reference, approved_by="fixture-user")

    def test_multi_service_policy_rejects_ownership_and_writer_errors(self):
        reference = "checkout.api@1.0.0"
        missing_dependency = multi_service_plan(
            task(
                1,
                owner="architect",
                files=[".contracts/checkout.yaml"],
                risks=["public-contract"],
                contract_writes=[reference],
            ),
            task(
                2,
                files=["services/checkout-bff/client.py"],
                service="checkout-bff",
                contract_reads=[reference],
            ),
        )
        wrong_writer = multi_service_plan(
            task(
                1,
                files=[".contracts/checkout.yaml"],
                risks=["public-contract"],
                service="order-service",
                contract_writes=[reference],
            )
        )
        wrong_data_owner = multi_service_plan(
            task(
                1,
                owner="database",
                files=["services/checkout-bff/migration.sql"],
                risks=["database"],
                service="checkout-bff",
                data_entities=["order"],
            )
        )
        duplicate_owner = multi_service_plan(
            task(1, owner="qa", files=["tests/integration.py"])
        )
        duplicate_owner["services"][1]["owns_data"] = ["order"]
        overlapping_paths = multi_service_plan(
            task(1, owner="qa", files=["tests/integration.py"])
        )
        overlapping_paths["services"][1]["paths"] = ["services/order/nested"]
        missing_service_participation = multi_service_plan(
            task(
                1,
                files=["services/notification/app.py"],
                service="notification-service",
                contract_reads=[reference],
            )
        )
        missing_service_participation["services"].append(
            {
                "id": "notification-service",
                "domain": "notifications",
                "paths": ["services/notification"],
                "owns_data": [],
                "exposes": [],
                "consumes": [],
                "dependencies": [],
                "forbidden_dependencies": [],
            }
        )
        missing_producer_dependency = multi_service_plan(
            task(1, owner="qa", files=["tests/integration.py"])
        )
        missing_producer_dependency["services"][1]["dependencies"] = []
        internal_contract_source = multi_service_plan(
            task(1, owner="qa", files=["tests/integration.py"])
        )
        internal_contract_source["contracts"][0]["source"] = ".AI-KIT/contracts/runtime.json"
        for candidate in (
            missing_dependency,
            wrong_writer,
            wrong_data_owner,
            duplicate_owner,
            overlapping_paths,
            missing_service_participation,
            missing_producer_dependency,
            internal_contract_source,
        ):
            with self.subTest(summary=candidate["tasks"][0]["title"]):
                with self.assertRaises(PolicyError):
                    normalize_plan(candidate)

    def test_state_validation_rejects_corrupted_contract_registry(self):
        self.initialize()
        state = self.engine.apply_plan(
            "demo", multi_service_plan(task(1, owner="qa", files=["tests/integration.py"]))
        )
        state["contracts"].append(dict(state["contracts"][0]))
        with self.assertRaises(ValueError):
            validate_state(state)

    def test_state_validation_rejects_malformed_requirement_ids(self):
        self.engine.initialize(
            "demo",
            "Validate canonical traceability",
            requirements=[{"id": "R1", "text": "Valid requirement"}],
        )
        state = self.store.load_state("demo")
        validate_state(state)
        state["requirements"][0]["id"] = "invalid"
        with self.assertRaisesRegex(ValueError, "R<n>"):
            validate_state(state)
        with self.assertRaisesRegex(StoreError, "invalid canonical state"):
            self.store.save_state("demo", state)

    def test_large_plan_and_independent_review_gates(self):
        self.engine = HarnessEngine(
            self.store,
            context_budget=1200,
            independent_review_enabled=True,
        )
        self.engine.initialize("demo", "Build a large controlled loop", size="large")
        self.engine.apply_plan("demo", {"summary": "large plan", "tasks": [task(1)]})
        with self.assertRaises(PlanApprovalRequired):
            self.engine.next_task("demo")
        state = self.engine.approve_plan("demo", approved_by="fixture-user")
        self.assertEqual(state["plan_approvals"][-1]["revision"], 1)
        self.execute_success()
        same_provider = named_provider([], "codex")
        with self.assertRaises(PolicyError):
            self.engine.review_with_provider("demo", "T1", same_provider)
        missing = named_provider(
            [
                {
                    "verdict": "approve",
                    "summary": "did not check evidence",
                    "findings": [],
                    "evidence_checked": [],
                }
            ],
            "claude",
        )
        with self.assertRaises(PolicyError):
            self.engine.review_with_provider("demo", "T1", missing)
        self.assertIn("Independently review", missing.calls[0].prompt)
        approved = self.approve_review()
        self.assertEqual(approved["status"], "complete")
        self.assertEqual(approved["tasks"][0]["reviews"][-1]["policy"], "independent")
        self.assertIn("Review (independent): approve", render_tasks(approved))

    def test_disabled_policy_overrides_recorded_independent_review(self):
        enabled = HarnessEngine(
            self.store,
            context_budget=1200,
            independent_review_enabled=True,
        )
        enabled.initialize(
            "demo",
            "Preserve recorded independent policy for audit",
            review_policy="independent",
        )
        enabled.apply_plan("demo", {"summary": "existing state", "tasks": [task(1)]})
        self.engine = enabled
        self.execute_success()

        disabled = HarnessEngine(self.store, context_budget=1200)
        review = {
            "verdict": "approve",
            "summary": "active-agent evidence accepted",
            "findings": [],
            "evidence_checked": ["criterion 1 passes"],
        }
        same_provider = named_provider([review], "codex")
        state = disabled.review_with_provider("demo", "T1", same_provider)
        self.assertEqual(state["tasks"][0]["state"], "complete")
        self.assertEqual(state["review_policy"], "independent")
        self.assertEqual(state["tasks"][0]["reviews"][-1]["policy"], "active-agent")
        self.assertIn("active-agent review", same_provider.calls[0].prompt)
        self.assertNotIn("Independently review", same_provider.calls[0].prompt)
        self.assertIn("Review (active-agent): approve", render_tasks(state))
        self.assertIn("Recorded review policy: independent", render_plan(state))

    def test_review_configuration_controls_engine_policy(self):
        state = self.engine.initialize("demo", "Use configured active-agent review")
        self.assertEqual(state["review_policy"], "active-agent")
        self.assertIn("Recorded review policy: active-agent", render_plan(state))

        with self.assertRaisesRegex(EngineError, "independent review is disabled"):
            self.engine.initialize(
                "demo",
                "Reject disabled independent review",
                review_policy="independent",
            )

        for feature in ("enabled-default", "enabled-active"):
            feature_dir = self.root / "features" / feature
            feature_dir.mkdir(parents=True)
            (feature_dir / "brief.md").write_text("# configured review\n", encoding="utf-8")
        enabled = HarnessEngine(
            self.store,
            context_budget=1200,
            independent_review_enabled=True,
        )
        default_state = enabled.initialize(
            "enabled-default", "Use independent review after manual activation"
        )
        active_state = enabled.initialize(
            "enabled-active",
            "Allow an explicit active-agent override",
            review_policy="active-agent",
        )
        self.assertEqual(default_state["review_policy"], "independent")
        self.assertEqual(active_state["review_policy"], "active-agent")

    def test_ai_kit_config_validation_fails_closed(self):
        harness_dir = self.root / ".ai-kit" / "harness"
        harness_dir.mkdir(parents=True)
        harness_config = {
            "schema_version": 1,
            "providers": {},
        }
        (harness_dir / "config.json").write_text(
            json.dumps(harness_config), encoding="utf-8"
        )
        kit_path = self.root / ".ai-kit" / "config.json"

        with self.assertRaisesRegex(EngineError, "invalid AI-Kit config"):
            load_config(self.root)

        kit_path.write_text("{not json", encoding="utf-8")
        with self.assertRaisesRegex(EngineError, "invalid AI-Kit config"):
            load_config(self.root)

        kit_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "review": {
                        "required": True,
                        "independent_enabled": "false",
                    },
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(EngineError, "must be true or false"):
            load_config(self.root)

        kit_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "review": {
                        "required": True,
                        "independent_enabled": False,
                    },
                    "orchestration": {
                        "mode": "ide-native-workers",
                        "enabled": True,
                        "max_workers": 4,
                        "require_dag": True,
                        "require_disjoint_files": True,
                        "coordinator_owns_task_state": True,
                        "require_worktree_per_worker": True,
                    },
                    "execution": {
                        "task_cli": {
                            "enabled": True,
                            "provider": "grok",
                            "model": None,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(EngineError, "must name a configured provider"):
            load_config(self.root)

        kit_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "review": {
                        "required": True,
                        "independent_enabled": False,
                    },
                    "execution": {
                        "codex_cli": {
                            "enabled": "false",
                            "model": "gpt-5.6-terra",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(EngineError, "enabled must be true or false"):
            load_config(self.root)

        kit_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "review": {
                        "required": True,
                        "independent_enabled": False,
                    },
                    "execution": {
                        "codex_cli": {
                            "enabled": False,
                            "model": "",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(EngineError, "model must be a non-empty string"):
            load_config(self.root)

        kit_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "review": {
                        "required": True,
                        "independent_enabled": False,
                    },
                    "execution": {
                        "codex_cli": {
                            "enabled": False,
                            "model": "gpt-5.6-terra",
                        },
                        "isolated_worktree": {"required": "true"},
                    },
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(EngineError, "isolated_worktree.required"):
            load_config(self.root)

        kit_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "review": {
                        "required": True,
                        "independent_enabled": False,
                    },
                    "execution": {
                        "codex_cli": {
                            "enabled": False,
                            "model": "gpt-5.6-terra",
                        },
                        "isolated_worktree": {"required": True},
                    },
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(EngineError, "quality.providers"):
            load_config(self.root)

        invalid_quality = quality_policy()
        invalid_quality["providers"]["claude-cli"]["model"] = "sonnet-5"
        kit_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "review": {
                        "required": True,
                        "independent_enabled": False,
                    },
                    "execution": {
                        "codex_cli": {
                            "enabled": False,
                            "model": "gpt-5.6-terra",
                        },
                        "isolated_worktree": {"required": True},
                    },
                    "quality": invalid_quality,
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(EngineError, "must be claude-sonnet-5"):
            load_config(self.root)

        kit_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "review": {
                        "required": True,
                        "independent_enabled": False,
                    },
                    "execution": {
                        "codex_cli": {
                            "enabled": False,
                            "model": "gpt-5.6-terra",
                        },
                        "isolated_worktree": {"required": True},
                    },
                    "orchestration": {
                        "mode": "ide-native-workers",
                        "enabled": True,
                        "max_workers": 4,
                        "require_dag": True,
                        "require_disjoint_files": True,
                        "coordinator_owns_task_state": True,
                        "require_worktree_per_worker": True,
                    },
                    "quality": quality_policy(),
                }
            ),
            encoding="utf-8",
        )
        loaded = load_config(self.root)
        self.assertFalse(loaded["kit_policy"]["review"]["independent_enabled"])
        self.assertTrue(
            loaded["kit_policy"]["execution"]["isolated_worktree"]["required"]
        )

        harness_config["providers"] = {
            "codex": {"reasoning_effort": {"planner": "unbounded"}}
        }
        (harness_dir / "config.json").write_text(
            json.dumps(harness_config), encoding="utf-8"
        )
        with self.assertRaisesRegex(EngineError, "invalid per-role reasoning effort"):
            load_config(self.root)

    def test_cli_isolation_blocks_missing_baseline_and_dirty_main_before_provider(self):
        self.initialize()
        self.engine.apply_plan(
            "demo", {"summary": "CLI isolation", "tasks": [task(1)]}
        )
        harness_dir = self.root / ".ai-kit" / "harness"
        harness_dir.mkdir(parents=True, exist_ok=True)
        (harness_dir / "config.json").write_text(
            json.dumps({"schema_version": 1, "providers": {}}),
            encoding="utf-8",
        )
        (self.root / ".ai-kit" / "config.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "review": {"required": True, "independent_enabled": False},
                    "orchestration": {
                        "mode": "ide-native-workers",
                        "enabled": True,
                        "max_workers": 4,
                        "require_dag": True,
                        "require_disjoint_files": True,
                        "coordinator_owns_task_state": True,
                        "require_worktree_per_worker": True,
                    },
                    "execution": {
                        "isolated_worktree": {"required": True},
                        "codex_cli": {
                            "enabled": False,
                            "model": "gpt-5.6-terra",
                        },
                    },
                    "quality": quality_policy(),
                }
            ),
            encoding="utf-8",
        )
        response = self.root / "response.json"
        response.write_text(
            json.dumps(
                {
                    "outcome": "success",
                    "summary": "must never execute",
                    "evidence": [],
                    "changed_files": [],
                    "memory": [],
                }
            ),
            encoding="utf-8",
        )
        subprocess.run(["git", "-C", str(self.root), "init", "-q"], check=True)
        arguments = [
            "--root",
            str(self.root),
            "step",
            "demo",
            "--task",
            "T1",
            "--provider",
            "scripted",
            "--response",
            str(response),
        ]
        stderr = io.StringIO()
        with patch.object(
            ScriptedProvider, "invoke", side_effect=AssertionError("provider invoked")
        ), patch("sys.stderr", stderr):
            self.assertEqual(cli_main(arguments), 2)
        self.assertIn("baseline commit", stderr.getvalue())
        self.assertEqual(self.store.load_state("demo")["tasks"][0]["state"], "ready")

        subprocess.run(
            ["git", "-C", str(self.root), "config", "user.email", "fixture@example.test"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.root), "config", "user.name", "Fixture"],
            check=True,
        )
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(self.root), "commit", "-q", "-m", "baseline"],
            check=True,
        )
        (self.root / "AGENTS.md").write_text("# dirty main\n", encoding="utf-8")
        stderr = io.StringIO()
        with patch.object(
            ScriptedProvider, "invoke", side_effect=AssertionError("provider invoked")
        ), patch("sys.stderr", stderr):
            self.assertEqual(cli_main(arguments), 2)
        self.assertIn("dirty outside control paths", stderr.getvalue())
        self.assertEqual(self.store.load_state("demo")["tasks"][0]["state"], "ready")

    def test_codex_cli_task_execution_policy_is_offline_and_fail_closed(self):
        config = {
            "provider_output_limit_chars": 200_000,
            "providers": {
                "codex": {
                    "executable": "codex",
                    "model": None,
                    "timeout_seconds": 1200,
                },
                "claude": {
                    "executable": "claude",
                    "model": None,
                    "timeout_seconds": 1200,
                },
            },
            "kit_policy": {
                "execution": {
                    "codex_cli": {
                        "enabled": True,
                        "model": "gpt-5.6-terra",
                    }
                }
            },
        }
        automatic = argparse.Namespace(provider=None, response=None)
        provider = task_provider_from_args(automatic, self.root, config)
        self.assertEqual(provider.name, "codex")
        self.assertEqual(provider.model, "gpt-5.6-terra")

        request = ProviderRequest("implementer", "execute one task", PLAN_SCHEMA)
        with patch.object(provider.provider, "invoke", return_value={}) as invoke:
            provider.invoke(request)
        forwarded = invoke.call_args.args[0]
        self.assertEqual(forwarded.model, "gpt-5.6-terra")
        command = provider.provider.command_preview(forwarded)
        self.assertIn("--model", command)
        self.assertIn("gpt-5.6-terra", command)
        self.assertIn("workspace-write", command)
        self.assertNotIn("bypass", " ".join(command).lower())

        for conflicting in ("claude", "scripted"):
            with self.subTest(conflicting=conflicting):
                args = argparse.Namespace(provider=conflicting, response=None)
                with self.assertRaisesRegex(EngineError, "only accepts --provider codex"):
                    task_provider_from_args(args, self.root, config)

        config["kit_policy"]["execution"]["codex_cli"]["enabled"] = False
        with self.assertRaisesRegex(EngineError, "pass --provider explicitly"):
            task_provider_from_args(automatic, self.root, config)
        explicit = argparse.Namespace(provider="codex", response=None)
        selected = task_provider_from_args(explicit, self.root, config)
        self.assertEqual(selected.name, "codex")
        self.assertIsNone(selected.model)

    def test_grok_task_cli_execution_is_automatic_only_for_implementers(self):
        config = {
            "provider_output_limit_chars": 200_000,
            "providers": {
                "codex": {"executable": "codex", "model": None, "timeout_seconds": 1200},
                "claude": {"executable": "claude", "model": None, "timeout_seconds": 1200},
                "grok": {"executable": "grok", "model": None, "timeout_seconds": 1200},
            },
            "kit_policy": {
                "execution": {
                    "task_cli": {"enabled": True, "provider": "grok", "model": None}
                },
                "quality": quality_policy(),
            },
        }
        automatic = argparse.Namespace(provider=None, response=None)
        selected = task_provider_from_args(automatic, self.root, config)
        self.assertEqual((selected.name, selected.model), ("grok", None))
        command = selected.provider.command_preview(
            ProviderRequest("implementer", "execute one task", PLAN_SCHEMA)
        )
        self.assertIn("acceptEdits", command)

        for conflicting in ("codex", "claude", "scripted"):
            with self.subTest(conflicting=conflicting):
                with self.assertRaisesRegex(EngineError, "only accepts --provider grok"):
                    task_provider_from_args(
                        argparse.Namespace(provider=conflicting, response=None),
                        self.root,
                        config,
                    )
        with self.assertRaisesRegex(EngineError, "--response is unavailable"):
            task_provider_from_args(
                argparse.Namespace(provider=None, response="response.json"),
                self.root,
                config,
            )

        config["kit_policy"]["execution"]["task_cli"]["enabled"] = False
        with self.assertRaisesRegex(EngineError, "pass --provider explicitly"):
            task_provider_from_args(automatic, self.root, config)
        self.assertEqual(
            task_provider_from_args(
                argparse.Namespace(provider="grok", response=None), self.root, config
            ).name,
            "grok",
        )

    def test_quality_routes_select_both_clis_without_provider_calls(self):
        config = {
            "provider_output_limit_chars": 200_000,
            "providers": {
                "codex": {
                    "executable": "codex",
                    "model": None,
                    "timeout_seconds": 1200,
                },
                "claude": {
                    "executable": "claude",
                    "model": None,
                    "timeout_seconds": 1200,
                },
            },
            "kit_policy": {
                "execution": {
                    "codex_cli": {
                        "enabled": True,
                        "model": "gpt-5.6-terra",
                    }
                },
                "quality": quality_policy(),
            },
        }
        automatic = argparse.Namespace(provider=None, response=None)

        with self.assertRaisesRegex(EngineError, "QA CLI routing is disabled"):
            task_provider_from_args(automatic, self.root, config, task_owner="qa")
        explicit_qa = task_provider_from_args(
            argparse.Namespace(provider="codex", response=None),
            self.root,
            config,
            task_owner="qa",
        )
        self.assertEqual(explicit_qa.name, "codex")
        self.assertIsNone(explicit_qa.model)

        config["kit_policy"]["quality"]["qa"]["enabled"] = True
        qa_codex = task_provider_from_args(
            automatic, self.root, config, task_owner="qa"
        )
        self.assertEqual((qa_codex.name, qa_codex.model), ("codex", "gpt-5.6-sol"))
        qa_request = ProviderRequest("implementer", "run QA", PLAN_SCHEMA)
        with patch.object(qa_codex.provider, "invoke", return_value={}) as invoke:
            qa_codex.invoke(qa_request)
        qa_codex_command = qa_codex.provider.command_preview(invoke.call_args.args[0])
        self.assertIn("workspace-write", qa_codex_command)
        self.assertIn("gpt-5.6-sol", qa_codex_command)
        with self.assertRaisesRegex(EngineError, "conflicting --provider claude"):
            task_provider_from_args(
                argparse.Namespace(provider="claude", response=None),
                self.root,
                config,
                task_owner="qa",
            )
        with self.assertRaisesRegex(EngineError, "--response is unavailable"):
            task_provider_from_args(
                argparse.Namespace(provider=None, response="unused.json"),
                self.root,
                config,
                task_owner="qa",
            )

        config["kit_policy"]["quality"]["qa"]["provider"] = "claude-cli"
        qa_claude = task_provider_from_args(
            automatic, self.root, config, task_owner="qa"
        )
        self.assertEqual(
            (qa_claude.name, qa_claude.model), ("claude", "claude-sonnet-5")
        )
        with patch.object(qa_claude.provider, "invoke", return_value={}) as invoke:
            qa_claude.invoke(qa_request)
        qa_claude_command = qa_claude.provider.command_preview(invoke.call_args.args[0])
        self.assertIn("acceptEdits", qa_claude_command)
        self.assertIn("claude-sonnet-5", qa_claude_command)

        normal = task_provider_from_args(
            automatic, self.root, config, task_owner="backend"
        )
        self.assertEqual((normal.name, normal.model), ("codex", "gpt-5.6-terra"))

        config["kit_policy"]["quality"]["review"]["enabled"] = True
        config["kit_policy"]["quality"]["review"]["provider"] = "codex-cli"
        review_codex = review_provider_from_args(automatic, self.root, config)
        self.assertEqual(
            (review_codex.name, review_codex.model), ("codex", "gpt-5.6-sol")
        )
        review_request = ProviderRequest("reviewer", "review task", PLAN_SCHEMA)
        with patch.object(review_codex.provider, "invoke", return_value={}) as invoke:
            review_codex.invoke(review_request)
        review_codex_command = review_codex.provider.command_preview(
            invoke.call_args.args[0]
        )
        self.assertIn("read-only", review_codex_command)

        config["kit_policy"]["quality"]["review"]["provider"] = "claude-cli"
        review_claude = review_provider_from_args(automatic, self.root, config)
        self.assertEqual(
            (review_claude.name, review_claude.model),
            ("claude", "claude-sonnet-5"),
        )
        with patch.object(review_claude.provider, "invoke", return_value={}) as invoke:
            review_claude.invoke(review_request)
        review_claude_command = review_claude.provider.command_preview(
            invoke.call_args.args[0]
        )
        self.assertIn("plan", review_claude_command)
        self.assertIn("claude-sonnet-5", review_claude_command)

        for command in (
            qa_codex_command,
            qa_claude_command,
            review_codex_command,
            review_claude_command,
        ):
            self.assertNotIn("bypass", " ".join(command).lower())

        conflict = argparse.Namespace(provider="codex", response=None)
        with self.assertRaisesRegex(EngineError, "conflicting --provider codex"):
            review_provider_from_args(conflict, self.root, config)
        with self.assertRaisesRegex(EngineError, "--response is unavailable"):
            review_provider_from_args(
                argparse.Namespace(provider=None, response="unused.json"),
                self.root,
                config,
            )

        config["kit_policy"]["quality"]["review"]["enabled"] = False
        with self.assertRaisesRegex(EngineError, "--provider is required"):
            review_provider_from_args(automatic, self.root, config)
        explicit = argparse.Namespace(provider="claude", response=None)
        selected = review_provider_from_args(explicit, self.root, config)
        self.assertEqual(selected.name, "claude")
        self.assertIsNone(selected.model)

    def test_retry_three_escalates(self):
        self.initialize()
        self.engine.apply_plan("demo", {"summary": "retry plan", "tasks": [task(1)]})
        failure = {
            "outcome": "failed",
            "summary": "acceptance failed",
            "evidence": [],
            "changed_files": [],
            "memory": [],
        }
        for attempt in range(1, 4):
            state = self.engine.execute_with_provider("demo", ScriptedProvider([failure]))
            self.assertEqual(state["tasks"][0]["attempts"], attempt)
        self.assertEqual(state["tasks"][0]["state"], "escalated")
        self.assertEqual(state["status"], "blocked")

    def test_success_requires_exact_evidence_and_file_scope(self):
        self.initialize()
        self.engine.apply_plan("demo", {"summary": "evidence plan", "tasks": [task(1)]})
        bad = {
            "outcome": "success",
            "summary": "claimed success",
            "evidence": [{"criterion": "different", "result": "pass", "detail": "none"}],
            "changed_files": ["outside.py"],
            "memory": [],
        }
        with self.assertRaises(PolicyError):
            self.engine.execute_with_provider("demo", ScriptedProvider([bad]))
        state = self.store.load_state("demo")
        self.assertEqual(state["tasks"][0]["attempts"], 1)
        self.assertEqual(state["tasks"][0]["state"], "ready")

    def test_memory_budget_provenance_and_staleness(self):
        self.initialize()
        source = self.root / "source.txt"
        source.write_text("original source\n", encoding="utf-8")
        memory = MemoryStore(self.store)
        memory.add(
            "demo",
            "working",
            "scheduler approval context",
            source="source.txt",
            tags=["scheduler", "approval"],
            importance=5,
        )
        memory.add("demo", "semantic", "unrelated convention", tags=["other"])
        result = memory.retrieve("demo", "scheduler approval", max_chars=512)
        self.assertLessEqual(result["used_chars"], 512)
        working = next(entry for entry in result["entries"] if entry.get("kind") == "working")
        self.assertTrue(working["provenance"]["hash"].startswith("sha256:"))
        self.assertFalse(working["stale"])
        source.write_text("changed source\n", encoding="utf-8")
        changed = memory.retrieve("demo", "scheduler approval", max_chars=512)
        working = next(entry for entry in changed["entries"] if entry.get("kind") == "working")
        self.assertTrue(working["stale"])
        source.unlink()
        missing = memory.retrieve("demo", "scheduler approval", max_chars=512)
        working = next(entry for entry in missing["entries"] if entry.get("kind") == "working")
        self.assertTrue(working["stale"])

    def test_native_provider_context_deduplicates_project_instructions(self):
        self.assertTrue(CodexProvider(self.root).loads_project_instructions)
        self.assertTrue(ClaudeProvider(self.root).loads_project_instructions)
        self.assertTrue(GrokProvider(self.root).loads_project_instructions)
        self.initialize()
        plan = {"summary": "native context plan", "tasks": [task(1)]}
        native = ScriptedProvider([plan])
        native.name = "codex"
        native.loads_project_instructions = True
        self.engine.plan_with_provider("demo", native)
        self.assertNotIn("# fixture rules", native.calls[0].prompt)
        self.assertIn("# fixture intent", native.calls[0].prompt)

        feature_dir = self.root / "features" / "custom"
        feature_dir.mkdir(parents=True)
        (feature_dir / "brief.md").write_text("# custom intent\n", encoding="utf-8")
        self.engine.initialize("custom", "Keep instructions for a custom provider")
        custom = ScriptedProvider(
            [{"summary": "custom context plan", "tasks": [task(1)]}]
        )
        self.engine.plan_with_provider("custom", custom)
        self.assertIn("# fixture rules", custom.calls[0].prompt)

    def test_deferred_project_source_is_reconsidered_without_early_truncation(self):
        self.initialize()
        architecture = "architecture-detail-" * 30
        project_dir = self.root / ".project" / "demo"
        (project_dir / "architecture.md").write_text(architecture, encoding="utf-8")
        result = MemoryStore(self.store).retrieve(
            "demo",
            "architecture",
            max_chars=1000,
            include_project_instructions=False,
        )
        entry = next(
            item
            for item in result["entries"]
            if item["provenance"]["ref"] == ".project/demo/architecture.md"
        )
        self.assertEqual(entry["content"], architecture)
        self.assertFalse(entry.get("truncated", False))
        self.assertEqual(result["excluded_sources"], ["AGENTS.md"])
        self.assertEqual(result["truncated_sources"], [])

    def test_execution_profiles_select_one_skill_and_owner_contract(self):
        cases = [
            ({"owner": "backend"}, "ai-kit-implement", ".ai-kit/agents/backend.md"),
            ({"owner": "database"}, "ai-kit-migrate-data", ".ai-kit/agents/database.md"),
            ({"owner": "qa"}, "ai-kit-validate-quality", ".ai-kit/agents/qa.md"),
            ({"owner": "reviewer"}, "ai-kit-review", ".ai-kit/agents/reviewer.md"),
            (
                {"owner": "architect", "contract_writes": []},
                "ai-kit-assess-architecture",
                ".ai-kit/agents/architect.md",
            ),
            (
                {"owner": "architect", "contract_writes": ["api@1.0.0"]},
                "ai-kit-design-contract",
                ".ai-kit/agents/architect.md",
            ),
        ]
        for task_value, workflow, contract in cases:
            with self.subTest(owner=task_value["owner"], workflow=workflow):
                self.assertEqual(
                    HarnessEngine._execution_profile(task_value),
                    (workflow, contract),
                )
                prompt_task = task(1, **task_value)
                prompt = HarnessEngine._execution_prompt(
                    {"goal": "bounded work", "services": [], "contracts": []},
                    prompt_task,
                    "context",
                )
                self.assertIn("`%s` skill" % workflow, prompt)
                self.assertIn("`%s` owner contract" % contract, prompt)
                self.assertIn(json.dumps(EXECUTION_SCHEMA, separators=(",", ":")), prompt)

        review_prompt = HarnessEngine._review_prompt(
            {"goal": "bounded review", "services": [], "contracts": []},
            task(1, owner="reviewer"),
            "context",
        )
        self.assertIn(json.dumps(REVIEW_SCHEMA, separators=(",", ":")), review_prompt)

    def test_effort_and_claude_reviewer_tools_are_explicit_offline(self):
        configured = ConfiguredProvider(
            CodexProvider(self.root),
            {
                "model": None,
                "timeout_seconds": 1200,
                "reasoning_effort": {
                    "planner": "xhigh",
                    "implementer": "high",
                    "reviewer": "xhigh",
                },
            },
            200_000,
        )
        request = ProviderRequest("reviewer", "review task", REVIEW_SCHEMA)
        with patch.object(configured.provider, "invoke", return_value={}) as invoke:
            configured.invoke(request)
        forwarded = invoke.call_args.args[0]
        self.assertEqual(forwarded.reasoning_effort, "xhigh")

        codex_command = configured.provider.command_preview(forwarded)
        self.assertIn('model_reasoning_effort="xhigh"', codex_command)
        claude_command = ClaudeProvider(self.root).command_preview(forwarded)
        self.assertIn("--effort", claude_command)
        self.assertIn("xhigh", claude_command)
        self.assertIn("plan", claude_command)
        self.assertEqual(
            claude_command[claude_command.index("--tools") + 1],
            "Read,Glob,Grep,Bash",
        )

        planner = ProviderRequest(
            "planner", "plan task", PLAN_SCHEMA, reasoning_effort="high"
        )
        planner_command = ClaudeProvider(self.root).command_preview(planner)
        self.assertEqual(
            planner_command[planner_command.index("--tools") + 1],
            "Read,Glob,Grep",
        )

    def test_grok_structured_command_modes_and_wrappers_are_explicit_offline(self):
        provider = GrokProvider(self.root)
        for role, schema, permission in (
            ("planner", PLAN_SCHEMA, "plan"),
            ("reviewer", REVIEW_SCHEMA, "plan"),
            ("implementer", EXECUTION_SCHEMA, "acceptEdits"),
        ):
            with self.subTest(role=role):
                request = ProviderRequest(
                    role,
                    "return a structured response",
                    schema,
                    model="grok-test-model",
                    reasoning_effort="high",
                )
                command = provider.command_preview(request)
                self.assertEqual(command[:2], ["grok", "--prompt-file"])
                self.assertEqual(command[2], "/tmp/ai-kit-prompt.md")
                self.assertEqual(command[command.index("--cwd") + 1], str(self.root))
                self.assertEqual(command[command.index("--output-format") + 1], "json")
                self.assertEqual(command[command.index("--permission-mode") + 1], permission)
                self.assertIn("--always-approve", command)
                self.assertEqual(command[command.index("--max-turns") + 1], "20")
                self.assertEqual(command[command.index("--model") + 1], "grok-test-model")
                self.assertEqual(command[command.index("--reasoning-effort") + 1], "high")
                # Grok's native schema mode cancels after intermediate
                # reasoning messages; the provider validates the canonical
                # schema after parsing the final JSON envelope instead.
                self.assertNotIn("--json-schema", command)

        response = {"summary": "wrapped plan", "tasks": [task(1)]}
        for stdout in (
            json.dumps(response),
            json.dumps({"structured_output": response}),
            json.dumps({"result": json.dumps(response)}),
        ):
            with self.subTest(stdout=stdout):
                with patch(
                    "providers.subprocess.run",
                    return_value=subprocess.CompletedProcess([], 0, stdout=stdout, stderr=""),
                ):
                    self.assertEqual(
                        provider.invoke(ProviderRequest("planner", "plan", PLAN_SCHEMA)),
                        response,
                    )

        nested_final = {
            "outcome": "success",
            "summary": "nested final response",
            "evidence": [
                {"criterion": "command passed", "result": "pass", "detail": "ok"}
            ],
            "changed_files": [],
            "memory": [{"kind": "episodic", "content": "proof", "tags": ["test"]}],
        }
        self.assertEqual(
            provider.parse_output(
                json.dumps({"text": "Done. " + json.dumps(nested_final)})
            ),
            nested_final,
        )

        final = {
            "outcome": "success",
            "summary": "completed after resume",
            "evidence": [],
            "changed_files": [],
            "memory": [],
        }
        incomplete = {
            "text": "I am still working.",
            "stopReason": "cancelled",
            "sessionId": "grok-session-1",
        }
        completed = {
            "text": "Done. " + json.dumps(final),
            "stopReason": "end_turn",
            "sessionId": "grok-session-1",
        }
        with patch(
            "providers.subprocess.run",
            side_effect=[
                subprocess.CompletedProcess([], 0, stdout=json.dumps(incomplete), stderr=""),
                subprocess.CompletedProcess([], 0, stdout=json.dumps(completed), stderr=""),
            ],
        ) as run:
            self.assertEqual(
                provider.invoke(ProviderRequest("implementer", "work", EXECUTION_SCHEMA)),
                final,
            )
        resume_command = run.call_args_list[1].args[0]
        self.assertEqual(
            resume_command[resume_command.index("--resume") + 1], "grok-session-1"
        )

        provider.max_resumes = 0
        with patch(
            "providers.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, stdout=json.dumps(incomplete), stderr=""),
        ):
            with self.assertRaisesRegex(
                ProviderError,
                r"Grok session incomplete; stop_reason=cancelled session_id=grok-session-1",
            ):
                provider.invoke(ProviderRequest("implementer", "work", EXECUTION_SCHEMA))

        still_incomplete = {
            "text": "The resumed session also needs more turns.",
            "stopReason": "max_turns",
            "sessionId": "grok-session-2",
        }
        retrying_provider = GrokProvider(self.root)
        with patch(
            "providers.subprocess.run",
            side_effect=[
                subprocess.CompletedProcess([], 0, stdout=json.dumps(incomplete), stderr=""),
                subprocess.CompletedProcess([], 0, stdout=json.dumps(still_incomplete), stderr=""),
            ],
        ):
            with self.assertRaisesRegex(
                ProviderError,
                r"stop_reason=cancelled session_id=grok-session-1.*"
                r"stop_reason=max_turns session_id=grok-session-2",
            ):
                retrying_provider.invoke(
                    ProviderRequest("implementer", "work", EXECUTION_SCHEMA)
                )

        with patch(
            "providers.subprocess.run",
            return_value=subprocess.CompletedProcess(
                [], 1, stdout="", stderr="Error: max turns reached"
            ),
        ):
            with self.assertRaisesRegex(
                ProviderError,
                r"Grok session incomplete; stop_reason=max_turns session_id=unknown",
            ):
                GrokProvider(self.root).invoke(
                    ProviderRequest("implementer", "work", EXECUTION_SCHEMA)
                )

    def test_review_provider_repository_mutation_fails_closed(self):
        self.initialize()
        self.engine.apply_plan("demo", {"summary": "review plan", "tasks": [task(1)]})
        self.execute_success()

        class MutatingReviewer:
            name = "claude"
            loads_project_instructions = True

            def invoke(inner_self, request):
                del inner_self, request
                (self.root / "review-artifact.txt").write_text(
                    "review must be read-only\n", encoding="utf-8"
                )
                return {
                    "verdict": "approve",
                    "summary": "claimed immutable review",
                    "findings": [],
                    "evidence_checked": ["criterion 1 passes"],
                }

        with self.assertRaisesRegex(
            PolicyError, "review provider mutated repository files: review-artifact.txt"
        ):
            self.engine.review_with_provider("demo", "T1", MutatingReviewer())
        state = self.store.load_state("demo")
        self.assertEqual(state["tasks"][0]["state"], "review")
        self.assertEqual(state["tasks"][0]["reviews"], [])

    def test_lock_and_path_validation(self):
        with self.store.lock("demo"):
            with self.assertRaises(LockError):
                with self.store.lock("demo"):
                    pass
        with self.assertRaises(StoreError):
            self.store.feature_dir("../escape")

        lock_dir = self.root / ".workspace" / "harness"
        lock_dir.mkdir(parents=True, exist_ok=True)
        stale = lock_dir / "demo.lock"
        stale.write_text('{"pid":2147483647,"created_at":"2000-01-01T00:00:00Z"}\n')
        self.assertTrue(self.store.lock_status("demo")["stale"])
        with self.store.lock("demo"):
            self.assertTrue(self.store.lock_status("demo")["alive"])

    def test_actual_mutation_and_symlink_scope_fail_closed(self):
        self.initialize()
        self.engine.apply_plan("demo", {"summary": "mutation plan", "tasks": [task(1)]})

        class MutatingProvider:
            name = "codex"

            def invoke(inner_self, request):
                del inner_self, request
                (self.root / "outside.py").write_text("undeclared\n", encoding="utf-8")
                (self.root / ".project" / "demo" / "state.json").write_text("{}\n", encoding="utf-8")
                return {
                    "outcome": "success",
                    "summary": "claimed scoped work",
                    "evidence": [
                        {"criterion": "criterion 1 passes", "result": "pass", "detail": "claimed"}
                    ],
                    "changed_files": ["src/1.py"],
                    "memory": [],
                }

        with self.assertRaises(PolicyError):
            self.engine.execute_with_provider("demo", MutatingProvider())
        state = self.store.load_state("demo")
        self.assertEqual(state["tasks"][0]["attempts"], 1)
        self.assertIn("outside.py", state["tasks"][0]["last_failure"])
        self.assertIn(".project/demo/state.json", state["tasks"][0]["last_failure"])

        # Use a fresh feature state because the first attempt is now recorded.
        (self.root / "features" / "linked").mkdir(parents=True)
        (self.root / "features" / "linked" / "brief.md").write_text("# linked\n")
        linked = HarnessEngine(self.store, context_budget=1200)
        linked.initialize("linked", "Reject a symlink escape")
        (self.root / "escape").symlink_to(self.root.parent, target_is_directory=True)
        linked.apply_plan(
            "linked",
            {"summary": "symlink plan", "tasks": [task(1, files=["escape/outside.py"])]},
        )
        with self.assertRaises(PolicyError):
            linked.execute_with_provider("linked", named_provider([], "codex"))

    def test_transition_artifact_reconciliation(self):
        self.initialize()
        state = self.store.load_state("demo")
        self.assertEqual(state["event_sequence"], 1)
        events_path = self.root / ".project" / "demo" / "events.jsonl"
        events_path.write_text("", encoding="utf-8")
        (self.root / ".project" / "demo" / "plan.md").write_text("stale\n", encoding="utf-8")
        status = self.engine.artifact_status("demo")
        self.assertTrue(status["needs_repair"])
        repaired = self.engine.repair_artifacts("demo")
        self.assertFalse(repaired["needs_repair"])
        event = self.store.read_records("demo", "events.jsonl")[-1]
        self.assertEqual(event["sequence"], 1)
        self.assertTrue(event["data"]["recovered"])

    def test_provider_commands_safe_without_execution(self):
        request = ProviderRequest("planner", "create a plan", PLAN_SCHEMA, timeout_seconds=10)
        for provider in (CodexProvider(self.root), ClaudeProvider(self.root), GrokProvider(self.root)):
            with self.subTest(provider=provider.name):
                command = provider.command_preview(request)
                joined = " ".join(command).lower()
                self.assertNotIn("bypass", joined)
                self.assertNotIn("skip-permissions", joined)
                self.assertIn("read-only", command) if provider.name == "codex" else self.assertIn("plan", command)
        with patch("providers.subprocess.run", side_effect=AssertionError("CLI executed")):
            value = ScriptedProvider([{"summary": "offline plan", "tasks": [task(1)]}]).invoke(request)
        self.assertEqual(value["summary"], "offline plan")

    def test_provider_working_directory_is_validated_and_routed(self):
        workspace = self.root / "isolated-workspace"
        workspace.mkdir()
        request = ProviderRequest(
            "planner",
            "create a plan",
            PLAN_SCHEMA,
            working_directory=workspace,
        )
        self.assertEqual(request.working_directory, workspace.resolve())

        codex = CodexProvider(self.root)
        command = codex.command_preview(request)
        self.assertEqual(command[command.index("--cd") + 1], str(workspace.resolve()))
        default_command = codex.command_preview(
            ProviderRequest("planner", "create a plan", PLAN_SCHEMA)
        )
        self.assertEqual(default_command[default_command.index("--cd") + 1], str(self.root))

        missing = self.root / "missing-workspace"
        with self.assertRaisesRegex(ProviderError, "existing directory"):
            ProviderRequest(
                "planner", "create a plan", PLAN_SCHEMA, working_directory=missing
            )
        regular_file = self.root / "not-a-workspace"
        regular_file.write_text("file\n", encoding="utf-8")
        with self.assertRaisesRegex(ProviderError, "existing directory"):
            ProviderRequest(
                "planner", "create a plan", PLAN_SCHEMA, working_directory=regular_file
            )
        linked = self.root / "linked-workspace"
        linked.symlink_to(workspace, target_is_directory=True)
        with self.assertRaisesRegex(ProviderError, "cannot use symlinks"):
            ProviderRequest(
                "planner", "create a plan", PLAN_SCHEMA, working_directory=linked
            )

    def test_native_subprocesses_use_request_working_directory(self):
        workspace = self.root / "provider-workspace"
        workspace.mkdir()
        request = ProviderRequest(
            "planner",
            "create a plan",
            PLAN_SCHEMA,
            working_directory=workspace,
        )
        response = {"summary": "isolated plan", "tasks": [task(1)]}

        def completed(command, **kwargs):
            self.assertEqual(kwargs["cwd"], str(workspace.resolve()))
            if "--output-last-message" in command:
                output_path = Path(command[command.index("--output-last-message") + 1])
                output_path.write_text(json.dumps(response), encoding="utf-8")
                stdout = ""
            elif command[0] == "claude":
                stdout = json.dumps({"structured_output": response})
            else:
                stdout = json.dumps(response)
            return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

        for provider in (CodexProvider(self.root), ClaudeProvider(self.root), GrokProvider(self.root)):
            with self.subTest(provider=provider.name):
                with patch("providers.subprocess.run", side_effect=completed):
                    self.assertEqual(provider.invoke(request), response)

    def test_codex_strict_schema_preserves_canonical_optional_fields(self):
        provider = CodexProvider(self.root, executable="codex")

        def assert_strict(schema):
            if "anyOf" in schema:
                for option in schema["anyOf"]:
                    assert_strict(option)
            if schema.get("type") == "object":
                self.assertEqual(schema["required"], list(schema["properties"]))
                for child in schema["properties"].values():
                    assert_strict(child)
            if schema.get("type") == "array" and "items" in schema:
                assert_strict(schema["items"])

        for canonical in (PLAN_SCHEMA, EXECUTION_SCHEMA, REVIEW_SCHEMA):
            assert_strict(provider.output_schema(canonical))

        request = ProviderRequest(
            "implementer", "execute bounded task", EXECUTION_SCHEMA, timeout_seconds=10
        )
        response = {
            "outcome": "success",
            "summary": "strict response accepted",
            "evidence": [
                {
                    "criterion": "proof exists",
                    "result": "pass",
                    "detail": "proof verified",
                    "command": None,
                }
            ],
            "changed_files": ["proof.txt"],
            "memory": [],
        }

        def completed(command, **kwargs):
            del kwargs
            schema_path = Path(command[command.index("--output-schema") + 1])
            output_path = Path(command[command.index("--output-last-message") + 1])
            strict = json.loads(schema_path.read_text(encoding="utf-8"))
            self.assertEqual(strict["required"], list(strict["properties"]))
            evidence = strict["properties"]["evidence"]["items"]
            self.assertEqual(evidence["required"], list(evidence["properties"]))
            self.assertEqual(
                evidence["properties"]["command"]["anyOf"][-1], {"type": "null"}
            )
            output_path.write_text(json.dumps(response), encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with patch("providers.subprocess.run", side_effect=completed):
            value = provider.invoke(request)
        self.assertNotIn("command", value["evidence"][0])

        response["summary"] = None
        with patch("providers.subprocess.run", side_effect=completed):
            with self.assertRaisesRegex(ProviderError, "must be string"):
                provider.invoke(request)

        response["summary"] = "unknown null must remain visible"
        response["unexpected"] = None
        with patch("providers.subprocess.run", side_effect=completed):
            with self.assertRaisesRegex(ProviderError, "unexpected keys: unexpected"):
                provider.invoke(request)

    def test_provider_failures_are_typed_and_closed(self):
        request = ProviderRequest("planner", "create a plan", PLAN_SCHEMA, timeout_seconds=1)
        for response in ("not-json", {"summary": "bad", "tasks": []}):
            with self.assertRaises(ProviderError):
                ScriptedProvider([response]).invoke(request)
        small = ProviderRequest("planner", "create a plan", PLAN_SCHEMA, max_output_chars=256)
        with self.assertRaises(ProviderError):
            ScriptedProvider(["{" + "x" * 300 + "}"]).invoke(small)
        failed = subprocess.CompletedProcess([], 7, stdout="", stderr="provider failure")
        for provider in (
            CodexProvider(self.root, executable="never-run-codex"),
            GrokProvider(self.root, executable="never-run-grok"),
        ):
            with self.subTest(provider=provider.name):
                with patch("providers.subprocess.run", return_value=failed):
                    with self.assertRaises(ProviderError):
                        provider.invoke(request)
                with patch(
                    "providers.subprocess.run",
                    side_effect=subprocess.TimeoutExpired(cmd=provider.executable, timeout=1),
                ):
                    with self.assertRaises(ProviderError):
                        provider.invoke(request)


class GitWorkspaceManagerCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / "repo"
        (self.root / ".ai-kit" / "knowledge").mkdir(parents=True)
        (self.root / ".ai-kit" / "fixture.txt").write_text("fixture\n", encoding="utf-8")
        (self.root / ".ai-kit" / "knowledge" / "conventions.md").write_text(
            "Use standard library.\n", encoding="utf-8"
        )
        for feature in ("demo", "retry", "drift"):
            (self.root / "features" / feature).mkdir(parents=True)
            (self.root / "features" / feature / "brief.md").write_text(
                "# %s\nControlled isolated change.\n" % feature,
                encoding="utf-8",
            )
        (self.root / "AGENTS.md").write_text("# fixture\n", encoding="utf-8")
        (self.root / "app.txt").write_text("base\n", encoding="utf-8")
        (self.root / "other.txt").write_text("stable\n", encoding="utf-8")
        (self.root / "check_app.py").write_text(
            "from pathlib import Path\nassert Path('app.txt').read_text() == 'isolated\\n'\n",
            encoding="utf-8",
        )
        self.git("init", "-q")
        self.git("config", "user.email", "fixture@example.test")
        self.git("config", "user.name", "Fixture")
        self.git(
            "add",
            "AGENTS.md",
            ".ai-kit",
            "features",
            "app.txt",
            "other.txt",
            "check_app.py",
        )
        self.git("commit", "-q", "-m", "baseline")
        self.manager = GitWorkspaceManager(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *arguments, cwd=None, check=True):
        return subprocess.run(
            ["git", "-C", str(cwd or self.root)] + list(arguments),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=check,
        )

    def test_create_capture_promote_and_owned_cleanup(self):
        record = self.manager.create("demo", "T1")
        workspace = Path(record.workspace)
        self.assertNotEqual(workspace, self.root)
        self.assertEqual(
            self.git("rev-parse", "HEAD", cwd=workspace).stdout.strip().decode(),
            record.base_commit,
        )
        (workspace / "app.txt").write_text("changed\n", encoding="utf-8")
        (workspace / "new.bin").write_bytes(b"\x00binary\xff")
        first = self.manager.capture_patch(record)
        second = self.manager.capture_patch(record)
        self.assertEqual(first.digest, second.digest)
        self.assertEqual(first.changed_files, ("app.txt", "new.bin"))
        self.assertIn(b"GIT binary patch", first.content)
        self.assertEqual((self.root / "app.txt").read_text(), "base\n")
        self.assertFalse((self.root / "new.bin").exists())
        promoted = self.manager.promote(record, first.digest)
        self.assertEqual(promoted.digest, first.digest)
        self.assertEqual((self.root / "app.txt").read_text(), "changed\n")
        self.assertEqual((self.root / "new.bin").read_bytes(), b"\x00binary\xff")
        self.assertEqual(self.git("diff", "--cached", "--quiet", check=False).returncode, 0)
        self.assertEqual(self.git("diff", "--quiet", check=False).returncode, 1)
        self.manager.cleanup(record)
        self.assertFalse(workspace.exists())
        self.assertFalse(self.manager.marker_path(record).exists())

    def test_owned_cleanup_survives_workspace_head_mutation(self):
        record = self.manager.create("demo", "T1")
        workspace = Path(record.workspace)
        (workspace / "app.txt").write_text("committed in disposable tree\n", encoding="utf-8")
        self.git("add", "app.txt", cwd=workspace)
        self.git("commit", "-q", "-m", "provider-local commit", cwd=workspace)
        with self.assertRaisesRegex(WorkspaceError, "base commit changed"):
            self.manager.capture_patch(record)
        self.manager.cleanup(record)
        self.assertFalse(workspace.exists())
        self.assertEqual((self.root / "app.txt").read_text(), "base\n")

    def test_engine_isolates_resumes_review_and_promotes_exact_patch(self):
        store = RepositoryStore(self.root)
        engine = HarnessEngine(store, workspace_manager=self.manager, context_budget=1200)
        engine.initialize("demo", "Change app only in an isolated workspace")
        engine.apply_plan(
            "demo",
            {
                "summary": "isolated app change",
                "tasks": [
                    task(
                        1,
                        files=["app.txt"],
                        verification_commands=[["python3", "check_app.py"]],
                    )
                ],
            },
        )

        class Implementer:
            name = "codex"
            loads_project_instructions = True

            def invoke(inner_self, request):
                del inner_self
                self.assertIsNotNone(request.working_directory)
                self.assertNotEqual(request.working_directory, self.root)
                (request.working_directory / "app.txt").write_text(
                    "isolated\n", encoding="utf-8"
                )
                self.assertEqual((self.root / "app.txt").read_text(), "base\n")
                return {
                    "outcome": "success",
                    "summary": "isolated implementation verified",
                    "evidence": [
                        {
                            "criterion": "criterion 1 passes",
                            "result": "pass",
                            "detail": "workspace content inspected",
                        }
                    ],
                    "changed_files": ["app.txt"],
                    "memory": [],
                }

        state = engine.execute_with_provider("demo", Implementer(), task_id="T1")
        isolated_task = state["tasks"][0]
        workspace_path = Path(isolated_task["workspace"]["workspace"])
        self.assertEqual(isolated_task["state"], "review")
        self.assertEqual(isolated_task["workspace"]["phase"], "review")
        self.assertRegex(isolated_task["workspace"]["patch_digest"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(isolated_task["workspace"]["changed_files"], ["app.txt"])
        self.assertTrue(isolated_task["verification_evidence"][0]["passed"])
        self.assertTrue(workspace_path.is_dir())
        self.assertEqual((self.root / "app.txt").read_text(), "base\n")

        class Reviewer:
            name = "claude"
            loads_project_instructions = True

            def invoke(inner_self, request):
                del inner_self
                self.assertEqual(request.working_directory, workspace_path.resolve())
                self.assertEqual(
                    (request.working_directory / "app.txt").read_text(), "isolated\n"
                )
                return {
                    "verdict": "approve",
                    "summary": "reviewed exact isolated result",
                    "findings": [],
                    "evidence_checked": ["criterion 1 passes"],
                }

        resumed = HarnessEngine(
            RepositoryStore(self.root),
            workspace_manager=GitWorkspaceManager(self.root),
            context_budget=1200,
        )
        state = resumed.review_with_provider("demo", "T1", Reviewer())
        isolated_task = state["tasks"][0]
        self.assertEqual(isolated_task["state"], "complete")
        self.assertEqual(isolated_task["workspace"]["phase"], "promoted")
        self.assertEqual((self.root / "app.txt").read_text(), "isolated\n")
        self.assertFalse(workspace_path.exists())
        self.assertEqual(self.git("diff", "--cached", "--quiet", check=False).returncode, 0)
        self.assertEqual(self.git("diff", "--quiet", check=False).returncode, 1)

    def test_engine_rejects_promotion_after_main_head_drift(self):
        store = RepositoryStore(self.root)
        engine = HarnessEngine(store, workspace_manager=self.manager, context_budget=1200)
        engine.initialize("drift", "Reject stale isolated promotion")
        engine.apply_plan(
            "drift",
            {"summary": "stale app change", "tasks": [task(1, files=["app.txt"])]},
        )

        class Implementer:
            name = "codex"
            loads_project_instructions = True

            def invoke(inner_self, request):
                del inner_self
                (request.working_directory / "app.txt").write_text(
                    "isolated\n", encoding="utf-8"
                )
                return {
                    "outcome": "success",
                    "summary": "stale candidate prepared",
                    "evidence": [
                        {
                            "criterion": "criterion 1 passes",
                            "result": "pass",
                            "detail": "candidate inspected",
                        }
                    ],
                    "changed_files": ["app.txt"],
                    "memory": [],
                }

        state = engine.execute_with_provider("drift", Implementer(), task_id="T1")
        workspace_path = Path(state["tasks"][0]["workspace"]["workspace"])
        (self.root / "other.txt").write_text("advanced\n", encoding="utf-8")
        self.git("add", "other.txt")
        self.git("commit", "-q", "-m", "advance main")
        reviewer = named_provider(
            [
                {
                    "verdict": "approve",
                    "summary": "candidate review passed",
                    "findings": [],
                    "evidence_checked": ["criterion 1 passes"],
                }
            ],
            "claude",
        )
        with self.assertRaisesRegex(WorkspaceError, "HEAD changed"):
            engine.review_with_provider("drift", "T1", reviewer)
        state = store.load_state("drift")
        self.assertEqual(state["tasks"][0]["state"], "review")
        self.assertEqual(state["tasks"][0]["workspace"]["phase"], "failed")
        self.assertTrue(workspace_path.exists())
        self.assertEqual((self.root / "app.txt").read_text(), "base\n")

    def test_cleanup_requires_explicit_abandon_and_status_exposes_phase(self):
        store = RepositoryStore(self.root)
        engine = HarnessEngine(store, workspace_manager=self.manager, context_budget=1200)
        engine.initialize("demo", "Guard live workspace cleanup")
        engine.apply_plan(
            "demo", {"summary": "guard cleanup", "tasks": [task(1, files=["app.txt"])]}
        )
        record = self.manager.create(
            "demo", "T1", allowed_dirty_paths=[".project/demo"]
        )
        artifact = self.manager.capture_patch(record)
        state = store.load_state("demo")
        state["tasks"][0]["state"] = "review"
        state["tasks"][0]["workspace"] = {
            **record.to_dict(),
            "phase": "review",
            "patch_digest": artifact.digest,
            "changed_files": [],
            "created_at": "2026-08-22T00:00:00Z",
            "verified_at": "2026-08-22T00:00:00Z",
            "promoted_at": None,
        }
        state["status"] = "awaiting_review"
        store.save_state("demo", state)

        view = status_view(store.load_state("demo"))
        self.assertEqual(view["workspaces"]["T1"]["phase"], "review")
        parsed = cli_parser().parse_args(["cleanup", "demo", "T1", "--abandon"])
        self.assertTrue(parsed.abandon)
        with self.assertRaisesRegex(EngineError, "pass --abandon explicitly"):
            engine.cleanup_workspace("demo", "T1")
        self.assertTrue(Path(record.workspace).exists())

        abandoned = engine.cleanup_workspace(
            "demo", "T1", abandon=True, actor="fixture-user"
        )
        self.assertEqual(abandoned["tasks"][0]["state"], "ready")
        self.assertEqual(abandoned["tasks"][0]["attempts"], 1)
        self.assertEqual(abandoned["tasks"][0]["workspace"]["phase"], "discarded")
        self.assertFalse(Path(record.workspace).exists())

        stale = store.load_state("demo")
        stale["tasks"][0]["workspace"]["cleanup_pending"] = True
        stale["tasks"][0]["workspace"]["last_error"] = "simulated stale cleanup"
        store.save_state("demo", stale)
        engine.cleanup_workspace("demo", "T1", actor="fixture-user")
        reloaded = store.load_state("demo")
        self.assertFalse(reloaded["tasks"][0]["workspace"]["cleanup_pending"])
        self.assertNotIn("last_error", reloaded["tasks"][0]["workspace"])
        self.assertEqual(reloaded["last_transition"]["event"], "workspace_reconciled")

    def test_review_revise_and_block_discard_before_retry(self):
        store = RepositoryStore(self.root)
        engine = HarnessEngine(store, workspace_manager=self.manager, context_budget=1200)
        engine.initialize("retry", "Retry isolated revisions")
        engine.apply_plan(
            "retry",
            {"summary": "retry app change", "tasks": [task(1, files=["app.txt"])]},
        )

        class Implementer:
            name = "codex"
            loads_project_instructions = True

            def __init__(inner_self, content):
                inner_self.content = content

            def invoke(inner_self, request):
                (request.working_directory / "app.txt").write_text(
                    inner_self.content + "\n", encoding="utf-8"
                )
                return {
                    "outcome": "success",
                    "summary": "isolated retry candidate",
                    "evidence": [
                        {
                            "criterion": "criterion 1 passes",
                            "result": "pass",
                            "detail": "candidate inspected",
                        }
                    ],
                    "changed_files": ["app.txt"],
                    "memory": [],
                }

        def review(verdict):
            return named_provider(
                [
                    {
                        "verdict": verdict,
                        "summary": "%s isolated candidate" % verdict,
                        "findings": [],
                        "evidence_checked": ["criterion 1 passes"],
                    }
                ],
                "claude",
            )

        first = engine.execute_with_provider("retry", Implementer("first"), task_id="T1")
        first_workspace = Path(first["tasks"][0]["workspace"]["workspace"])
        first_run = first["tasks"][0]["workspace"]["run_id"]
        revised = engine.review_with_provider("retry", "T1", review("revise"))
        self.assertEqual(revised["tasks"][0]["state"], "ready")
        self.assertEqual(revised["tasks"][0]["workspace"]["phase"], "discarded")
        self.assertFalse(first_workspace.exists())
        self.assertEqual((self.root / "app.txt").read_text(), "base\n")

        second = engine.execute_with_provider("retry", Implementer("second"), task_id="T1")
        second_workspace = Path(second["tasks"][0]["workspace"]["workspace"])
        self.assertNotEqual(second["tasks"][0]["workspace"]["run_id"], first_run)
        blocked = engine.review_with_provider("retry", "T1", review("block"))
        self.assertEqual(blocked["tasks"][0]["state"], "escalated")
        self.assertEqual(blocked["tasks"][0]["workspace"]["phase"], "discarded")
        self.assertFalse(second_workspace.exists())
        self.assertEqual((self.root / "app.txt").read_text(), "base\n")

    def test_missing_head_dirty_main_and_base_drift_fail_closed(self):
        no_head = self.base / "no-head"
        (no_head / ".ai-kit").mkdir(parents=True)
        (no_head / "AGENTS.md").write_text("# fixture\n")
        subprocess.run(["git", "-C", str(no_head), "init", "-q"], check=True)
        with self.assertRaisesRegex(WorkspaceError, "baseline commit"):
            GitWorkspaceManager(no_head).create("demo", "T1")

        (self.root / "app.txt").write_text("dirty\n")
        with self.assertRaisesRegex(WorkspaceError, "dirty outside control paths"):
            self.manager.create("demo", "T1")
        self.git("checkout", "--", "app.txt")

        record = self.manager.create("demo", "T1")
        workspace = Path(record.workspace)
        (workspace / "app.txt").write_text("isolated\n")
        artifact = self.manager.capture_patch(record)
        (self.root / "main-only.txt").write_text("advance\n")
        self.git("add", "main-only.txt")
        self.git("commit", "-q", "-m", "advance main")
        with self.assertRaisesRegex(WorkspaceError, "HEAD changed"):
            self.manager.promote(record, artifact.digest)
        self.assertEqual((self.root / "app.txt").read_text(), "base\n")
        self.manager.cleanup(record)

    def test_path_marker_parent_and_git_failures_do_not_cleanup_unowned_data(self):
        parent = self.manager.workspace_parent
        external = self.base / "external"
        external.mkdir()
        parent.symlink_to(external, target_is_directory=True)
        with self.assertRaisesRegex(WorkspaceError, "parent cannot be a symlink"):
            self.manager.create("demo", "T1")
        parent.unlink()

        parent.write_text("conflict\n", encoding="utf-8")
        with self.assertRaisesRegex(WorkspaceError, "prepare workspace parent"):
            self.manager.create("demo", "T1")
        parent.unlink()

        with patch("worktrees.subprocess.run", side_effect=FileNotFoundError):
            with self.assertRaisesRegex(WorkspaceError, "Git executable"):
                self.manager.create("demo", "T1")

        record = self.manager.create("demo", "T1")
        escaped = WorkspaceRecord(
            repository=record.repository,
            workspace=str(external),
            feature=record.feature,
            task=record.task,
            run_id=record.run_id,
            base_commit=record.base_commit,
        )
        with self.assertRaisesRegex(WorkspaceError, "escapes the owned parent"):
            self.manager.cleanup(escaped)
        self.assertTrue(external.exists())

        marker = self.manager.marker_path(record)
        original = marker.read_text(encoding="utf-8")
        marker.write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(WorkspaceError, "marker does not match"):
            self.manager.cleanup(record)
        self.assertTrue(Path(record.workspace).exists())
        marker.write_text(original, encoding="utf-8")
        self.manager.cleanup(record)


if __name__ == "__main__":
    unittest.main(verbosity=2)
