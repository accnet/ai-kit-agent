#!/usr/bin/env python3
"""QA profile contract and safety mechanics."""

import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".ai/harness"))
sys.path.insert(1, str(ROOT / ".ai/scripts"))

from qa_profiles import validate  # noqa: E402
from qa_profiles import QaProfileError, QaProfileResolver  # noqa: E402


def profile(**overrides):
    value = {
        "command": ["bash", "check.sh"],
        "cwd": "tests",
        "timeout_seconds": 60,
        "evidence": {"feature": "fixture", "task": "T1", "artifacts": ["stdout"]},
    }
    value.update(overrides)
    return {"schema_version": 1, "profiles": {"check": value}}


def run_case(data, root, directory="tests"):
    (root / directory).mkdir(parents=True, exist_ok=True)
    path = root / "profiles.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return validate(root, path)


def main():
    failures = []
    temporary = tempfile.TemporaryDirectory()
    root = Path(temporary.name)
    if run_case(profile(), root):
        failures.append("valid profile was rejected")
    if not run_case(profile(command="bash check.sh"), root):
        failures.append("shell-string command was accepted")
    if not run_case(profile(cwd="../outside"), root):
        failures.append("escaping cwd was accepted")
    if not run_case(profile(timeout_seconds=10), root):
        failures.append("timeout below safety bound was accepted")
    if not run_case(profile(evidence={"feature": "fixture", "task": "T1"}), root):
        failures.append("incomplete evidence was accepted")
    if not run_case(profile(command=["bash", "check.sh;touch"]), root):
        failures.append("shell separator in command argument was accepted")
    if not run_case({"schema_version": 1, "profiles": {}}, root):
        failures.append("empty profile registry was accepted")
    registry = root / "profiles.json"
    registry.write_text(json.dumps(profile()), encoding="utf-8")
    resolved = QaProfileResolver(root, registry).resolve(["check"])
    if resolved[0].command != ("bash", "check.sh") or resolved[0].cwd != "tests":
        failures.append("profile did not resolve to immutable argv/cwd")
    try:
        QaProfileResolver(root, registry).resolve(["check", "check"])
        failures.append("duplicate profile request was accepted")
    except QaProfileError:
        pass
    try:
        QaProfileResolver(root, registry).resolve(["missing"])
        failures.append("unknown profile request was accepted")
    except QaProfileError:
        pass
    temporary.cleanup()
    if failures:
        print("AI-Kit QA profile mechanics FAILED: " + "; ".join(failures))
        return 1
    print("AI-Kit QA profile mechanics OK: schema, cwd, command, timeout, and evidence safety")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
