#!/usr/bin/env python3
"""Canonical-first and legacy task-state resolution tests."""

import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".ai-kit" / "scripts"))
from task_state import TaskStateError, resolve  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        feature = root / ".project" / "demo"
        feature.mkdir(parents=True)
        (feature / "tasks.md").write_text("- [ ] T1 Task | owner: backend | scope: S | needs: - | files: src/a.py\n", encoding="utf-8")
        legacy = resolve(root, "demo")
        assert legacy["source"] == "tasks.md" and not legacy["canonical"]
        state = {"feature": "demo", "tasks": [{"id": "T1", "title": "Task", "owner": "backend", "scope": "S", "dependencies": [], "files": ["src/a.py"], "state": "ready", "attempts": 0}]}
        (feature / "state.json").write_text(json.dumps(state), encoding="utf-8")
        canonical = resolve(root, "demo")
        assert canonical["source"] == "state.json" and canonical["canonical"]
        (feature / "state.json").write_text("{broken", encoding="utf-8")
        try:
            resolve(root, "demo")
        except TaskStateError:
            pass
        else:
            raise AssertionError("malformed canonical state must not fall back")
    print("AI-Kit task-state resolver OK: canonical precedence and fail-closed fallback")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
