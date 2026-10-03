#!/usr/bin/env python3
"""Regression checks for fixed-matrix compact QA reporting."""

from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import signal
import stat
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".ai-kit" / "scripts"))
import qa_report  # noqa: E402


def profile(name: str, source: str, status: int = 0, timeout: int = 30):
    command = ("python3", "-c", source if status == 0 else source + "; import sys; sys.exit(%d)" % status)
    return qa_report.Profile(name, command, ".", timeout)


def load_manifest(root: Path):
    manifests = list(root.glob("run-*/run.json"))
    assert len(manifests) == 1, manifests
    return json.loads(manifests[0].read_text(encoding="utf-8")), manifests[0]


def run_main(root: Path, profiles, arguments=("--profile", "all")):
    original_root = qa_report.ARTIFACT_ROOT
    original_profiles = qa_report.PROFILES
    qa_report.ARTIFACT_ROOT = root
    qa_report.PROFILES = profiles
    output = io.StringIO()
    try:
        with contextlib.redirect_stdout(output):
            status = qa_report.main(list(arguments))
    finally:
        qa_report.ARTIFACT_ROOT = original_root
        qa_report.PROFILES = original_profiles
    return status, output.getvalue()


def inject_artifact_error(root: Path, replacement):
    original_root = qa_report.ARTIFACT_ROOT
    original_profiles = qa_report.PROFILES
    original_write = qa_report.write_private_bytes
    qa_report.ARTIFACT_ROOT = root
    qa_report.PROFILES = {"ai-kit": profile("ai-kit", "print('ok')")}
    qa_report.write_private_bytes = replacement
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            status = qa_report.main(["--profile", "ai-kit"])
    finally:
        qa_report.ARTIFACT_ROOT = original_root
        qa_report.PROFILES = original_profiles
        qa_report.write_private_bytes = original_write
    return status


def main() -> int:
    failures = []
    fixed = qa_report.resolve_profiles(["all"])
    expected = [
        ("ai-kit", ("bash", ".ai-kit/tests/run.sh")),
        ("theme", ("bash", "tests/run.sh")),
        ("browser", ("npm", "--prefix", "tests/e2e", "test", "--", "--project=chromium")),
    ]
    if [(item.name, item.command) for item in fixed] != expected:
        failures.append("fixed all profile argv/order changed")
    for values in ((), ("missing",), ("ai-kit", "ai-kit"), ("all", "theme")):
        try:
            qa_report.resolve_profiles(values)
            failures.append("unsafe profile request was accepted: %s" % (values,))
        except qa_report.QaReportError:
            pass

    with tempfile.TemporaryDirectory(prefix="qa-report-test-") as directory:
        root = Path(directory)
        fixture_secret = "".join(("AK", "IA", "1234567890123456"))
        os.environ["QA_REPORT_TEST_SECRET"] = fixture_secret
        profiles = {
            "ai-kit": profile(
                "ai-kit",
                "import os; print('RAW-FIRST secret=' + os.environ['QA_REPORT_TEST_SECRET'])",
                7,
            ),
            "theme": profile("theme", "print('RAW-THEME')"),
            "browser": profile("browser", "print('RAW-BROWSER')", 9),
        }
        status, quiet = run_main(root / "quiet", profiles)
        manifest, manifest_path = load_manifest(root / "quiet")
        if status != 7 or manifest["first_failure_status"] != 7:
            failures.append("all did not return its first failure")
        if manifest["executed_profiles"] != ["ai-kit", "theme", "browser"]:
            failures.append("all did not continue through the fixed profile order")
        if "RAW-THEME" in quiet:
            failures.append("quiet summary exposed successful raw logs")
        if fixture_secret in quiet or "[REDACTED]" not in quiet:
            failures.append("quiet failure excerpt did not redact credential-like output")
        for result in manifest["results"]:
            for stream in ("stdout", "stderr"):
                path = Path(result[stream]["path"])
                if not path.is_file() or not result[stream]["sha256"]:
                    failures.append("missing checksummed %s artifact" % stream)
                elif stat.S_IMODE(path.stat().st_mode) != 0o600:
                    failures.append("artifact is not owner-only")
        if stat.S_IMODE(manifest_path.parent.stat().st_mode) != 0o700:
            failures.append("artifact directory is not owner-only")

        success_profiles = {
            "ai-kit": profile("ai-kit", "print('QUIET-AI')"),
            "theme": profile("theme", "print('QUIET-THEME')"),
            "browser": profile("browser", "print('QUIET-BROWSER')"),
        }
        quiet_status, quiet_success = run_main(root / "quiet-success", success_profiles)
        verbose_status, verbose_success = run_main(root / "verbose-success", success_profiles, ("--profile", "all", "--verbose"))
        quiet_manifest, _ = load_manifest(root / "quiet-success")
        verbose_manifest, _ = load_manifest(root / "verbose-success")
        compact_records = [(item["profile"], item["command"], item["status"]) for item in quiet_manifest["results"]]
        verbose_records = [(item["profile"], item["command"], item["status"]) for item in verbose_manifest["results"]]
        if quiet_status or verbose_status or compact_records != verbose_records:
            failures.append("quiet and verbose changed command execution or status")
        if len(quiet_success.splitlines()) > 12 or len(quiet_success.encode("utf-8")) > 1000:
            failures.append("quiet successful all output exceeded its contract bound")
        if "QUIET-AI" in quiet_success or "QUIET-THEME" in quiet_success or "QUIET-BROWSER" in quiet_success:
            failures.append("quiet successful all output exposed raw logs")
        if "QUIET-AI" not in verbose_success or "QUIET-BROWSER" not in verbose_success:
            failures.append("verbose output did not replay stored logs")

        timeout = qa_report.Profile("timeout", ("python3", "-c", "import time; time.sleep(1)"), ".", 0.01)
        timeout_result = qa_report.execute_profile(timeout, root / "timeout") if (root / "timeout").mkdir() is None else None
        if timeout_result["status"] != 124 or not timeout_result["timed_out"]:
            failures.append("timeout did not map to status 124")
        if timeout_result["failure_kind"] != "timeout":
            failures.append("timeout was not classified")
        (root / "missing").mkdir()
        missing = qa_report.Profile("missing", ("never-run-this",), ".", 30, ("absent.py",))
        missing_result = qa_report.execute_profile(missing, root / "missing", root=root)
        if missing_result["failure_kind"] != "environment" or "absent.py" not in missing_result["failure_excerpt"]:
            failures.append("missing QA input was not diagnosed before execution")
        (root / "custom").mkdir()
        custom = qa_report.execute_profile(profile("custom", "import os; print(os.getcwd())"), root / "custom", root=root)
        if Path(custom["stdout"]["path"]).read_text().strip() != str(root):
            failures.append("supplied repository root was ignored")
        if manifest["results"][0]["failure_kind"] != "test":
            failures.append("non-zero test exit was not classified")
        if quiet_manifest["metrics"]["llm_usage"] is not None or quiet_manifest["metrics"]["output_bytes"] <= 0:
            failures.append("local metrics were missing or fabricated token usage")
        signalled = qa_report.Profile(
            "signal",
            ("python3", "-c", "import os, signal; os.kill(os.getpid(), signal.SIGTERM)"),
            ".",
            30,
        )
        (root / "signal").mkdir()
        signal_result = qa_report.execute_profile(signalled, root / "signal")
        if signal_result["status"] != 128 + signal.SIGTERM:
            failures.append("signal did not map to 128 + signal")
        if len(qa_report.bounded_excerpt(("é" * 3000).encode("utf-8"), b"").encode("utf-8")) > 2048:
            failures.append("failure excerpt exceeded the UTF-8 byte bound")

        for label in ("create", "read", "checksum", "permission"):
            def fail_write(path, data, label=label):
                raise OSError("injected %s artifact failure" % label)
            if inject_artifact_error(root / ("artifact-" + label), fail_write) == 0:
                failures.append("%s artifact failure returned success" % label)
        os.environ.pop("QA_REPORT_TEST_SECRET", None)

    original_run = qa_report.subprocess.run
    seen = []
    def fake_run(*args, **kwargs):
        seen.append(kwargs)
        return type("Completed", (), {"stdout": b"", "stderr": b"", "returncode": 0})()
    try:
        qa_report.subprocess.run = fake_run
        with tempfile.TemporaryDirectory(prefix="qa-report-shell-") as directory:
            qa_report.execute_profile(profile("shell", "print('ok')"), Path(directory))
    finally:
        qa_report.subprocess.run = original_run
    if len(seen) != 1 or seen[0].get("shell") is not False:
        failures.append("profile execution did not force shell=False")

    with contextlib.redirect_stderr(io.StringIO()):
        if qa_report.main([]) != 2:
            failures.append("no profile did not fail with usage status")

    if failures:
        print("AI-Kit QA reporter FAILED: " + "; ".join(failures))
        return 1
    print("AI-Kit QA reporter OK: fixed matrix, artifacts, compact output, and failure propagation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
