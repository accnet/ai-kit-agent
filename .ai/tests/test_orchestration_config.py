#!/usr/bin/env python3
"""Configuration contract tests for native-worker orchestration policy."""

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".ai" / "harness"))

from cli import load_config  # noqa: E402
from engine import EngineError  # noqa: E402


def load_fixture(kit_config):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / ".ai" / "harness").mkdir(parents=True)
        (root / ".ai" / "config.json").write_text(
            json.dumps(kit_config), encoding="utf-8"
        )
        harness_config = (ROOT / ".ai" / "harness" / "config.json").read_text(
            encoding="utf-8"
        )
        (root / ".ai" / "harness" / "config.json").write_text(
            harness_config, encoding="utf-8"
        )
        return load_config(root)


def main():
    base = json.loads((ROOT / ".ai" / "config.json").read_text(encoding="utf-8"))
    failures = []

    try:
        loaded = load_config(ROOT)
        policy = loaded["kit_policy"]["orchestration"]
        expected = {
            "mode": "ide-native-workers",
            "enabled": True,
            "max_workers": 4,
            "require_dag": True,
            "require_disjoint_files": True,
            "coordinator_owns_task_state": True,
            "require_worktree_per_worker": True,
        }
        if policy != expected:
            failures.append("repository policy does not match the approved v1 contract")
        if loaded["kit_policy"]["execution"]["task_cli"]["enabled"] is not False:
            failures.append("orchestration changed task_cli activation")
    except Exception as error:  # pragma: no cover - assertion reporting
        failures.append("valid repository config rejected: %s" % error)

    invalid = []
    malformed = deepcopy(base)
    malformed.pop("orchestration")
    invalid.append(("missing orchestration policy", malformed))
    malformed = deepcopy(base)
    malformed["orchestration"]["mode"] = "api-workers"
    invalid.append(("unsupported scheduler mode", malformed))
    malformed = deepcopy(base)
    malformed["orchestration"]["max_workers"] = 5
    invalid.append(("worker cap above four", malformed))
    malformed = deepcopy(base)
    malformed["orchestration"]["max_workers"] = True
    invalid.append(("boolean worker cap", malformed))
    malformed = deepcopy(base)
    malformed["orchestration"]["require_dag"] = False
    invalid.append(("disabled DAG requirement", malformed))
    malformed = deepcopy(base)
    malformed["orchestration"]["provider"] = "grok"
    invalid.append(("provider leakage", malformed))
    for name, fixture in invalid:
        try:
            load_fixture(fixture)
        except EngineError:
            continue
        except Exception as error:  # pragma: no cover - assertion reporting
            failures.append("%s raised unexpected %s" % (name, type(error).__name__))
        else:
            failures.append(name + " unexpectedly accepted")

    if failures:
        print("AI-Kit orchestration config FAILED: " + "; ".join(failures))
        return 1
    print("AI-Kit orchestration config OK: valid policy + %d invalid fixtures" % len(invalid))
    return 0


if __name__ == "__main__":
    sys.exit(main())
