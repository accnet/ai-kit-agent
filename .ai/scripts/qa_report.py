#!/usr/bin/env python3
"""Run fixed QA commands with compact, artifact-backed output."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_ROOT = ROOT / ".workspace" / "qa"
MAX_FAILURE_EXCERPT_BYTES = 2_048


@dataclass(frozen=True)
class Profile:
    name: str
    command: Tuple[str, ...]
    cwd: str
    timeout_seconds: int


PROFILES: Dict[str, Profile] = {
    "ai-kit": Profile("ai-kit", ("bash", ".ai/tests/run.sh"), ".", 900),
    "theme": Profile("theme", ("bash", "tests/run.sh"), ".", 900),
    "browser": Profile(
        "browser",
        ("npm", "--prefix", "tests/e2e", "test", "--", "--project=chromium"),
        ".",
        1200,
    ),
}
ALL_PROFILE_NAMES: Tuple[str, ...] = ("ai-kit", "theme", "browser")
REDACTIONS = (
    (re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"), "[REDACTED_AWS_ACCESS_KEY]"),
    (re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"\b(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{16,}\b"), "[REDACTED_API_KEY]"),
    (
        re.compile(r"(?i)\b(password|passwd|secret|token|api[_-]?key|authorization)\b(\s*[:=]\s*)([^\s\"']+)"),
        r"\1\2[REDACTED]",
    ),
)


class QaReportError(ValueError):
    pass


def artifact_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def redact(value: str) -> str:
    for pattern, replacement in REDACTIONS:
        value = pattern.sub(replacement, value)
    return value


def bounded_excerpt(stdout: bytes, stderr: bytes) -> str:
    combined = (stdout + (b"\n" if stdout and stderr else b"") + stderr).decode(
        "utf-8", errors="replace"
    )
    encoded = redact(combined).strip().encode("utf-8")
    if len(encoded) <= MAX_FAILURE_EXCERPT_BYTES:
        return encoded.decode("utf-8")
    marker = b"[... output truncated ...]\n"
    tail = encoded[-(MAX_FAILURE_EXCERPT_BYTES - len(marker)) :]
    while tail and (tail[0] & 0xC0) == 0x80:
        tail = tail[1:]
    return marker.decode("ascii") + tail.decode("utf-8")


def sha256_and_readback(path: Path) -> Tuple[str, int]:
    first = path.read_bytes()
    digest = hashlib.sha256(first).hexdigest()
    reread = path.read_bytes()
    if first != reread or digest != hashlib.sha256(reread).hexdigest():
        raise OSError("artifact read-back checksum mismatch: %s" % path)
    return digest, len(first)


def write_private_bytes(path: Path, data: bytes) -> Tuple[str, int]:
    with path.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(path, 0o600)
    return sha256_and_readback(path)


def write_private_json(path: Path, data: object) -> None:
    write_private_bytes(path, (json.dumps(data, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def create_artifact_dir() -> Path:
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    os.chmod(ARTIFACT_ROOT, 0o700)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = ARTIFACT_ROOT / ("run-%s-%s-%s" % (stamp, os.getpid(), secrets.token_hex(4)))
    run_dir.mkdir(mode=0o700)
    os.chmod(run_dir, 0o700)
    return run_dir


def resolve_profiles(requested: Sequence[str]) -> Tuple[Profile, ...]:
    values = list(requested) or ["all"]
    if len(values) != len(set(values)):
        raise QaReportError("duplicate QA profile requested")
    unknown = [value for value in values if value not in PROFILES and value != "all"]
    if unknown:
        raise QaReportError("unknown QA profile: %s" % ", ".join(unknown))
    if "all" in values and len(values) != 1:
        raise QaReportError("profile 'all' cannot be combined with another profile")
    names: Iterable[str] = ALL_PROFILE_NAMES if values == ["all"] else values
    return tuple(PROFILES[name] for name in names)


def return_status(returncode: Optional[int], timed_out: bool) -> int:
    if timed_out:
        return 124
    if returncode is None:
        return 125
    return 128 + abs(returncode) if returncode < 0 else returncode


def execute_profile(profile: Profile, run_dir: Path) -> dict:
    started_at = datetime.now(timezone.utc)
    started = time.monotonic()
    stdout = b""
    stderr = b""
    returncode: Optional[int] = None
    timed_out = False
    launch_error: Optional[str] = None
    try:
        completed = subprocess.run(
            profile.command,
            cwd=ROOT / profile.cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            shell=False,
            timeout=profile.timeout_seconds,
        )
        stdout, stderr, returncode = completed.stdout, completed.stderr, completed.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = exc.stdout if isinstance(exc.stdout, bytes) else (exc.stdout or "").encode()
        stderr = exc.stderr if isinstance(exc.stderr, bytes) else (exc.stderr or "").encode()
        stderr += (b"\n" if stderr else b"") + (
            "QA profile timed out after %s seconds\n" % profile.timeout_seconds
        ).encode("utf-8")
    except OSError as exc:
        launch_error = "%s: %s" % (type(exc).__name__, exc)
        stderr = ("QA profile could not start: %s\n" % launch_error).encode("utf-8")

    stdout_path = run_dir / (profile.name + ".stdout.log")
    stderr_path = run_dir / (profile.name + ".stderr.log")
    stdout_sha256, stdout_bytes = write_private_bytes(stdout_path, stdout)
    stderr_sha256, stderr_bytes = write_private_bytes(stderr_path, stderr)
    status = return_status(returncode, timed_out)
    result = {
        "profile": profile.name,
        "command": list(profile.command),
        "cwd": profile.cwd,
        "timeout_seconds": profile.timeout_seconds,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(time.monotonic() - started, 3),
        "returncode": returncode,
        "status": status,
        "timed_out": timed_out,
        "launch_error": redact(launch_error) if launch_error else None,
        "stdout": {"path": artifact_relative(stdout_path), "sha256": stdout_sha256, "bytes": stdout_bytes},
        "stderr": {"path": artifact_relative(stderr_path), "sha256": stderr_sha256, "bytes": stderr_bytes},
    }
    if status:
        result["failure_excerpt"] = bounded_excerpt(stdout, stderr)
    return result


def write_manifest(run_dir: Path, requested: Sequence[str], results: List[dict], state: str) -> Path:
    manifest = run_dir / "run.json"
    write_private_json(
        manifest,
        {
            "schema_version": 1,
            "state": state,
            "requested_profiles": list(requested) or ["all"],
            "executed_profiles": [result["profile"] for result in results],
            "artifact_directory": artifact_relative(run_dir),
            "first_failure_status": next((result["status"] for result in results if result["status"]), 0),
            "results": results,
        },
    )
    return manifest


def print_summary(results: Sequence[dict], manifest: Path, verbose: bool) -> None:
    print("QA %s: %s profile(s)" % ("PASS" if all(result["status"] == 0 for result in results) else "FAIL", len(results)))
    for result in results:
        print(
            "%s %s exit=%s duration=%ss"
            % ("PASS" if result["status"] == 0 else "FAIL", result["profile"], result["status"], result["duration_seconds"])
        )
        if result["status"]:
            print("  command: %s" % " ".join(result["command"]))
            print("  cwd: %s" % result["cwd"])
            print("  artifact: %s" % artifact_relative(manifest.parent / (result["profile"] + ".stdout.log")))
            excerpt = result.get("failure_excerpt", "")
            if excerpt:
                print("  excerpt:")
                for line in excerpt.splitlines():
                    print("    " + line)
    print("artifact manifest: %s" % artifact_relative(manifest))
    if verbose:
        for result in results:
            for stream in ("stdout", "stderr"):
                data = (ROOT / result[stream]["path"]).read_bytes().decode("utf-8", errors="replace")
                print("----- %s %s (stored artifact) -----" % (result["profile"], stream))
                sys.stdout.write(data)
                if data and not data.endswith("\n"):
                    print()


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true", help="print full stored output after the summary")
    parser.add_argument("--profile", action="append", default=[], metavar="PROFILE")
    parser.add_argument("profiles", nargs="*", metavar="PROFILE")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    requested = [*args.profile, *args.profiles]
    try:
        profiles = resolve_profiles(requested)
    except QaReportError as exc:
        print("QA REPORT ERROR: %s" % exc, file=sys.stderr)
        return 2
    try:
        run_dir = create_artifact_dir()
        results: List[dict] = []
        write_manifest(run_dir, requested, results, "running")
        for profile in profiles:
            results.append(execute_profile(profile, run_dir))
            write_manifest(run_dir, requested, results, "running")
        manifest = write_manifest(run_dir, requested, results, "complete")
    except OSError as exc:
        print("QA REPORT ERROR: artifact capture failed: %s" % redact(str(exc)), file=sys.stderr)
        return 125
    print_summary(results, manifest, args.verbose)
    return next((result["status"] for result in results if result["status"]), 0)


if __name__ == "__main__":
    raise SystemExit(main())
