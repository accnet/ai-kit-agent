"""Self-contained prompt projections with independently guarded local artifacts."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import shutil
import stat
import tempfile
from typing import Any, Dict, Optional

from policy import PolicyError, canonical_digest, plan_revision_digest, snapshot_repository
from verification import reporter


class EvidenceError(PolicyError):
    """Evidence cannot safely support the requested provider call."""


def evidence_payload(task: Dict[str, Any]) -> Dict[str, Any]:
    return {key: task.get(key, []) for key in ("evidence", "verification_evidence", "reviews")}


def source_identity(root: Path) -> str:
    # Coordinator state changes when results are saved; it is not tested source.
    return canonical_digest({key: value for key, value in snapshot_repository(root).items()
                             if not key.startswith(".project/")})


def verification_binding(state: Dict[str, Any], task: Dict[str, Any], root: Path,
                         artifact_root: Optional[Path] = None, *, manifest_bytes=None) -> Dict[str, Any]:
    manifests = {record["artifact_manifest"] for record in task.get("verification_evidence", [])
                 if record.get("artifact_manifest")}
    manifest_bytes = {} if manifest_bytes is None else manifest_bytes
    for relative in sorted(manifests):
        _safe_path(artifact_root or root, relative)
        if relative not in manifest_bytes:
            manifest_bytes[relative] = _read(artifact_root or root, relative)
    return {"source": source_identity(root), "plan": plan_revision_digest(state),
            "evidence": canonical_digest(task.get("verification_evidence", [])),
            "attempt": task.get("attempts", 0), "run": state.get("run", {}).get("id"),
            "manifests": {relative: _sha(manifest_bytes[relative])
                          for relative in sorted(manifests)}}


def _sanitized(value: Any, *, artifacts: bool = False) -> Any:
    if isinstance(value, dict):
        return {key: _sanitized(item, artifacts=key == "artifacts")
                for key, item in value.items()
                if key not in {"environment", "env", "raw_logs", "raw_stdout", "raw_stderr"}
                and (artifacts or key not in {"stdout", "stderr"})}
    if isinstance(value, (list, tuple)):
        return [_sanitized(item, artifacts=artifacts) for item in value]
    return reporter.redact(value) if isinstance(value, str) else value


def _detail(value: str) -> str:
    return reporter.bounded_excerpt(str(value).encode("utf-8"), b"")


def _sanitized_task(task: Dict[str, Any]) -> Dict[str, Any]:
    view = _sanitized(task)
    for key in ("acceptance_criteria", "contract_evidence", "description", "files",
                "dependencies", "risks", "requirement_refs", "verification_commands",
                "verification_profiles"):
        if key in task:
            view[key] = copy.deepcopy(task[key])
    return view


def _inline_eligible(task):
    return (not task.get("verification_evidence") and not task.get("reviews") and
            not task.get("verification_binding", {}).get("manifests") and
            all(isinstance(item, dict) and isinstance(item.get("detail", ""), str) and
                len(item.get("detail", "").encode("utf-8")) <= reporter.MAX_FAILURE_EXCERPT_BYTES and
                not any(item.get(key) for key in ("artifacts", "artifact", "artifact_ref"))
                for item in task.get("evidence", [])))


def compact_task(task: Dict[str, Any], reference: Optional[Dict[str, Any]] = None,
                 *, freshness: str = "unavailable") -> Dict[str, Any]:
    """Keep unknown task fields; compact only fields whose semantics are defined."""
    view = _sanitized_task(task)
    if reference is None and _inline_eligible(task):
        view.pop("verification_binding", None)
        for original, selected in zip(task.get("evidence", []), view.get("evidence", [])):
            if "criterion" in original:
                selected["criterion"] = original["criterion"]
            selected["detail"] = _detail(original.get("detail", ""))
        view["evidence_view"] = {"mode": "inline", "freshness": None}
        if task.get("verification_commands") or task.get("verification_profiles"):
            view["evidence_view"]["not_run"] = True
        return view
    records = task.get("verification_evidence", [])
    criteria = list(task.get("acceptance_criteria", []))
    criterion_refs = list(range(len(criteria)))
    for contract, values in task.get("contract_evidence", {}).items():
        for index, value in enumerate(values):
            if value not in criteria:
                criteria.append(value)
                criterion_refs.append(["contract_evidence", contract, index])
    checks, declarations, identities = [], [], {}
    for record in records:
        identity = canonical_digest({key: record.get(key) for key in (
            "check_digest", "command", "cwd", "source_snapshot", "passed", "failure_kind",
            "exit_code", "artifacts", "artifact_manifest")})
        if identity not in identities:
            check_id = "V%d" % (len(checks) + 1)
            identities[identity] = check_id
            item = {key: _sanitized(record[key]) for key in (
                "command", "cwd", "timeout_seconds", "exit_code", "timed_out", "failure_kind", "policy_error")
                    if key in record}
            item.update(id=check_id, status="pass" if record.get("passed") else "fail",
                        attribution=freshness if record.get("artifacts") else "unavailable")
            if record.get("check_digest"):
                item["digest"] = record["check_digest"]
            if record.get("failure_excerpt"):
                item["failure_excerpt"] = _detail(record["failure_excerpt"])
            checks.append(item)
        declarations.append({"check": identities[identity],
                             **({"profile_id": record["profile_id"]} if record.get("profile_id") else {})})
    remaining = list(records)
    for command in task.get("verification_commands", []):
        match = next((record for record in remaining if not record.get("profile_id")
                      and record.get("command") == command), None)
        if match is None:
            declarations.append({"command": command, "status": "not-run"})
        else:
            remaining.remove(match)
    for profile in task.get("verification_profiles", []):
        if not any(record.get("profile_id") == profile for record in records):
            declarations.append({"profile_id": profile, "status": "not-run"})

    coverage = []
    for index, criterion in enumerate(criteria):
        reported = []
        for item in task.get("evidence", []):
            if item.get("criterion") != criterion:
                continue
            command = item.get("command")
            links = [check["id"] for check in checks if command and
                     (command == check.get("command") or
                      command == shlex.join(check.get("command", []))) and
                     ("cwd" not in item or item["cwd"] == check.get("cwd", "."))]
            detail = _detail(item.get("detail", ""))
            reported.append({"result": item.get("result", "unknown"), "detail": detail,
                             "linkage": "explicit" if len(links) == 1 else
                             ("manual" if not command else "unverified"),
                             "checks": links if len(links) == 1 else []})
        coverage.append({"id": "C%d" % (index + 1), "criterion_ref": criterion_refs[index],
                         "reported": reported or [{"result": "unavailable"}]})

    # Review findings have no resolution flag today: keep all findings visible.
    reviews = [{"verdict": item.get("verdict"), "summary": _detail(item.get("summary", "")),
                "findings": _sanitized(item.get("findings", []))}
               for item in task.get("reviews", [])]
    for key in ("evidence", "verification_evidence", "reviews", "verification_binding"):
        view.pop(key, None)
    view["evidence_view"] = {"version": 1, "freshness": freshness, "coverage": coverage,
                             "checks": checks, "declarations": declarations, "reviews": reviews}
    if reference:
        view["evidence_view"]["package"] = reference
    return view


def _safe_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or "\\" in relative or ":" in relative:
        raise EvidenceError("invalid artifact path")
    parts = PurePosixPath(relative).parts
    if (PurePosixPath(relative).is_absolute() or ".." in parts or
            tuple(parts[:2]) != (".workspace", "qa")):
        raise EvidenceError("artifact escapes coordinator QA namespace")
    cursor = root
    for part in parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise EvidenceError("artifact path traverses a symlink")
    if not cursor.resolve().is_relative_to(root):
        raise EvidenceError("artifact escapes root")
    return cursor


def _read(root: Path, relative: str) -> bytes:
    try:
        path = _safe_path(root, relative)
        if not path.is_file():
            raise EvidenceError("artifact is missing or not a regular file: %s" % relative)
        return path.read_bytes()
    except OSError as exc:
        raise EvidenceError("cannot read artifact: %s" % relative) from exc


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _new_directory(root: Path) -> Path:
    for relative in (".workspace", ".workspace/qa"):
        directory = root / relative
        if directory.is_symlink():
            raise EvidenceError("package directory traverses a symlink")
        directory.mkdir(mode=0o700, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="context-", dir=str(root / ".workspace/qa")))


def _tree(root: Path, directory: Path) -> Dict[str, str]:
    _safe_path(root, directory.relative_to(root).as_posix())
    if not directory.is_dir():
        raise EvidenceError("evidence package disappeared")
    result = {}
    for base, directories, files in os.walk(str(directory), followlinks=False):
        for name in directories + files:
            path = Path(base) / name
            _safe_path(root, path.relative_to(root).as_posix())
            relative = path.relative_to(directory).as_posix()
            mode = path.stat().st_mode
            if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise EvidenceError("evidence package contains a special file")
            result[relative] = "directory" if stat.S_ISDIR(mode) else _sha(path.read_bytes())
    return result


class EvidencePackage:
    def __init__(self, view: Dict[str, Any], roots: list, originals: list):
        self.view, self.roots, self.originals = view, roots, originals
        self.expected = [_tree(root, directory) for root, directory in roots]

    def validate(self) -> None:
        try:
            for (root, directory), expected in zip(self.roots, self.expected):
                if _tree(root, directory) != expected:
                    raise EvidenceError("provider mutated evidence package")
            for root, relative, digest in self.originals:
                if _sha(_read(root, relative)) != digest:
                    raise EvidenceError("canonical evidence artifact changed")
        except OSError as exc:
            raise EvidenceError("evidence package integrity check failed") from exc

    def cleanup_projection(self) -> None:
        if len(self.roots) > 1:
            root, directory = self.roots[-1]
            _safe_path(root, directory.relative_to(root).as_posix())
            try:
                shutil.rmtree(directory)
            except OSError as exc:
                raise EvidenceError("cannot remove disposable evidence projection") from exc


def prepare_evidence(state: Dict[str, Any], task: Dict[str, Any], artifact_root: Path,
                     provider_root: Path, *, review: bool = False) -> EvidencePackage:
    """Validate canonical records, then project private artifacts into readable scope."""
    artifact_root, provider_root = artifact_root.resolve(), provider_root.resolve()
    if _inline_eligible(task):
        if review and (task.get("verification_commands") or task.get("verification_profiles")):
            raise EvidenceError("review verification evidence is stale or unavailable; verify again")
        return EvidencePackage(compact_task(task), [], [])
    records = task.get("verification_evidence", [])
    binding = task.get("verification_binding")
    read_cache = {}

    def read_original(relative):
        if relative not in read_cache:
            read_cache[relative] = _read(artifact_root, relative)
        return read_cache[relative]

    try:
        expected = verification_binding(state, task, provider_root, artifact_root, manifest_bytes=read_cache)
    except (PolicyError, OSError) as exc:
        raise EvidenceError("cannot attribute verification evidence: %s" % exc) from exc
    if binding and binding.get("manifests", {}) != expected["manifests"]:
        raise EvidenceError("verification manifest hash changed")
    freshness = "current" if review and records and binding == expected else (
        "historical" if records and binding else "unavailable")
    if review and (task.get("verification_commands") or task.get("verification_profiles")):
        if freshness != "current" or not records or any(not item.get("passed") for item in records):
            raise EvidenceError("review verification evidence is stale or unavailable; verify again")
        preview = compact_task(task, freshness=freshness)
        if any(item.get("status") == "not-run" for item in preview["evidence_view"]["declarations"]):
            raise EvidenceError("review has required verification checks not run")

    originals, copies, manifests = {}, {}, {}
    try:
        for record in records:
            artifacts = record.get("artifacts", {})
            if record.get("passed") and not artifacts:
                if review:
                    raise EvidenceError("passing legacy check lacks artifact attribution")
                continue
            if not artifacts:
                continue
            relative = record.get("artifact_manifest")
            if not relative:
                raise EvidenceError("check lacks its verification manifest")
            if relative not in manifests:
                raw = read_original(relative)
                manifest = json.loads(raw.decode("utf-8"))
                if manifest.get("task") != task["id"] or manifest.get("state") != "complete":
                    raise EvidenceError("verification manifest ownership/state mismatch")
                manifests[relative] = manifest
                originals[relative] = (artifact_root, relative, _sha(raw))
                copies[relative] = json.dumps(_sanitized(manifest), ensure_ascii=False).encode("utf-8")
            manifest = manifests[relative]
            plain = {key: value for key, value in record.items() if key != "artifact_manifest"}
            if canonical_digest(plain) not in {canonical_digest(item) for item in manifest.get("results", [])}:
                raise EvidenceError("canonical check differs from verification manifest")
            for artifact in artifacts.values():
                raw = read_original(artifact["path"])
                if _sha(raw) != artifact["sha256"] or len(raw) != artifact["bytes"]:
                    raise EvidenceError("verification log hash/size mismatch")
                originals[artifact["path"]] = (artifact_root, artifact["path"], _sha(raw))
                copies[artifact["path"]] = raw
        directory = _new_directory(artifact_root)
        files, locations = {}, {}
        for index, (relative, raw) in enumerate(copies.items()):
            name = "artifact-%03d%s" % (index, ".json" if relative in manifests else ".log")
            reporter.write_private_bytes(directory / name, raw)
            files[name] = {"sha256": _sha(raw), "bytes": len(raw)}
            locations[relative] = name
        sanitized_task = _sanitized_task(task)
        reporter.write_private_json(directory / "task.json", sanitized_task)
        task_bytes = (directory / "task.json").read_bytes()
        files["task.json"] = {"sha256": _sha(task_bytes), "bytes": len(task_bytes)}
        manifest = {"schema_version": 1, "feature": state.get("feature"), "task": task["id"],
                    "plan": plan_revision_digest(state), "attempt": task.get("attempts", 0),
                    "run": state.get("run", {}).get("id"), "source": expected["source"],
                    "patch": task.get("workspace", {}).get("patch_digest"),
                    "evidence_digest": canonical_digest(evidence_payload(task)),
                    "artifact_root": canonical_digest(str(artifact_root)), "freshness": freshness,
                    "files": files, "artifact_locations": locations}
        reporter.write_private_json(directory / "manifest.json", manifest)
        roots = [(artifact_root, directory)]
        readable = directory
        if provider_root != artifact_root:
            readable = _new_directory(provider_root)
            for path in directory.iterdir():
                reporter.write_private_bytes(readable / path.name, path.read_bytes())
            roots.append((provider_root, readable))
        reference = {"manifest": (readable / "manifest.json").relative_to(provider_root).as_posix(),
                     "sha256": _sha((readable / "manifest.json").read_bytes()),
                     "source": expected["source"], "evidence_digest": manifest["evidence_digest"]}
        view = compact_task(task, reference, freshness=freshness)
        return EvidencePackage(view, roots, list(originals.values()))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise EvidenceError("cannot prepare attributed evidence package: %s" % exc) from exc
