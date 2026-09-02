#!/usr/bin/env python3
"""Guard the canonical/legacy state authority boundary."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    assert (ROOT / ".ai" / "scripts" / "task_state.py").is_file()
    assert not (ROOT / ".ai" / "tests" / "test_grid_first_contracts.py").exists()
    resolver = (ROOT / ".ai" / "scripts" / "task_state.py").read_text(encoding="utf-8")
    assert "if state_path.exists()" in resolver
    assert "raise TaskStateError(\"malformed canonical state" in resolver
    assert "return _legacy(tasks_path, feature)" in resolver
    # The project contract suite must remain outside the kit test manifest.
    manifest = (ROOT / ".ai" / "tests" / "manifest.json").read_text(encoding="utf-8")
    assert "test_grid_first_contracts.py" not in manifest
    print("AI-Kit state authority contract OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
