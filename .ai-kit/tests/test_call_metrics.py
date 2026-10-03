#!/usr/bin/env python3
"""Offline telemetry for complete requests and real adapter subprocess counts."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "harness"))
from call_metrics import CallMetrics
from cli import ConfiguredProvider
from engine import HarnessEngine
from prompt_evidence import EvidenceError
from providers import GrokProvider, ProviderError, ProviderRequest, ScriptedProvider, SubprocessProvider
from schemas import EXECUTION_SCHEMA
from store import RepositoryStore


TASK = {"id": "T1", "title": "Verify", "description": "Bounded fixture", "dependencies": [],
        "acceptance_criteria": ["criterion passes"], "owner": "backend", "scope": "S",
        "files": ["src/a.py"], "risks": [], "review_required": True}
RESULT = {"outcome": "success", "summary": "verified", "changed_files": ["src/a.py"],
          "evidence": [{"criterion": "criterion passes", "result": "pass", "detail": "manual inspection"}],
          "memory": []}


class FakeNative(SubprocessProvider):
    def build_command(self, request, schema_path, output_path, prompt_path):
        return ["fixture-cli"]


class CallMetricsCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / ".ai-kit").mkdir()
        (self.root / "AGENTS.md").write_text("# Rules\n")
        (self.root / "features/demo").mkdir(parents=True)
        (self.root / "features/demo/brief.md").write_text("# Fixture\n")
        self.engine = HarnessEngine(RepositoryStore(self.root))
        self.engine.initialize("demo", "Verify fixture")

    def tearDown(self):
        self.temp.cleanup()

    def metrics(self):
        return [json.loads(path.read_text()) for path in sorted(self.root.glob(".workspace/qa/call-*/metrics.json"))]

    def test_all_three_routes_measure_complete_prompts_without_fabricated_usage(self):
        planner = ScriptedProvider([{"summary": "plan", "tasks": [TASK]}])
        planner.name = "planner"
        self.engine.plan_with_provider("demo", planner)
        implementer = ScriptedProvider([RESULT])
        implementer.name = "implementer"
        self.engine.execute_with_provider("demo", implementer)
        reviewer = ScriptedProvider([{"verdict": "approve", "summary": "checked", "findings": [],
                                      "evidence_checked": ["criterion passes"]}])
        reviewer.name = "reviewer"
        self.engine.review_with_provider("demo", "T1", reviewer)
        records = {item["role"]: item for item in self.metrics()}
        self.assertEqual(set(records), {"planner", "implementer", "reviewer"})
        for provider, role in ((planner, "planner"), (implementer, "implementer"), (reviewer, "reviewer")):
            record = records[role]
            request = provider.calls[0]
            self.assertEqual(record["prompt_bytes"], len(request.prompt.encode("utf-8")))
            self.assertEqual(record["prompt_chars"], len(request.prompt))
            self.assertEqual(record["provider_calls"], 1)
            self.assertEqual(record["status"], "success")
            self.assertIn("provider", record["phases_ms"])
            self.assertLessEqual(record["context_chars"], record["context_budget_chars"])
            for field in ("llm_usage", "tool_output_bytes", "quota", "cache_hits", "provider_subprocess_calls"):
                self.assertIsNone(record[field])

    def test_failed_provider_retains_metadata_and_task_failure(self):
        self.engine.apply_plan("demo", {"summary": "plan", "tasks": [TASK]})
        provider = ScriptedProvider([])
        with self.assertRaises(ProviderError):
            self.engine.execute_with_provider("demo", provider)
        record = self.metrics()[0]
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["error_kind"], "ProviderError")
        self.assertEqual(self.engine.store.load_state("demo")["tasks"][0]["state"], "ready")

    def test_native_counts_and_configured_wrapper_forwarding(self):
        native = FakeNative(self.root, "fixture-cli")
        wrapper = ConfiguredProvider(native, {"timeout_seconds": 60}, 1000)
        request = ProviderRequest("planner", "PRIVATE-PROMPT-\u03b1", {"type": "object"})
        stdout, stderr = '{"ok":true}', "diagnostic \u03b1"
        with patch("providers.subprocess.run", return_value=subprocess.CompletedProcess([], 0, stdout, stderr)):
            wrapper.invoke(request)
        metric = CallMetrics(self.root, "demo", "planner")
        metric.request(request)
        metric.provider(wrapper)
        metric.write()
        data = json.loads(metric.path.read_text())
        self.assertEqual(data["provider_subprocess_calls"], 1)
        self.assertEqual(data["provider_resume_calls"], 0)
        self.assertEqual(data["provider_stdout_bytes"], len(stdout.encode()))
        self.assertEqual(data["provider_stderr_bytes"], len(stderr.encode()))
        self.assertNotIn("PRIVATE-PROMPT", metric.path.read_text())
        self.assertNotIn("diagnostic", metric.path.read_text())

    def test_grok_resume_counts_actual_subprocesses_and_resets_next_call(self):
        provider = GrokProvider(self.root)
        incomplete = json.dumps({"text": "Continue", "stopReason": "max_turns", "sessionId": "fixture-session"})
        complete = json.dumps({"text": json.dumps(RESULT)})
        request = ProviderRequest("implementer", "work", EXECUTION_SCHEMA)
        with patch("providers.subprocess.run", side_effect=[
                subprocess.CompletedProcess([], 0, incomplete, ""),
                subprocess.CompletedProcess([], 0, complete, "")]):
            provider.invoke(request)
        self.assertEqual(provider.last_invocation_metrics["subprocess_calls"], 2)
        self.assertEqual(provider.last_invocation_metrics["resume_calls"], 1)
        with patch("providers.subprocess.run", return_value=subprocess.CompletedProcess([], 0, complete, "")):
            provider.invoke(request)
        self.assertEqual(provider.last_invocation_metrics["subprocess_calls"], 1)

    def test_timeout_counts_captured_partial_streams(self):
        provider = FakeNative(self.root, "fixture-cli")
        with patch("providers.subprocess.run", side_effect=subprocess.TimeoutExpired(
                ["fixture-cli"], 1, output=b"partial", stderr=b"error")):
            with self.assertRaises(ProviderError):
                provider.invoke(ProviderRequest("planner", "work", {"type": "object"}))
        self.assertEqual(provider.last_invocation_metrics["stdout_bytes"], 7)
        self.assertEqual(provider.last_invocation_metrics["stderr_bytes"], 5)

    def test_wrapper_configuration_failure_does_not_reuse_previous_adapter_counts(self):
        native = FakeNative(self.root, "fixture-cli")
        wrapper = ConfiguredProvider(native, {"timeout_seconds": 60}, 1000)
        request = ProviderRequest("planner", "work", {"type": "object"})
        with patch("providers.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "{}", "")):
            wrapper.invoke(request)
        self.assertEqual(wrapper.last_invocation_metrics["subprocess_calls"], 1)
        wrapper.reasoning_effort["planner"] = "invalid"
        with self.assertRaises(ProviderError):
            wrapper.invoke(request)
        self.assertIsNone(wrapper.last_invocation_metrics)

    def test_metrics_write_failure_cannot_accept_execution(self):
        self.engine.apply_plan("demo", {"summary": "plan", "tasks": [TASK]})
        with patch("call_metrics.reporter.write_private_json", side_effect=OSError("disk full")):
            with self.assertRaises(EvidenceError):
                self.engine.execute_with_provider("demo", ScriptedProvider([RESULT]))
        self.assertNotIn(self.engine.store.load_state("demo")["tasks"][0]["state"], {"review", "complete"})

    def test_custom_provider_without_supported_metrics_remains_unknown(self):
        provider = ScriptedProvider([])
        provider.last_invocation_metrics = ["unsupported legacy metadata"]
        metric = CallMetrics(self.root, "demo", "planner")
        metric.provider(provider)
        self.assertIsNone(metric.data["provider_subprocess_calls"])


if __name__ == "__main__":
    unittest.main()
