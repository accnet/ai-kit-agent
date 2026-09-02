#!/usr/bin/env python3
import json, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.capability_config import resolve
def main():
    value = resolve(["database_safety"], ["db/migrations"])
    assert value["capabilities"] == sorted(value["capabilities"])
    assert value["provenance"]["proposal"] == ["database_safety"]
    root = Path(__file__).resolve().parents[2]
    command = [sys.executable, str(root / ".ai/harness/cli.py"), "--root", str(root), "effective-config", "--capability", "database_safety", "--signal", "db/migrations"]
    completed = subprocess.run(command, cwd=str(root), capture_output=True, text=True, timeout=10)
    assert completed.returncode == 0, completed.stderr
    output = json.loads(completed.stdout)
    assert output["providers"]["implementation"]["provider"] == "grok"
    assert output["timeouts"]["implementation_seconds"] == 1200
    assert output["permissions"]["destructive_approval_required"] is True
    human = subprocess.run(command + ["--human"], cwd=str(root), capture_output=True, text=True, timeout=10)
    assert human.returncode == 0 and "Capabilities:" in human.stdout and "Timeout:" in human.stdout
    print("Effective capability config OK")
if __name__ == "__main__": main()
