"""Deterministic validation, scheduling, approval, and completion policy."""

from __future__ import annotations

import fnmatch
import hashlib
import os
import json
import re
import sys
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from models import APPROVAL_REQUIRED_RISKS, RISK_LABELS, contract_by_ref, contract_ref, task_by_id
from schemas import PLAN_SCHEMA, SchemaError, validate
from dependencies import CrossFeatureDependencyResolver
from capability_config import resolve_plan as resolve_plan_capabilities


MAX_TASKS = 50
MAX_ATTEMPTS = 3
DISALLOWED_WRITE_ROOTS = {"features", ".project", ".workspace", ".git"}


class PolicyError(RuntimeError):
    """Raised when a proposed plan or transition violates a harness invariant."""


class ApprovalRequired(PolicyError):
    """Raised when a schedulable task needs explicit user authorization."""


class PlanApprovalRequired(ApprovalRequired):
    """Raised when a large plan revision has not been approved."""


class ContractApprovalRequired(ApprovalRequired):
    """Raised when a task consumes a contract that is not approved."""


class ContractStale(PolicyError):
    """Raised when an approved contract source is missing or changed."""


def normalize_path(value: str) -> str:
    raw = str(value).strip().replace("\\", "/")
    path = PurePosixPath(raw)
    if not raw or path.is_absolute() or ".." in path.parts or raw.startswith("/"):
        raise PolicyError("file scope must be a repository-relative path: %s" % value)
    if path.parts and path.parts[0] in DISALLOWED_WRITE_ROOTS:
        raise PolicyError("implementation scope cannot write %s/" % path.parts[0])
    return path.as_posix()


def validate_scope_roots(root: Path, task: Dict[str, Any]) -> None:
    """Reject scope prefixes that traverse symlinks or escape the repository."""

    root = Path(root).resolve()
    for scope in task.get("files", []):
        cursor = root
        for part in PurePosixPath(scope).parts:
            if any(character in part for character in "*?["):
                break
            cursor = cursor / part
            if cursor.is_symlink():
                try:
                    cursor.resolve().relative_to(root)
                except ValueError as exc:
                    raise PolicyError("task scope traverses a symlink outside the repository: %s" % scope) from exc
                # Even an internal link makes mutation attribution ambiguous.
                raise PolicyError("task scope cannot traverse a symlink: %s" % scope)
        try:
            cursor.resolve().relative_to(root)
        except ValueError as exc:
            raise PolicyError("task scope escapes the repository: %s" % scope) from exc


def snapshot_repository(root: Path) -> Dict[str, str]:
    """Hash repository files without following symlinks for mutation attribution."""

    root = Path(root).resolve()
    snapshot: Dict[str, str] = {}
    try:
        for directory, dirnames, filenames in os.walk(str(root), followlinks=False):
            base = Path(directory)
            dirnames[:] = sorted(
                name
                for name in dirnames
                if name
                not in {
                    ".git",
                    "__pycache__",
                    "node_modules",
                    "test-results",
                    "playwright-report",
                    ".workspace",
                    ".pytest_cache",
                }
            )
            for name in list(dirnames):
                candidate = base / name
                if candidate.is_symlink():
                    relative = candidate.relative_to(root).as_posix()
                    snapshot[relative] = "link:" + os.readlink(str(candidate))
                    dirnames.remove(name)
            for name in sorted(filenames):
                path = base / name
                relative = path.relative_to(root).as_posix()
                if path.is_symlink():
                    snapshot[relative] = "link:" + os.readlink(str(path))
                    continue
                digest = hashlib.sha256()
                with path.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
                snapshot[relative] = "sha256:" + digest.hexdigest()
    except OSError as exc:
        raise PolicyError("cannot snapshot repository mutations: %s" % exc) from exc
    return snapshot


def changed_paths(before: Dict[str, str], after: Dict[str, str]) -> List[str]:
    return sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))


def source_digest(root: Path, source: str) -> str:
    """Hash one regular repository file without following a symlink."""

    relative = normalize_path(source)
    root = Path(root).resolve()
    path = root
    for part in PurePosixPath(relative).parts:
        path = path / part
        if path.is_symlink():
            raise ContractStale("contract source traverses a symlink: %s" % relative)
    if not path.is_file():
        raise ContractStale("contract source is missing or not a regular file: %s" % relative)
    try:
        path.resolve().relative_to(root)
    except ValueError as exc:
        raise ContractStale("contract source escapes the repository: %s" % relative) from exc
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ContractStale("cannot hash contract source %s: %s" % (relative, exc)) from exc
    return "sha256:" + digest.hexdigest()


def _unique(values: Iterable[str], label: str) -> List[str]:
    normalized = [str(value).strip() for value in values]
    if len(normalized) != len(set(normalized)):
        raise PolicyError("%s contains duplicates" % label)
    return normalized


def normalize_verification_command(command: Sequence[str], task_id: str) -> List[str]:
    """Accept only bounded test/build argv forms; never accept inline code or a shell."""

    arguments = [str(argument) for argument in command]
    if not arguments or any(not argument for argument in arguments):
        raise PolicyError("%s has an empty verification command" % task_id)
    raw_executable = arguments[0]
    portable_executable = raw_executable.replace("\\", "/")
    executable_path = PurePosixPath(portable_executable)
    if len(executable_path.parts) > 1 or executable_path.is_absolute():
        try:
            is_current_python = Path(raw_executable).resolve() == Path(sys.executable).resolve()
        except OSError:
            is_current_python = False
        if not is_current_python:
            raise PolicyError(
                "%s verification executable must be a trusted bare command" % task_id
            )
    executable = executable_path.name.lower()
    for suffix in (".exe", ".cmd", ".bat"):
        if executable.endswith(suffix):
            executable = executable[: -len(suffix)]
            break

    if re.fullmatch(r"python(?:[0-9]+(?:\.[0-9]+)?)?", executable):
        if any(argument in {"-c", "--command"} for argument in arguments[1:]):
            raise PolicyError("%s verification cannot execute inline Python" % task_id)
        if "-m" in arguments[1:]:
            index = arguments.index("-m")
            module = arguments[index + 1] if index + 1 < len(arguments) else ""
            if module not in {"pytest", "unittest", "compileall"}:
                raise PolicyError("%s verification uses unsupported Python module %s" % (task_id, module))
            return arguments
        scripts = [value for value in arguments[1:] if not value.startswith("-")]
        if not scripts or not normalize_path(scripts[0]).endswith(".py"):
            raise PolicyError("%s Python verification must name a repository .py script" % task_id)
        return arguments

    if executable in {"bash", "sh"}:
        if "-c" in arguments[1:]:
            raise PolicyError("%s verification cannot execute an inline shell" % task_id)
        scripts = [value for value in arguments[1:] if not value.startswith("-")]
        if not scripts or not normalize_path(scripts[0]).endswith(".sh"):
            raise PolicyError("%s shell verification must name a repository .sh script" % task_id)
        return arguments

    unrestricted_test_tools = {"pytest", "ruff", "mypy", "eslint", "tsc"}
    if executable in unrestricted_test_tools:
        return arguments

    verb_allowlist = {
        "cargo": {"build", "check", "clippy", "test"},
        "go": {"build", "test", "vet"},
        "dotnet": {"build", "test"},
        "make": {"build", "check", "lint", "test", "verify"},
    }
    if executable in verb_allowlist:
        verb = next((value for value in arguments[1:] if not value.startswith("-")), "")
        if verb not in verb_allowlist[executable]:
            raise PolicyError("%s verification uses unsupported %s action %s" % (task_id, executable, verb))
        return arguments

    if executable in {"npm", "pnpm", "yarn"}:
        values = [value for value in arguments[1:] if not value.startswith("-")]
        if not values:
            raise PolicyError("%s verification is missing a package script" % task_id)
        if values[0] == "test":
            return arguments
        if values[0] in {"run", "run-script"} and len(values) > 1 and values[1] in {
            "build",
            "check",
            "lint",
            "test",
            "typecheck",
            "verify",
        }:
            return arguments
        raise PolicyError("%s verification uses an unsupported package action" % task_id)

    raise PolicyError("%s verification executable is not allowed: %s" % (task_id, executable))


def validate_verification_command_paths(
    root: Path, command: Sequence[str], task_id: str
) -> None:
    """Require interpreter scripts to be regular, non-symlinked repository files."""

    arguments = [str(argument) for argument in command]
    executable = PurePosixPath(arguments[0].replace("\\", "/")).name.lower()
    for suffix in (".exe", ".cmd", ".bat"):
        if executable.endswith(suffix):
            executable = executable[: -len(suffix)]
            break
    script: Optional[str] = None
    if re.fullmatch(r"python(?:[0-9]+(?:\.[0-9]+)?)?", executable):
        if "-m" not in arguments[1:]:
            script = next(
                (value for value in arguments[1:] if not value.startswith("-")), None
            )
    elif executable in {"bash", "sh"}:
        script = next(
            (value for value in arguments[1:] if not value.startswith("-")), None
        )
    if script is None:
        return

    relative = normalize_path(script)
    repository = Path(root).resolve()
    path = repository
    for part in PurePosixPath(relative).parts:
        path = path / part
        if path.is_symlink():
            raise PolicyError(
                "%s verification script traverses a symlink: %s" % (task_id, relative)
            )
    if not path.is_file():
        raise PolicyError(
            "%s verification script is missing or not a regular file: %s"
            % (task_id, relative)
        )
    try:
        path.resolve().relative_to(repository)
    except ValueError as exc:
        raise PolicyError(
            "%s verification script escapes the repository: %s" % (task_id, relative)
        ) from exc


def normalize_contract_graph(plan: Dict[str, Any], *, validated: bool = False) -> Dict[str, Any]:
    """Validate and normalize optional hierarchy, service, and contract metadata."""

    if not validated:
        try:
            validate(plan, PLAN_SCHEMA)
        except SchemaError as exc:
            raise PolicyError("invalid plan schema: %s" % exc) from exc
    raw_services = plan.get("services", [])
    raw_contracts = plan.get("contracts", [])
    if raw_contracts and not raw_services:
        raise PolicyError("a contract registry requires a service registry")

    services: List[Dict[str, Any]] = []
    service_ids = [service["id"] for service in raw_services]
    if len(service_ids) != len(set(service_ids)):
        raise PolicyError("plan contains duplicate service IDs")
    known_services = set(service_ids)
    data_owners: Dict[str, str] = {}
    path_owners: Dict[str, str] = {}
    for raw in raw_services:
        service_id = raw["id"]
        dependencies = _unique(raw["dependencies"], "%s dependencies" % service_id)
        forbidden = _unique(raw["forbidden_dependencies"], "%s forbidden dependencies" % service_id)
        unknown = sorted((set(dependencies) | set(forbidden)) - known_services)
        if unknown:
            raise PolicyError("service %s references unknown services: %s" % (service_id, ", ".join(unknown)))
        if service_id in dependencies or service_id in forbidden:
            raise PolicyError("service %s cannot depend on or forbid itself" % service_id)
        overlap = sorted(set(dependencies) & set(forbidden))
        if overlap:
            raise PolicyError("service %s both depends on and forbids: %s" % (service_id, ", ".join(overlap)))
        owns_data = _unique(raw["owns_data"], "%s data ownership" % service_id)
        for entity in owns_data:
            if entity in data_owners:
                raise PolicyError(
                    "data entity %s has multiple owners: %s, %s"
                    % (entity, data_owners[entity], service_id)
                )
            data_owners[entity] = service_id
        paths = _unique(
            [normalize_path(value) for value in raw["paths"]], "%s paths" % service_id
        )
        for path in paths:
            for owned_path, owner in path_owners.items():
                if _scope_is_within(owned_path, path) or _scope_is_within(path, owned_path):
                    raise PolicyError(
                        "service paths overlap: %s owns %s and %s owns %s"
                        % (owner, owned_path, service_id, path)
                    )
            path_owners[path] = service_id
        services.append(
            {
                "id": service_id,
                "domain": raw["domain"].strip(),
                "paths": paths,
                "owns_data": owns_data,
                "exposes": _unique(raw["exposes"], "%s exposes" % service_id),
                "consumes": _unique(raw["consumes"], "%s consumes" % service_id),
                "dependencies": dependencies,
                "forbidden_dependencies": forbidden,
            }
        )

    contracts: List[Dict[str, Any]] = []
    references = [contract_ref(raw) for raw in raw_contracts]
    if len(references) != len(set(references)):
        raise PolicyError("plan contains duplicate contract references")
    known_contracts = set(references)
    services_by_id = {service["id"]: service for service in services}
    for raw in raw_contracts:
        reference = contract_ref(raw)
        participants = set(raw["producers"]) | set(raw["consumers"]) | {raw["owner"]}
        unknown = sorted(participants - known_services)
        if unknown:
            raise PolicyError("contract %s references unknown services: %s" % (reference, ", ".join(unknown)))
        if raw["owner"] not in raw["producers"]:
            raise PolicyError("contract %s owner must be one of its producers" % reference)
        if raw["change_type"] == "breaking" and raw["compatibility"] != "none":
            raise PolicyError("breaking contract %s must declare compatibility none" % reference)
        source = normalize_path(raw["source"])
        source_root = PurePosixPath(source).parts[0].lower()
        if source_root in {".ai-kit", ".project", ".workspace", ".git", "features"}:
            raise PolicyError("project contract source cannot use control root %s" % source_root)
        owner_paths = services_by_id[raw["owner"]]["paths"]
        if not _scope_is_within(".contracts", source) and not any(
            _scope_is_within(owner_path, source) for owner_path in owner_paths
        ):
            raise PolicyError(
                "project contract %s source must be under .contracts or owner service paths"
                % reference
            )
        contract = dict(raw)
        contract.update(
            {
                "source": source,
                "producers": _unique(raw["producers"], "%s producers" % reference),
                "consumers": _unique(raw["consumers"], "%s consumers" % reference),
                "invariants": _unique(raw["invariants"], "%s invariants" % reference),
                "verification": _unique(raw["verification"], "%s verification" % reference),
            }
        )
        contracts.append(contract)
    for service in services:
        unknown = sorted((set(service["exposes"]) | set(service["consumes"])) - known_contracts)
        if unknown:
            raise PolicyError("service %s references unknown contracts: %s" % (service["id"], ", ".join(unknown)))
    for contract in contracts:
        reference = contract_ref(contract)
        for producer in contract["producers"]:
            if reference not in services_by_id[producer]["exposes"]:
                raise PolicyError("producer %s must expose %s" % (producer, reference))
        for consumer in contract["consumers"]:
            if reference not in services_by_id[consumer]["consumes"]:
                raise PolicyError("consumer %s must consume %s" % (consumer, reference))
            missing_dependencies = sorted(
                set(contract["producers"])
                - {consumer}
                - set(services_by_id[consumer]["dependencies"])
            )
            if missing_dependencies:
                raise PolicyError(
                    "consumer %s must depend on producers of %s: %s"
                    % (consumer, reference, ", ".join(missing_dependencies))
                )

    return {
        "program_id": plan.get("program_id"),
        "workstream_id": plan.get("workstream_id"),
        "parent_feature": plan.get("parent_feature"),
        "services": services,
        "contracts": contracts,
    }


def normalize_plan(
    plan: Dict[str, Any],
    *,
    size: str = "standard",
    completed_tasks: Optional[Dict[str, Dict[str, Any]]] = None,
    required_requirements: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    try:
        validate(plan, PLAN_SCHEMA)
    except SchemaError as exc:
        raise PolicyError("invalid plan schema: %s" % exc) from exc
    try:
        resolve_plan_capabilities(plan)
    except ValueError as exc:
        raise PolicyError("invalid plan capabilities: %s" % exc) from exc
    graph = normalize_contract_graph(plan, validated=True)
    proposed = plan["tasks"]
    if len(proposed) > MAX_TASKS:
        raise PolicyError("plan exceeds %d tasks" % MAX_TASKS)
    ids = [task["id"] for task in proposed]
    if len(ids) != len(set(ids)):
        raise PolicyError("plan contains duplicate task IDs")
    known_completed = completed_tasks or {}
    required_requirement_ids = _unique(
        required_requirements or [], "required requirements"
    )
    known_requirement_ids = set(required_requirement_ids)
    known_ids = set(ids) | set(known_completed)
    normalized: List[Dict[str, Any]] = []
    services = {service["id"]: service for service in graph["services"]}
    contracts = {contract_ref(contract): contract for contract in graph["contracts"]}
    data_owners = {
        entity: service["id"] for service in graph["services"] for entity in service["owns_data"]
    }
    for raw in proposed:
        task_id = raw["id"]
        dependencies = list(dict.fromkeys(raw["dependencies"]))
        if task_id in dependencies:
            raise PolicyError("%s cannot depend on itself" % task_id)
        unknown = sorted(set(dependencies) - known_ids)
        if unknown:
            raise PolicyError("%s has unknown dependencies: %s" % (task_id, ", ".join(unknown)))
        files = [normalize_path(value) for value in raw["files"]]
        if len(files) != len(set(files)):
            raise PolicyError("%s has duplicate file scopes" % task_id)
        risks = list(dict.fromkeys(raw["risks"]))
        if not set(risks).issubset(RISK_LABELS):
            raise PolicyError("%s has unknown risk labels" % task_id)
        if raw["owner"] == "database" and "database" not in risks:
            raise PolicyError("database-owned task %s must declare database risk" % task_id)
        review_required = bool(raw["review_required"] or size in {"standard", "large"} or risks)
        requirement_refs = _unique(
            raw.get("requirement_refs", []), "%s requirement_refs" % task_id
        )
        unknown_requirements = sorted(set(requirement_refs) - known_requirement_ids)
        if unknown_requirements:
            raise PolicyError(
                "%s references unknown requirements: %s"
                % (task_id, ", ".join(unknown_requirements))
            )
        verification_commands = []
        for command in raw.get("verification_commands", []):
            verification_commands.append(normalize_verification_command(command, task_id))
        verification_profiles = _unique(raw.get("verification_profiles", []), "%s verification_profiles" % task_id)
        remediation_id = raw.get("remediation_id")
        remediation_of = raw.get("remediation_of")
        if (remediation_id is None) != (remediation_of is None):
            raise PolicyError("%s remediation_id and remediation_of must be provided together" % task_id)
        if remediation_id is not None and not re.fullmatch(r"REM-[1-9][0-9]*", str(remediation_id)):
            raise PolicyError("%s has an invalid remediation_id" % task_id)
        if remediation_of is not None and not re.fullmatch(r"T[1-9][0-9]*", str(remediation_of)):
            raise PolicyError("%s has an invalid remediation_of" % task_id)
        contract_reads = _unique(raw.get("contract_reads", []), "%s contract_reads" % task_id)
        contract_writes = _unique(raw.get("contract_writes", []), "%s contract_writes" % task_id)
        produces = _unique(raw.get("produces", []), "%s produces" % task_id)
        referenced = set(contract_reads) | set(contract_writes) | set(produces)
        unknown_contracts = sorted(referenced - set(contracts))
        if unknown_contracts:
            raise PolicyError("%s references unknown contracts: %s" % (task_id, ", ".join(unknown_contracts)))
        overlap = sorted(set(contract_reads) & set(contract_writes))
        if overlap:
            raise PolicyError("%s cannot read and write the same contracts: %s" % (task_id, ", ".join(overlap)))
        service_id = raw.get("service")
        if service_id and service_id not in services:
            raise PolicyError("%s references unknown service %s" % (task_id, service_id))
        if services and raw["owner"] in {"backend", "frontend", "database"} and not service_id:
            raise PolicyError("multi-service task %s must declare one service" % task_id)
        if service_id:
            for reference in contract_reads:
                participants = set(contracts[reference]["producers"]) | set(
                    contracts[reference]["consumers"]
                )
                if service_id not in participants:
                    raise PolicyError(
                        "%s service %s is not a producer or consumer of %s"
                        % (task_id, service_id, reference)
                    )
        if contract_writes:
            if raw["owner"] != "architect":
                raise PolicyError("contract-writing task %s must be owned by architect" % task_id)
            if "public-contract" not in risks:
                raise PolicyError("contract-writing task %s must declare public-contract risk" % task_id)
            for reference in contract_writes:
                source = contracts[reference]["source"]
                if not any(_scope_matches(scope, source) for scope in files):
                    raise PolicyError("%s file scope must include contract source %s" % (task_id, source))
        data_entities = _unique(raw.get("data_entities", []), "%s data_entities" % task_id)
        if data_entities and not service_id:
            raise PolicyError("%s declares data entities without a service" % task_id)
        for entity in data_entities:
            owner = data_owners.get(entity)
            if owner != service_id:
                raise PolicyError(
                    "%s cannot mutate data entity %s owned by %s"
                    % (task_id, entity, owner or "no registered service")
                )
        if services and raw["owner"] == "database" and not data_entities:
            raise PolicyError("database task %s must declare owned data_entities" % task_id)
        deploy_after = _unique(raw.get("deploy_after", []), "%s deploy_after" % task_id)
        unknown_services = sorted(set(deploy_after) - set(services))
        if unknown_services:
            raise PolicyError("%s deploy_after references unknown services: %s" % (task_id, ", ".join(unknown_services)))
        if service_id and service_id in deploy_after:
            raise PolicyError("%s cannot deploy after its own service" % task_id)
        if service_id and raw["owner"] in {"backend", "frontend", "database"}:
            allowed_contract_sources = {contracts[reference]["source"] for reference in contract_writes}
            invalid_files = [
                scope
                for scope in files
                if scope not in allowed_contract_sources
                and not any(_scope_is_within(path, scope) for path in services[service_id]["paths"])
            ]
            if invalid_files:
                raise PolicyError(
                    "%s files escape service %s paths: %s"
                    % (task_id, service_id, ", ".join(invalid_files))
                )
        for reference in produces:
            if service_id and service_id not in contracts[reference]["producers"]:
                raise PolicyError("%s service is not a producer of %s" % (task_id, reference))
        raw_contract_evidence = raw.get("contract_evidence", {})
        contract_evidence = {
            category: _unique(
                raw_contract_evidence.get(category, []),
                "%s contract_evidence.%s" % (task_id, category),
            )
            for category in ("integration", "rollout", "rollback", "reconciliation")
        }
        referenced_kinds = {contracts[reference]["kind"] for reference in referenced}
        required_evidence = []
        if referenced and raw["owner"] == "qa":
            required_evidence.append("integration")
        if referenced and raw["owner"] == "release":
            required_evidence.extend(("rollout", "rollback"))
        if "data" in referenced_kinds and raw["owner"] in {"qa", "release"}:
            required_evidence.append("reconciliation")
        missing_evidence = [category for category in required_evidence if not contract_evidence[category]]
        if missing_evidence:
            raise PolicyError(
                "%s requires contract evidence: %s"
                % (task_id, ", ".join(missing_evidence))
            )
        task = {
            "id": task_id,
            "title": raw["title"].strip(),
            "description": raw["description"].strip(),
            "dependencies": dependencies,
            "acceptance_criteria": [item.strip() for item in raw["acceptance_criteria"]],
            "owner": raw["owner"],
            "scope": raw["scope"],
            "files": files,
            "risks": risks,
            "review_required": review_required,
            "requirement_refs": requirement_refs,
            "verification_commands": verification_commands,
            "verification_profiles": verification_profiles,
            "remediation_id": remediation_id,
            "remediation_of": remediation_of,
            "service": service_id,
            "layer": raw.get("layer") or _default_layer(raw["owner"]),
            "contract_reads": contract_reads,
            "contract_writes": contract_writes,
            "produces": produces,
            "data_entities": data_entities,
            "environments": _unique(raw.get("environments", []), "%s environments" % task_id),
            "integration_tests": _unique(
                raw.get("integration_tests", []), "%s integration_tests" % task_id
            ),
            "contract_evidence": contract_evidence,
            "deploy_after": deploy_after,
            "rollback": raw.get("rollback", "").strip(),
            "approval_required": bool(set(risks) & APPROVAL_REQUIRED_RISKS),
            "state": "proposed",
            "attempts": 0,
            "evidence": [],
            "reviews": [],
        }
        if task_id in known_completed:
            previous = known_completed[task_id]
            contract_keys = (
                "title",
                "description",
                "dependencies",
                "acceptance_criteria",
                "owner",
                "files",
                "risks",
                "requirement_refs",
                "verification_commands",
                "verification_profiles",
                "remediation_id",
                "remediation_of",
                "service",
                "layer",
                "contract_reads",
                "contract_writes",
                "produces",
                "data_entities",
                "contract_evidence",
                "deploy_after",
                "rollback",
            )
            if any(task[key] != previous.get(key) for key in contract_keys):
                raise PolicyError("replan cannot alter completed task %s" % task_id)
            task = previous
        normalized.append(task)
    for task_id, task in known_completed.items():
        if task_id not in ids:
            normalized.insert(0, task)
    _assert_acyclic(normalized)
    _assert_contract_writers(normalized)
    covered_requirements = {
        reference
        for task in normalized
        for reference in task.get("requirement_refs", [])
    }
    missing_requirements = sorted(known_requirement_ids - covered_requirements)
    if missing_requirements:
        raise PolicyError(
            "plan leaves requirements uncovered: %s" % ", ".join(missing_requirements)
        )
    refresh_readiness(normalized)
    return normalized


def validate_remediation_links(
    state: Dict[str, Any], tasks: Sequence[Dict[str, Any]]
) -> None:
    """Validate coordinator-created finding to fix-task relationships."""

    records = state.get("remediations", [])
    if not isinstance(records, list):
        raise PolicyError("state remediations must be an array")
    by_id = {record.get("id"): record for record in records if isinstance(record, dict)}
    by_task = {task.get("id"): task for task in tasks}
    for task in tasks:
        remediation_id = task.get("remediation_id")
        remediation_of = task.get("remediation_of")
        if (remediation_id is None) != (remediation_of is None):
            raise PolicyError("%s remediation link is incomplete" % task.get("id"))
        if remediation_id is None:
            continue
        record = by_id.get(remediation_id)
        if record is None:
            raise PolicyError("%s references missing remediation %s" % (task["id"], remediation_id))
        if record.get("status") != "open":
            raise PolicyError("%s references non-open remediation %s" % (task["id"], remediation_id))
        if record.get("source_task") != remediation_of or remediation_of not in by_task:
            raise PolicyError("%s remediation source task does not match %s" % (task["id"], remediation_id))
        if record.get("fix_task") not in {None, task["id"]}:
            raise PolicyError("remediation %s already links another fix task" % remediation_id)
    for record in records:
        if not isinstance(record, dict):
            continue
        fix_task = record.get("fix_task")
        if fix_task is not None:
            linked = by_task.get(fix_task)
            if linked is None or linked.get("remediation_id") != record.get("id"):
                raise PolicyError("remediation %s fix_task link is inconsistent" % record.get("id"))


def canonical_digest(value: Any) -> str:
    """Return a deterministic digest for an authorization payload."""

    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def plan_revision_digest(state: Dict[str, Any]) -> str:
    """Bind approval to the exact goal, requirements, graph, and plan revision."""

    tasks = []
    protected_task_keys = (
        "id",
        "title",
        "description",
        "dependencies",
        "acceptance_criteria",
        "owner",
        "scope",
        "files",
        "risks",
        "requirement_refs",
        "verification_commands",
        "verification_profiles",
        "remediation_id",
        "remediation_of",
        "service",
        "layer",
        "contract_reads",
        "contract_writes",
        "produces",
        "data_entities",
        "environments",
                "integration_tests",
                "contract_evidence",
        "deploy_after",
        "rollback",
    )
    for task in state.get("tasks", []):
        item = {key: task.get(key) for key in protected_task_keys if key != "verification_profiles"}
        if task.get("verification_profiles"):
            item["verification_profiles"] = task["verification_profiles"]
        if task.get("remediation_id"):
            item["remediation_id"] = task["remediation_id"]
            item["remediation_of"] = task.get("remediation_of")
        tasks.append(item)
    payload = {
        "feature": state.get("feature"),
        "goal": state.get("goal"),
        "requirements": state.get("requirements", []),
        "revision": state.get("plan_revision", 0),
        "services": state.get("services", []),
        "contracts": state.get("contracts", []),
        "tasks": tasks,
    }
    if state.get("feature_dependencies"):
        payload["feature_dependencies"] = state["feature_dependencies"]
    return canonical_digest(payload)


def task_action_digest(state: Dict[str, Any], task: Dict[str, Any]) -> str:
    """Bind risky-task approval to the accepted revision and executable action."""

    payload = {
        "feature": state.get("feature"),
        "revision": state.get("plan_revision", 0),
        "task": task.get("id"),
        "files": task.get("files", []),
        "risks": task.get("risks", []),
        "environments": task.get("environments", []),
        "verification_commands": task.get("verification_commands", []),
        "contract_writes": task.get("contract_writes", []),
        "data_entities": task.get("data_entities", []),
        "rollback": task.get("rollback", ""),
    }
    if task.get("verification_profiles"):
        payload["verification_profiles"] = task["verification_profiles"]
    if task.get("remediation_id"):
        payload["remediation_id"] = task["remediation_id"]
        payload["remediation_of"] = task.get("remediation_of")
    return canonical_digest(payload)


def _default_layer(owner: str) -> str:
    return {
        "architect": "architecture",
        "frontend": "frontend",
        "backend": "backend",
        "database": "database",
        "qa": "integration",
        "reviewer": "integration",
        "documenter": "documentation",
        "release": "operations",
    }[owner]


def _scope_is_within(prefix: str, scope: str) -> bool:
    prefix_parts = PurePosixPath(prefix).parts
    scope_parts = PurePosixPath(scope).parts
    return len(scope_parts) >= len(prefix_parts) and scope_parts[: len(prefix_parts)] == prefix_parts


def _assert_contract_writers(tasks: Sequence[Dict[str, Any]]) -> None:
    writers: Dict[str, str] = {}
    graph = {task["id"]: task.get("dependencies", []) for task in tasks}
    for task in tasks:
        for reference in task.get("contract_writes", []):
            if reference in writers:
                raise PolicyError(
                    "contract %s has multiple writers: %s, %s"
                    % (reference, writers[reference], task["id"])
                )
            writers[reference] = task["id"]
    for task in tasks:
        for reference in set(task.get("contract_reads", [])) | set(task.get("produces", [])):
            writer = writers.get(reference)
            if writer and writer != task["id"] and not _depends_on(task["id"], writer, graph):
                raise PolicyError(
                    "%s must depend on contract writer %s for %s"
                    % (task["id"], writer, reference)
                )


def _depends_on(task_id: str, dependency: str, graph: Dict[str, Sequence[str]]) -> bool:
    pending = list(graph.get(task_id, []))
    visited: Set[str] = set()
    while pending:
        current = pending.pop()
        if current == dependency:
            return True
        if current not in visited:
            visited.add(current)
            pending.extend(graph.get(current, []))
    return False


def _assert_acyclic(tasks: Sequence[Dict[str, Any]]) -> None:
    graph = {task["id"]: task.get("dependencies", []) for task in tasks}
    visiting: Set[str] = set()
    visited: Set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visiting:
            raise PolicyError("plan dependency graph contains a cycle at %s" % task_id)
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in graph.get(task_id, []):
            if dependency not in graph:
                raise PolicyError("%s depends on missing task %s" % (task_id, dependency))
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in graph:
        visit(task_id)


def refresh_readiness(tasks: Sequence[Dict[str, Any]]) -> bool:
    changed = False
    completed = {task["id"] for task in tasks if task.get("state") == "complete"}
    for task in tasks:
        state = task.get("state")
        if state in {"complete", "running", "review", "escalated"}:
            continue
        if int(task.get("attempts", 0)) >= MAX_ATTEMPTS:
            if state != "escalated":
                task["state"] = "escalated"
                changed = True
            continue
        desired = "ready" if set(task.get("dependencies", [])).issubset(completed) else "proposed"
        if state != desired:
            task["state"] = desired
            changed = True
    return changed


def task_is_approved(state: Dict[str, Any], task: Dict[str, Any]) -> bool:
    if not task.get("approval_required"):
        return True
    required = set(task.get("risks", [])) & APPROVAL_REQUIRED_RISKS
    approved: Set[str] = set()
    expected_digest = task_action_digest(state, task)
    for record in state.get("approvals", []):
        if record.get("task") == task.get("id") and record.get("action_digest") == expected_digest:
            approved.update(record.get("risks", []))
    return required.issubset(approved)


def validate_contract_readiness(
    state: Dict[str, Any], task: Dict[str, Any], *, root: Optional[Path]
) -> None:
    references = list(dict.fromkeys(task.get("contract_reads", []) + task.get("produces", [])))
    for reference in references:
        contract = contract_by_ref(state, reference)
        status = contract.get("status")
        if status == "draft":
            raise ContractApprovalRequired("%s requires contract approval: %s" % (task["id"], reference))
        if status == "deprecated":
            raise ContractStale("%s consumes deprecated contract %s; replan required" % (task["id"], reference))
        if root is None:
            raise ContractStale("repository root is required to verify contract %s" % reference)
        actual = source_digest(root, contract["source"])
        if contract.get("source_hash") != actual:
            raise ContractStale(
                "contract %s source hash changed; expected %s, found %s; replan required"
                % (reference, contract.get("source_hash"), actual)
            )


def next_schedulable(
    state: Dict[str, Any], *, root: Optional[Path] = None
) -> Optional[Dict[str, Any]]:
    if state.get("status") == "plan_pending_approval":
        raise PlanApprovalRequired(
            "plan revision %s requires explicit approval" % state.get("plan_revision", 0)
        )
    if state.get("feature_dependencies"):
        if root is None:
            return None
        barriers = CrossFeatureDependencyResolver(root, state["feature"]).resolve(
            state["feature_dependencies"]
        )
        if not all(item.satisfied for item in barriers):
            return None
    refresh_readiness(state.get("tasks", []))
    blocked: List[Dict[str, Any]] = []
    contract_blocks: List[PolicyError] = []
    for task in state.get("tasks", []):
        if task.get("state") != "ready":
            continue
        if not task_is_approved(state, task):
            blocked.append(task)
            continue
        try:
            validate_contract_readiness(state, task, root=root)
        except (ContractApprovalRequired, ContractStale) as exc:
            contract_blocks.append(exc)
            continue
        return task
    if blocked:
        task = blocked[0]
        risks = sorted(set(task.get("risks", [])) & APPROVAL_REQUIRED_RISKS)
        raise ApprovalRequired("%s requires approval for: %s" % (task["id"], ", ".join(risks)))
    if contract_blocks:
        raise contract_blocks[0]
    return None


def changed_files_in_scope(task: Dict[str, Any], changed_files: Iterable[str]) -> bool:
    scopes = task.get("files", [])
    for value in changed_files:
        try:
            path = normalize_path(value)
        except PolicyError:
            return False
        if not any(_scope_matches(scope, path) for scope in scopes):
            return False
    return True


def _scope_matches(scope: str, path: str) -> bool:
    scope_parts = PurePosixPath(scope).parts
    path_parts = PurePosixPath(path).parts

    def match(scope_index: int, path_index: int) -> bool:
        if scope_index == len(scope_parts):
            return path_index == len(path_parts)
        pattern = scope_parts[scope_index]
        if pattern == "**":
            return match(scope_index + 1, path_index) or (
                path_index < len(path_parts) and match(scope_index, path_index + 1)
            )
        return (
            path_index < len(path_parts)
            and fnmatch.fnmatchcase(path_parts[path_index], pattern)
            and match(scope_index + 1, path_index + 1)
        )

    return match(0, 0)


def validate_success(task: Dict[str, Any], result: Dict[str, Any]) -> None:
    if result.get("outcome") != "success":
        raise PolicyError("execution result is not successful")
    if not changed_files_in_scope(task, result.get("changed_files", [])):
        raise PolicyError("execution changed a file outside the task scope")
    passes = {
        item.get("criterion")
        for item in result.get("evidence", [])
        if item.get("result") == "pass"
    }
    required = list(task.get("acceptance_criteria", []))
    for criteria in task.get("contract_evidence", {}).values():
        required.extend(criteria)
    missing = [criterion for criterion in required if criterion not in passes]
    if missing:
        raise PolicyError("execution lacks passing evidence for: %s" % "; ".join(missing))


def task_complete(state: Dict[str, Any], task_id: str) -> bool:
    return task_by_id(state, task_id).get("state") == "complete"
