#!/usr/bin/env python3
"""Coordinator ownership, locking, worker cap, and transition mechanics."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATE = ROOT / ".ai-kit" / "scripts" / "orchestrate.py"
NEXT_TASK = ROOT / ".ai-kit" / "scripts" / "next-task.sh"


CONFIG = {
    "schema_version": 1,
    "orchestration": {
        "mode": "ide-native-workers",
        "enabled": True,
        "max_workers": 2,
        "require_dag": True,
        "require_disjoint_files": True,
        "coordinator_owns_task_state": True,
        "require_worktree_per_worker": True,
    },
}


def task(task_id, files):
    return "- [ ] %s Build %s | owner: backend | scope: S | needs: - | files: %s" % (task_id, task_id, files)


def run(root, *args, check=False, env=None):
    command = [sys.executable, str(ORCHESTRATE), *args, "--root", str(root), "--json"]
    return subprocess.run(command, text=True, capture_output=True, check=check, env=env)


def bash_path(path):
    """Translate a native Windows path for the repository's WSL bash boundary."""
    resolved = Path(path).resolve()
    if sys.platform == "win32":
        drive = resolved.drive.rstrip(":").lower()
        return "/mnt/%s/%s" % (drive, resolved.as_posix().split(":/", 1)[1])
    return str(resolved)


def main():
    failures = []
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / ".project" / "fixture").mkdir(parents=True)
        (root / ".ai-kit").mkdir()
        (root / ".project" / "fixture" / "tasks.md").write_text(
            "# Tasks\n\n"
            + "\n".join(
                [task("T1", "one.php"), task("T2", "two.php"), task("T3", "three.php")]
            )
            + "\n",
            encoding="utf-8",
        )
        (root / ".ai-kit" / "config.json").write_text(json.dumps(CONFIG), encoding="utf-8")
        # No log-event helper is needed for the state assertions.
        report = run(root, "fixture", "status")
        status = json.loads(report.stdout)
        if status["dispatchable"] != ["T1", "T2"]:
            failures.append("dispatchable list did not honor max_workers")

        marker = root / "waiter-acquired"
        scripts = ROOT / ".ai-kit" / "scripts"
        holder_code = (
            "import pathlib,sys; sys.path.insert(0,sys.argv[1]); import orchestrate; "
            "root=pathlib.Path(sys.argv[2]); _,_,lock=orchestrate.locked_state(root,'fixture'); "
            "print('locked',flush=True); sys.stdin.readline(); "
            "orchestrate._release_lock(lock); lock.close()"
        )
        waiter_code = (
            "import pathlib,sys; sys.path.insert(0,sys.argv[1]); import orchestrate; "
            "root=pathlib.Path(sys.argv[2]); marker=pathlib.Path(sys.argv[3]); "
            "_,_,lock=orchestrate.locked_state(root,'fixture'); marker.write_text('acquired'); "
            "orchestrate._release_lock(lock); lock.close()"
        )
        holder = subprocess.Popen(
            [sys.executable, "-c", holder_code, str(scripts), str(root)],
            text=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        if holder.stdout.readline().strip() != "locked":
            failures.append("lock holder did not acquire the coordinator lock")
        waiter = subprocess.Popen(
            [sys.executable, "-c", waiter_code, str(scripts), str(root), str(marker)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        try:
            waiter.wait(timeout=0.3)
            failures.append("contending coordinator lock did not serialize")
        except subprocess.TimeoutExpired:
            if marker.exists():
                failures.append("contending coordinator entered the locked section")
        finally:
            holder.stdin.write("\n")
            holder.stdin.flush()
            holder.wait(timeout=5)
        waiter.wait(timeout=5)
        if not marker.exists() or waiter.returncode != 0:
            failures.append("contending coordinator did not acquire after release")

        worker_claim = subprocess.run(
            ["bash", bash_path(NEXT_TASK), "fixture", "--claim", "T1", "--instance", "worker"],
            cwd=str(root),
            text=True,
            capture_output=True,
        )
        if worker_claim.returncode == 0 or "coordinator-only" not in worker_claim.stderr:
            failures.append("worker claim was not rejected")
        original = (root / ".project" / "fixture" / "tasks.md").read_text(encoding="utf-8")
        if "status: in-progress" in original:
            failures.append("worker rejection changed tasks.md")

        claimed = run(root, "fixture", "claim", "T1", "--lease", "lease-1", "--instance", "worker-1", check=True)
        if json.loads(claimed.stdout)["status"] != "claimed":
            failures.append("coordinator claim did not succeed")
        state_path = root / ".workspace" / "orchestration" / "fixture.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state["active"]["T1"]["files"] != ["one.php"]:
            failures.append("coordinator lease did not retain the declared file scope")
        conflict = run(root, "fixture", "claim", "T1", "--lease", "lease-2", "--instance", "worker-2")
        if conflict.returncode == 0:
            failures.append("double claim was accepted")

        claimed_second = run(root, "fixture", "claim", "T2", "--lease", "lease-2", "--instance", "worker-2", check=True)
        if json.loads(claimed_second.stdout)["active"] != ["T1", "T2"]:
            failures.append("second independent claim did not succeed")
        capped = run(root, "fixture", "claim", "T3", "--lease", "lease-3", "--instance", "worker-3")
        if capped.returncode == 0 or "max_workers" not in (capped.stdout + capped.stderr):
            failures.append("worker cap was not enforced")

        completed = run(root, "fixture", "complete", "T1", "--lease", "lease-1", "--evidence", "offline test", check=True)
        if json.loads(completed.stdout)["active"] != ["T2"]:
            failures.append("completion did not release the owning lease")
        text = (root / ".project" / "fixture" / "tasks.md").read_text(encoding="utf-8")
        if "- [x] T1" not in text or "status: in-progress" in text.splitlines()[2]:
            failures.append("completion did not atomically mark T1 done")

    if failures:
        print("AI-Kit orchestration state FAILED: " + "; ".join(failures))
        return 1
    print("AI-Kit orchestration state OK: worker guard, lease ownership, locking, cap, and completion")
    return 0


if __name__ == "__main__":
    sys.exit(main())
