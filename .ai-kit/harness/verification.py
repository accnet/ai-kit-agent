"""Local, artifact-backed verification; never reuse evidence from an earlier run."""

from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any, Dict, List

from policy import canonical_digest, PolicyError, snapshot_repository, validate_verification_command_paths
from qa_profiles import QaProfileError, QaProfileResolver


def _load_reporter():
    path = Path(__file__).resolve().parents[1] / "scripts" / "qa_report.py"
    spec = importlib.util.spec_from_file_location("_harness_qa_report", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


reporter = _load_reporter()


def _failure(kind: str, detail: str) -> Dict[str, Any]:
    return {
        "passed": False, "exit_code": None, "timed_out": False,
        "failure_kind": kind,
        "failure_excerpt": reporter.bounded_excerpt(b"", detail.encode("utf-8")),
    }


def _artifact_directory(root: Path) -> Path:
    directory = root
    for name in (".workspace", "qa"):
        directory = directory / name
        if directory.is_symlink():
            raise OSError("verification artifact directory cannot be a symlink")
        directory.mkdir(mode=0o700, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="verification-", dir=str(directory)))


def run_verification(task: Dict[str, Any], root: Path, artifact_root: Path) -> List[Dict[str, Any]]:
    """Coalesce duplicate declarations, retaining one evidence record per check."""
    root, artifact_root = root.resolve(), artifact_root.resolve()
    try:
        profiles = QaProfileResolver(root).resolve(task["verification_profiles"]) if task.get("verification_profiles") else ()
        timeouts = {}
        for profile in profiles:
            key = (profile.command, str((root / profile.cwd).resolve()))
            if key in timeouts and timeouts[key] != profile.timeout_seconds:
                raise QaProfileError("conflicting timeouts for the same verification command")
            timeouts[key] = profile.timeout_seconds
    except QaProfileError as exc:
        return [dict(_failure("configuration", str(exc)), profile_id=None, policy_error=str(exc))]

    checks = []
    for command in task.get("verification_commands", []):
        checks.append({
            "command": list(command), "cwd": ".", "inline": True,
            "timeout_seconds": timeouts.get((tuple(command), str(root)), 120),
        })
    for profile in profiles:
        checks.append({
            "profile_id": profile.identifier, "command": list(profile.command),
            "cwd": profile.cwd, "timeout_seconds": profile.timeout_seconds,
            "metadata": profile.evidence_metadata(),
        })
    if not checks:
        return []

    try:
        snapshot = canonical_digest(snapshot_repository(root))
        run_dir = _artifact_directory(artifact_root)
    except (OSError, PolicyError) as exc:
        return [_failure("environment", str(exc))]

    runtime = {
        "platform": sys.platform, "python": sys.version,
        "environment_digest": canonical_digest(dict(os.environ)),
    }
    records: List[Dict[str, Any]] = []
    completed: Dict[str, Dict[str, Any]] = {}
    for check in checks:
        command = check["command"]
        identity = {
            "command": command, "cwd": str((root / check["cwd"]).resolve()),
            "timeout_seconds": check["timeout_seconds"], "source_snapshot": snapshot,
            "runtime": runtime, "executable": shutil.which(command[0]),
        }
        digest = canonical_digest(identity)
        declaration = {key: value for key, value in check.items() if key != "inline"}
        if digest in completed:
            record = dict(completed[digest], **declaration)
            record["reused_in_batch"] = True
            record["duration_ms"] = 0
            records.append(record)
            continue
        record = dict(declaration, source_snapshot=snapshot, runtime=runtime,
                      check_digest=digest, reused_in_batch=False)
        try:
            if check.get("inline"):
                validate_verification_command_paths(root, command, task["id"])
            name = "check-%03d" % (len(completed) + 1)
            result = reporter.execute_profile(
                reporter.Profile(name, tuple(command), check["cwd"], check["timeout_seconds"]),
                run_dir, root=root,
            )
            artifacts = {}
            streams = []
            for stream in ("stdout", "stderr"):
                path = Path(result[stream]["path"])
                if not path.is_absolute():
                    path = reporter.ROOT / path
                streams.append(path.read_bytes())
                artifacts[stream] = dict(result[stream], path=path.relative_to(artifact_root).as_posix())
            output = streams[0] + b"\n" + streams[1]
            record.update({
                "exit_code": result["returncode"], "timed_out": result["timed_out"],
                "duration_ms": int(result["duration_seconds"] * 1000),
                "output_digest": "sha256:" + hashlib.sha256(output).hexdigest(),
                "output_bytes": len(output), "artifacts": artifacts,
                "failure_kind": result["failure_kind"], "passed": result["status"] == 0,
            })
            if result.get("failure_excerpt"):
                record["failure_excerpt"] = result["failure_excerpt"]
            after = canonical_digest(snapshot_repository(root))
            record["source_snapshot_after"] = after
            if after != snapshot:
                record.update(_failure("repository_mutation", "verification mutated repository files"))
        except PolicyError as exc:
            record.update(_failure("policy", str(exc)))
            record["policy_error"] = str(exc)
        except OSError as exc:
            record.update(_failure("artifact", str(exc)))
        records.append(record)
        if not record["passed"]:
            break
        completed[digest] = record

    manifest = {
        "schema_version": 1, "task": task["id"], "state": "complete",
        "source_snapshot": snapshot, "runtime": runtime, "results": records,
        "metrics": {
            "declared_checks": len(checks), "evidence_records": len(records),
            "executed_checks": sum("artifacts" in item and not item["reused_in_batch"] for item in records),
            "duplicate_references": sum(item["reused_in_batch"] for item in records),
            "output_bytes": sum(item.get("output_bytes", 0) for item in records if not item["reused_in_batch"]),
            "llm_usage": None,
        },
    }
    try:
        manifest_path = run_dir / "run.json"
        reporter.write_private_json(manifest_path, manifest)
        for record in records:
            record["artifact_manifest"] = manifest_path.relative_to(artifact_root).as_posix()
    except OSError as exc:
        records.append(_failure("artifact", str(exc)))
    return records
