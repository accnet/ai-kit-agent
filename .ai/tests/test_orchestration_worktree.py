#!/usr/bin/env python3
"""Worker manifest and isolated worktree handoff checks."""

import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".ai" / "scripts"))

from worker_manifest import ManifestError, validate  # noqa: E402


def manifest(path, files=None):
    return {
        "kind": "worker-manifest",
        "contractVersion": 1,
        "coordinator_lease": "lease-t2",
        "task": "T2",
        "files": files or ["src/two.php"],
        "worktree": {"path": str(path), "isolated": True, "clean": True},
        "worker": {"id": "worker-t2", "scheduler": "codex-ide"},
    }


def git_clean(path):
    import subprocess

    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "fixture@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Fixture"], check=True)
    (path / "README").write_text("clean", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "README"], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "base"], check=True)


def main():
    failures = []
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / "repo"
        root.mkdir()
        (root / ".project" / "fixture").mkdir(parents=True)
        (root / ".ai").mkdir()
        (root / ".ai" / "config.json").write_text(
            json.dumps({"orchestration": {"max_workers": 4}}), encoding="utf-8"
        )
        (root / ".project" / "fixture" / "tasks.md").write_text(
            "# Tasks\n- [x] T1 Done | owner: backend | scope: S | needs: - | files: one.php\n"
            "- [ ] T2 Build | owner: backend | scope: S | needs: T1 | files: src/two.php\n",
            encoding="utf-8",
        )
        worktree = Path(temporary) / "worker-t2"
        worktree.mkdir()
        git_clean(worktree)
        state_dir = root / ".workspace" / "orchestration"
        state_dir.mkdir(parents=True)
        (state_dir / "fixture.json").write_text(
            json.dumps(
                {
                    "contractVersion": 1,
                    "feature": "fixture",
                    "active": {"T2": {"lease": "lease-t2", "instance": "worker-t2"}},
                    "history": [],
                }
            ),
            encoding="utf-8",
        )

        valid = validate(root, "fixture", manifest(worktree))
        if not valid["valid"]:
            failures.append("valid isolated worker manifest rejected")
        for name, broken in (
            ("primary checkout", manifest(root)),
            ("scope mismatch", manifest(worktree, ["src/other.php"])),
            ("non-IDE scheduler", {**manifest(worktree), "worker": {"id": "w", "scheduler": "api"}}),
            ("lease instance mismatch", {**manifest(worktree), "worker": {"id": "other-worker", "scheduler": "codex-ide"}}),
        ):
            try:
                validate(root, "fixture", broken)
            except ManifestError:
                continue
            failures.append(name + " unexpectedly accepted")
        (worktree / "dirty.txt").write_text("dirty", encoding="utf-8")
        try:
            validate(root, "fixture", manifest(worktree))
        except ManifestError:
            pass
        else:
            failures.append("dirty worktree unexpectedly accepted")

    if failures:
        print("AI-Kit worker manifest FAILED: " + "; ".join(failures))
        return 1
    print("AI-Kit worker manifest OK: contract, scope, scheduler, isolation, and cleanliness")
    return 0


if __name__ == "__main__":
    sys.exit(main())
