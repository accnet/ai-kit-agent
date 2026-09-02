"""Versioned state constructors shared by the harness control plane."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any, Dict, Iterable, List, Optional


SCHEMA_VERSION = 1
RUN_STATES = {"idle", "running", "paused", "needs_input", "cancelled", "completed"}
FEATURE_STATES = {
    "initialized",
    "plan_pending_approval",
    "planned",
    "running",
    "awaiting_review",
    "blocked",
    "needs_replan",
    "complete",
}
TASK_STATES = {
    "proposed",
    "ready",
    "running",
    "review",
    "complete",
    "failed",
    "escalated",
}
MEMORY_KINDS = {"working", "episodic", "semantic"}
RISK_LABELS = {
    "database",
    "destructive",
    "production",
    "credentials",
    "external-write",
    "security",
    "public-contract",
}
APPROVAL_REQUIRED_RISKS = {
    "database",
    "destructive",
    "production",
    "credentials",
    "external-write",
}
WORKSPACE_PHASES = {
    "created",
    "implemented",
    "verified",
    "review",
    "promoted",
    "discarded",
    "failed",
}
REMEDIATION_GATES = {"qa", "review"}
REMEDIATION_SEVERITIES = {"minor", "major", "blocker"}
REMEDIATION_STATES = {"open", "resolved", "dismissed"}


def utc_now() -> str:
    """Return a stable, timezone-qualified UTC timestamp."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _strings(values: Optional[Iterable[str]]) -> List[str]:
    return [str(value).strip() for value in (values or []) if str(value).strip()]


def new_state(
    feature: str,
    goal: str,
    *,
    constraints: Optional[Iterable[str]] = None,
    verification: Optional[Iterable[str]] = None,
    requirements: Optional[Iterable[Dict[str, str]]] = None,
    size: str = "standard",
    review_policy: str = "active-agent",
) -> Dict[str, Any]:
    """Construct the canonical initial state for a harness-managed feature."""

    now = utc_now()
    normalized_requirements = [
        {"id": str(item["id"]).strip(), "text": str(item["text"]).strip()}
        for item in (requirements or [])
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "feature": feature,
        "goal": str(goal).strip(),
        "constraints": _strings(constraints),
        "verification": _strings(verification),
        "requirements": normalized_requirements,
        "size": size,
        "status": "initialized",
        "plan_revision": 0,
        "event_sequence": 0,
        "review_policy": review_policy,
        "program_id": None,
        "workstream_id": None,
        "parent_feature": None,
        "feature_dependencies": [],
        "capability_decision": None,
        "feature_dependency_results": [],
        "remediations": [],
        "services": [],
        "contracts": [],
        "contract_approvals": [],
        "tasks": [],
        "approvals": [],
        "plan_approvals": [],
        "provider_history": [],
        "run": {
            "id": None,
            "state": "idle",
            "started_at": None,
            "updated_at": now,
            "reason": "",
        },
        "created_at": now,
        "updated_at": now,
        "last_transition": {"event": "initialized", "at": now},
    }


def touch(state: Dict[str, Any], event: str, **details: Any) -> None:
    """Update common transition metadata in-place."""

    now = utc_now()
    state["updated_at"] = now
    state["last_transition"] = {"event": event, "at": now, **details}


def task_by_id(state: Dict[str, Any], task_id: str) -> Dict[str, Any]:
    for task in state.get("tasks", []):
        if task.get("id") == task_id:
            return task
    raise KeyError("unknown task: %s" % task_id)


def contract_ref(contract: Dict[str, Any]) -> str:
    """Return the canonical version-qualified identifier for a contract."""

    return "%s@%s" % (contract["id"], contract["version"])


def contract_by_ref(state: Dict[str, Any], reference: str) -> Dict[str, Any]:
    for contract in state.get("contracts", []):
        if contract_ref(contract) == reference:
            return contract
    raise KeyError("unknown contract: %s" % reference)


def validate_state(state: Dict[str, Any]) -> None:
    """Reject structurally corrupted canonical state before transitions use it."""

    if not isinstance(state, dict) or state.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported or missing state schema version")
    if not isinstance(state.get("feature"), str) or not isinstance(state.get("goal"), str):
        raise ValueError("state feature and goal must be strings")
    if state.get("status") not in FEATURE_STATES:
        raise ValueError("unknown feature state")
    requirements = state.get("requirements", [])
    if not isinstance(requirements, list):
        raise ValueError("state requirements must be an array")
    requirement_ids = []
    for requirement in requirements:
        if not isinstance(requirement, dict):
            raise ValueError("every requirement must be an object")
        requirement_id = requirement.get("id")
        if not isinstance(requirement_id, str) or not re.fullmatch(
            r"R[1-9][0-9]*", requirement_id
        ):
            raise ValueError("every requirement needs an R<n> string id")
        if not isinstance(requirement.get("text"), str) or not requirement["text"].strip():
            raise ValueError("every requirement needs non-empty text")
        requirement_ids.append(requirement_id)
    if len(requirement_ids) != len(set(requirement_ids)):
        raise ValueError("state contains duplicate requirement ids")
    run = state.get("run", {"state": "idle"})
    if not isinstance(run, dict) or run.get("state") not in RUN_STATES:
        raise ValueError("state run must contain a known lifecycle state")
    if run.get("id") is not None and not isinstance(run.get("id"), str):
        raise ValueError("state run id must be null or a string")
    for key in ("plan_revision", "event_sequence"):
        value = state.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError("%s must be a non-negative integer" % key)
    tasks = state.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError("state tasks must be an array")
    ids = []
    for task in tasks:
        if not isinstance(task, dict) or not isinstance(task.get("id"), str):
            raise ValueError("every state task must have a string id")
        ids.append(task["id"])
        if task.get("state") not in TASK_STATES:
            raise ValueError("unknown task state for %s" % task["id"])
        attempts = task.get("attempts")
        if not isinstance(attempts, int) or isinstance(attempts, bool) or attempts < 0:
            raise ValueError("invalid attempts for %s" % task["id"])
        for key in (
            "dependencies",
            "acceptance_criteria",
            "files",
            "risks",
            "evidence",
            "reviews",
            "requirement_refs",
            "verification_commands",
            "verification_profiles",
        ):
            if key not in task and key in {"requirement_refs", "verification_commands", "verification_profiles"}:
                continue
            if not isinstance(task.get(key), list):
                raise ValueError("%s.%s must be an array" % (task["id"], key))
        for command in task.get("verification_commands", []):
            if not isinstance(command, list) or not command or not all(
                isinstance(argument, str) and argument for argument in command
            ):
                raise ValueError("%s verification command must be a non-empty string array" % task["id"])
        if len(task.get("verification_profiles", [])) != len(set(task.get("verification_profiles", []))):
            raise ValueError("duplicate verification profiles for %s" % task["id"])
        remediation_id = task.get("remediation_id")
        remediation_of = task.get("remediation_of")
        if remediation_id is not None and (
            not isinstance(remediation_id, str) or not re.fullmatch(r"REM-[1-9][0-9]*", remediation_id)
        ):
            raise ValueError("invalid remediation_id for %s" % task["id"])
        if remediation_of is not None and (
            not isinstance(remediation_of, str) or not re.fullmatch(r"T[1-9][0-9]*", remediation_of)
        ):
            raise ValueError("invalid remediation_of for %s" % task["id"])
        if (remediation_id is None) != (remediation_of is None):
            raise ValueError("%s remediation_id and remediation_of must be provided together" % task["id"])
        unknown_requirements = set(task.get("requirement_refs", [])) - set(requirement_ids)
        if unknown_requirements:
            raise ValueError(
                "%s references unknown requirements: %s"
                % (task["id"], ", ".join(sorted(unknown_requirements)))
            )
        for review in task["reviews"]:
            if isinstance(review, dict) and review.get("policy") not in {
                None,
                "active-agent",
                "independent",
            }:
                raise ValueError("invalid review policy for %s" % task["id"])
        workspace = task.get("workspace")
        if workspace is not None:
            if not isinstance(workspace, dict):
                raise ValueError("%s.workspace must be an object" % task["id"])
            for key in (
                "repository",
                "workspace",
                "feature",
                "task",
                "run_id",
                "base_commit",
            ):
                if not isinstance(workspace.get(key), str) or not workspace[key]:
                    raise ValueError("%s.workspace.%s must be a non-empty string" % (task["id"], key))
            if workspace.get("feature") != state.get("feature") or workspace.get("task") != task["id"]:
                raise ValueError("%s workspace ownership does not match state" % task["id"])
            if workspace.get("phase") not in WORKSPACE_PHASES:
                raise ValueError("invalid workspace phase for %s" % task["id"])
            if not isinstance(workspace.get("allowed_dirty_paths", []), list) or not all(
                isinstance(path, str) and path for path in workspace.get("allowed_dirty_paths", [])
            ):
                raise ValueError("%s.workspace.allowed_dirty_paths must be a string array" % task["id"])
            if not isinstance(workspace.get("changed_files", []), list) or not all(
                isinstance(path, str) and path for path in workspace.get("changed_files", [])
            ):
                raise ValueError("%s.workspace.changed_files must be a string array" % task["id"])
            patch_digest = workspace.get("patch_digest")
            if patch_digest is not None and not (
                isinstance(patch_digest, str)
                and re.fullmatch(r"sha256:[0-9a-f]{64}", patch_digest)
            ):
                raise ValueError("invalid workspace patch digest for %s" % task["id"])
        for key in (
            "contract_reads",
            "contract_writes",
            "produces",
            "data_entities",
            "environments",
            "integration_tests",
            "deploy_after",
        ):
            if not isinstance(task.get(key, []), list):
                raise ValueError("%s.%s must be an array" % (task["id"], key))
        if not set(task["risks"]).issubset(RISK_LABELS):
            raise ValueError("unknown risk label for %s" % task["id"])
    if len(ids) != len(set(ids)):
        raise ValueError("state contains duplicate task ids")
    known = set(ids)
    if any(set(task["dependencies"]) - known for task in tasks):
        raise ValueError("state contains an unknown task dependency")
    if not isinstance(state.get("feature_dependencies", []), list):
        raise ValueError("state feature_dependencies must be an array")
    decision = state.get("capability_decision")
    if decision is not None:
        if not isinstance(decision, dict) or decision.get("schema_version") != 1:
            raise ValueError("state capability_decision must use schema_version 1")
        if not isinstance(decision.get("capabilities"), list) or not isinstance(decision.get("provenance"), dict):
            raise ValueError("state capability_decision is malformed")
    remediations = state.get("remediations", [])
    if not isinstance(remediations, list):
        raise ValueError("state remediations must be an array")
    remediation_ids = []
    for remediation in remediations:
        if not isinstance(remediation, dict):
            raise ValueError("every remediation must be an object")
        required = {"id", "source_gate", "source_task", "severity", "criterion", "summary", "status", "fix_task", "attempts", "created_at", "resolved_at"}
        if set(remediation) != required:
            raise ValueError("remediation fields must be exactly: %s" % ", ".join(sorted(required)))
        identifier = remediation.get("id")
        if not isinstance(identifier, str) or not re.fullmatch(r"REM-[1-9][0-9]*", identifier):
            raise ValueError("every remediation needs a valid REM-n id")
        remediation_ids.append(identifier)
        if remediation.get("source_gate") not in REMEDIATION_GATES:
            raise ValueError("invalid remediation source_gate for %s" % identifier)
        if not isinstance(remediation.get("source_task"), str) or remediation["source_task"] not in known:
            raise ValueError("remediation %s has an unknown source task" % identifier)
        if remediation.get("severity") not in REMEDIATION_SEVERITIES:
            raise ValueError("invalid remediation severity for %s" % identifier)
        for field in ("criterion", "summary", "created_at"):
            if not isinstance(remediation.get(field), str) or not remediation[field].strip():
                raise ValueError("remediation %s.%s must be a non-empty string" % (identifier, field))
        if remediation.get("status") not in REMEDIATION_STATES:
            raise ValueError("invalid remediation status for %s" % identifier)
        if remediation.get("fix_task") is not None and (
            not isinstance(remediation.get("fix_task"), str) or remediation["fix_task"] not in known
        ):
            raise ValueError("remediation %s has an unknown fix task" % identifier)
        attempts = remediation.get("attempts")
        if not isinstance(attempts, int) or isinstance(attempts, bool) or attempts < 0:
            raise ValueError("invalid remediation attempts for %s" % identifier)
        if remediation.get("resolved_at") is not None and not isinstance(remediation.get("resolved_at"), str):
            raise ValueError("remediation %s.resolved_at must be null or a string" % identifier)
    if len(remediation_ids) != len(set(remediation_ids)):
        raise ValueError("state contains duplicate remediation ids")

    services = state.get("services", [])
    contracts = state.get("contracts", [])
    approvals = state.get("contract_approvals", [])
    if not isinstance(services, list) or not isinstance(contracts, list):
        raise ValueError("state services and contracts must be arrays")
    if not isinstance(approvals, list):
        raise ValueError("state contract_approvals must be an array")
    service_ids = []
    for service in services:
        if not isinstance(service, dict) or not isinstance(service.get("id"), str):
            raise ValueError("every state service must have a string id")
        service_ids.append(service["id"])
        for key in (
            "paths",
            "owns_data",
            "exposes",
            "consumes",
            "dependencies",
            "forbidden_dependencies",
        ):
            if not isinstance(service.get(key), list):
                raise ValueError("service %s.%s must be an array" % (service["id"], key))
    if len(service_ids) != len(set(service_ids)):
        raise ValueError("state contains duplicate service ids")
    references = []
    for contract in contracts:
        if not isinstance(contract, dict):
            raise ValueError("every state contract must be an object")
        try:
            reference = contract_ref(contract)
        except (KeyError, TypeError) as exc:
            raise ValueError("every state contract needs string id and version") from exc
        if contract.get("status") not in {"draft", "approved", "deprecated"}:
            raise ValueError("unknown contract status for %s" % reference)
        for key in ("producers", "consumers", "invariants", "verification"):
            if not isinstance(contract.get(key), list):
                raise ValueError("contract %s.%s must be an array" % (reference, key))
        references.append(reference)
    if len(references) != len(set(references)):
        raise ValueError("state contains duplicate contract references")
