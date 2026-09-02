"""Project-owned multi-service contract registry (separate from .ai/contracts)."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Dict

KINDS = {"schema", "api", "event", "data", "workflow"}
REF = re.compile(r"^[a-z][a-z0-9.-]*[a-z0-9]@[0-9]+\.[0-9]+\.[0-9]+$")
SERVICE_ID = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
CONTROL_ROOTS = {".ai", ".project", ".workspace", ".git"}


class ProjectContractError(ValueError):
    pass


def _relative(value: Any, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value.strip():
        raise ProjectContractError("%s must be a non-empty repository-relative path" % label)
    raw = value.strip().replace("\\", "/")
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ProjectContractError("%s escapes repository" % label)
    if path.parts[0].lower() in CONTROL_ROOTS:
        raise ProjectContractError("%s uses reserved control root %s" % (label, path.parts[0]))
    return path


def _resolved(root: Path, relative: PurePosixPath, label: str, *, regular_file: bool = False) -> Path:
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ProjectContractError("%s traverses a symlink" % label)
    try:
        resolved = cursor.resolve()
    except OSError as exc:
        raise ProjectContractError("%s cannot be resolved" % label) from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ProjectContractError("%s escapes repository" % label) from exc
    if regular_file and not resolved.is_file():
        raise ProjectContractError("%s is missing or not a regular file" % label)
    return resolved


def _string_list(value: Any, label: str, *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value):
        raise ProjectContractError("%s must be %sa string array" % (label, "a non-empty " if nonempty else ""))
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ProjectContractError("%s must contain non-empty strings" % label)
    normalized = [item.strip() for item in value]
    if len(normalized) != len(set(normalized)):
        raise ProjectContractError("%s contains duplicates" % label)
    return normalized


def load_registry(root: Path, path: str = ".contracts/registry.json") -> Dict[str, Any]:
    root = Path(root).resolve()
    registry_relative = _relative(path, "registry path")
    if not registry_relative.parts or registry_relative.parts[0] != ".contracts":
        raise ProjectContractError("project registry must live under .contracts/")
    registry = _resolved(root, registry_relative, "registry path", regular_file=True)
    try:
        value = json.loads(registry.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectContractError("invalid project contract registry") from exc
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ProjectContractError("registry schema_version must be 1")
    services = value.get("services", [])
    contracts = value.get("contracts", [])
    if not isinstance(services, list) or not isinstance(contracts, list):
        raise ProjectContractError("registry services/contracts must be arrays")

    service_paths: dict[str, list[PurePosixPath]] = {}
    for service in services:
        if not isinstance(service, dict) or not isinstance(service.get("id"), str) or not SERVICE_ID.fullmatch(service["id"]):
            raise ProjectContractError("registry contains an invalid service id")
        service_id = service["id"]
        if service_id in service_paths:
            raise ProjectContractError("registry contains duplicate service id: %s" % service_id)
        declared = _string_list(service.get("contract_paths", []), "%s contract_paths" % service_id)
        paths = [_relative(item, "%s contract path" % service_id) for item in declared]
        for declared_path in paths:
            _resolved(root, declared_path, "%s contract path" % service_id)
        service_paths[service_id] = paths

    refs = set()
    for item in contracts:
        if not isinstance(item, dict) or item.get("kind") not in KINDS:
            raise ProjectContractError("unsupported or malformed project contract kind")
        ref = "%s@%s" % (item.get("id"), item.get("version"))
        if not REF.fullmatch(ref) or ref in refs:
            raise ProjectContractError("invalid or duplicate contract reference: %s" % ref)
        refs.add(ref)
        owner = item.get("owner")
        if not isinstance(owner, str) or owner not in service_paths:
            raise ProjectContractError("contract %s has an unknown owner" % ref)
        producers = _string_list(item.get("producers"), "%s producers" % ref, nonempty=True)
        consumers = _string_list(item.get("consumers", []), "%s consumers" % ref)
        participants = set(producers) | set(consumers)
        unknown = participants - set(service_paths)
        if unknown:
            raise ProjectContractError("contract %s references unknown service" % ref)
        if owner not in producers:
            raise ProjectContractError("contract %s owner must be a producer" % ref)

        source_relative = _relative(item.get("source"), "contract %s source" % ref)
        allowed_roots = [PurePosixPath(".contracts")] + service_paths[owner]
        if not any(source_relative == allowed or allowed in source_relative.parents for allowed in allowed_roots):
            raise ProjectContractError("contract %s source is outside owner-declared roots" % ref)
        source = _resolved(root, source_relative, "contract %s source" % ref, regular_file=True)
        try:
            content = source.read_bytes()
        except OSError as exc:
            raise ProjectContractError("contract %s source cannot be read" % ref) from exc
        item["source_hash"] = "sha256:" + hashlib.sha256(content).hexdigest()
    return value


def load_contract_document(root: Path, entry: Dict[str, Any]) -> Dict[str, Any]:
    root = Path(root).resolve()
    relative = _relative(entry.get("source"), "contract source")
    source = _resolved(root, relative, "contract source", regular_file=True)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectContractError("invalid contract document") from exc
    if not isinstance(value, dict):
        raise ProjectContractError("contract document must be an object")
    return value


def adapter_for(kind: str):
    try:
        from .adapters.api import ApiAdapter
        from .adapters.data import DataAdapter
        from .adapters.event import EventAdapter
        from .adapters.json_schema import JsonSchemaAdapter
        from .adapters.workflow import WorkflowAdapter
    except ImportError:  # direct script/test import with harness on sys.path
        from adapters.api import ApiAdapter
        from adapters.data import DataAdapter
        from adapters.event import EventAdapter
        from adapters.json_schema import JsonSchemaAdapter
        from adapters.workflow import WorkflowAdapter
    adapters = {"schema": JsonSchemaAdapter, "api": ApiAdapter, "event": EventAdapter,
                "data": DataAdapter, "workflow": WorkflowAdapter}
    try:
        return adapters[kind]()
    except KeyError as exc:
        raise ProjectContractError("unsupported project contract kind") from exc


def validate_contracts(root: Path, path: str = ".contracts/registry.json") -> Dict[str, Any]:
    registry = load_registry(root, path)
    results = []
    for entry in registry["contracts"]:
        document = load_contract_document(root, entry)
        result = adapter_for(entry["kind"]).validate(document)
        results.append({"ref": "%s@%s" % (entry["id"], entry["version"]), **result})
    return {"valid": True, "results": results}
