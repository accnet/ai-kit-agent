#!/usr/bin/env python3
"""Regression tests for AI-Kit session and worker-policy consistency checks."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".ai/scripts/consistency.py"


def write_fixture(root: Path, *, valid: bool, isolated: bool = True) -> None:
    (root / ".ai").mkdir(parents=True, exist_ok=True)
    (root / ".project/demo").mkdir(parents=True, exist_ok=True)
    (root / ".workspace").mkdir(exist_ok=True)
    (root / ".ai/config.json").write_text(json.dumps({
        "orchestration": {"enabled": True, "require_worktree_per_worker": True},
        "execution": {"isolated_worktree": {"required": isolated}},
    }), encoding="utf-8")
    (root / ".project/INDEX.md").write_text(
        "| Feature | State | Source | Updated |\n| demo | active | plan.md | today |\n", encoding="utf-8"
    )
    task = "T1" if valid else "T9"
    (root / ".project/demo/tasks.md").write_text(
        "- [ ] T1 Build | owner: backend | scope: S | needs: - | files: src/\n", encoding="utf-8"
    )
    (root / ".workspace/session.md").write_text(
        f"feature: demo\ntask: {task}\nphase: implementation\n", encoding="utf-8"
    )


def run(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["python3", str(SCRIPT), "--root", str(root)], text=True, capture_output=True, check=False)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="ai-kit-consistency-") as directory:
        root = Path(directory)
        write_fixture(root, valid=True)
        valid = run(root)
        write_fixture(root, valid=False, isolated=False)
        invalid = run(root)
        (root / ".workspace/session.md").write_text("feature: ../../outside\ntask: T1\n", encoding="utf-8")
        traversal = run(root)
    checks = [
        (valid.returncode == 0, "valid worker policy and session pass"),
        (invalid.returncode != 0 and "isolated_worktree.required=true" in invalid.stdout, "contradictory worktree policy fails"),
        ("does not exist" in invalid.stdout, "stale session task fails"),
        (traversal.returncode != 0 and "safe project identifier" in traversal.stdout, "session path traversal fails closed"),
    ]
    for passed, label in checks:
        print(("PASS" if passed else "FAIL") + ": " + label)
    return 0 if all(passed for passed, _ in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
