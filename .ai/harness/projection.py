"""Deterministic human-readable projections of canonical harness state."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List

from store import RepositoryStore


def _one_line(value: Any) -> str:
    return " ".join(str(value).replace("|", "\\|").split())


def _items(values: Iterable[Any], empty: str = "none") -> str:
    rendered = [_one_line(value) for value in values if str(value).strip()]
    return ", ".join(rendered) if rendered else empty


def render_plan(state: Dict[str, Any]) -> str:
    lines = [
        "# Plan — %s" % _one_line(state["feature"]),
        "",
        "status: %s" % _one_line(state["status"]),
        "revision: %s" % state.get("plan_revision", 0),
        "source: features/%s/" % _one_line(state["feature"]),
        "generated-from: .project/%s/state.json" % _one_line(state["feature"]),
        "",
        "## Goal",
        "",
        _one_line(state.get("goal", "")),
        "",
        "## Constraints",
        "",
    ]
    constraints = state.get("constraints", [])
    lines.extend(["- " + _one_line(item) for item in constraints] or ["- none"])
    lines.extend(["", "## Verification", ""])
    verification = state.get("verification", [])
    lines.extend(["- " + _one_line(item) for item in verification] or ["- none"])
    requirements = state.get("requirements", [])
    if requirements:
        lines.extend(["", "## Requirements", ""])
        covered = {
            reference
            for task in state.get("tasks", [])
            for reference in task.get("requirement_refs", [])
        }
        for requirement in requirements:
            marker = "covered" if requirement.get("id") in covered else "uncovered"
            lines.append(
                "- %s [%s]: %s"
                % (
                    _one_line(requirement.get("id", "?")),
                    marker,
                    _one_line(requirement.get("text", "")),
                )
            )
    hierarchy = [
        ("Program", state.get("program_id")),
        ("Workstream", state.get("workstream_id")),
        ("Parent feature", state.get("parent_feature")),
    ]
    if any(value for _, value in hierarchy):
        lines.extend(["", "## Hierarchy", ""])
        lines.extend(
            ["- %s: %s" % (label, _one_line(value)) for label, value in hierarchy if value]
        )
    barriers = state.get("feature_dependency_results", [])
    if barriers:
        lines.extend(["", "## Feature Dependencies", ""])
        for barrier in barriers:
            lines.append(
                "- %s:%s | %s | source: %s | %s"
                % (
                    _one_line(barrier.get("feature", "?")),
                    _one_line(barrier.get("task", "?")),
                    "satisfied" if barrier.get("satisfied") else "blocked",
                    _one_line(barrier.get("source") or "none"),
                    _one_line(barrier.get("diagnostic") or ""),
                )
            )
    remediations = state.get("remediations", [])
    if remediations:
        lines.extend(["", "## Remediations", ""])
        for remediation in remediations:
            lines.append(
                "- %s | %s | %s | source: %s/%s | fix: %s"
                % (
                    _one_line(remediation.get("id", "?")),
                    _one_line(remediation.get("status", "unknown")),
                    _one_line(remediation.get("severity", "unknown")),
                    _one_line(remediation.get("source_gate", "unknown")),
                    _one_line(remediation.get("source_task", "?")),
                    _one_line(remediation.get("fix_task") or "unassigned"),
                )
            )
            lines.append("  - " + _one_line(remediation.get("summary", "")))
    services = state.get("services", [])
    if services:
        lines.extend(["", "## Services", ""])
        for service in services:
            lines.append(
                "- %s | domain: %s | paths: %s | owns data: %s"
                % (
                    _one_line(service.get("id", "unknown")),
                    _one_line(service.get("domain", "unknown")),
                    _items(service.get("paths", [])),
                    _items(service.get("owns_data", [])),
                )
            )
            if service.get("exposes") or service.get("consumes"):
                lines.append(
                    "  - Contracts: exposes %s; consumes %s"
                    % (
                        _items(service.get("exposes", [])),
                        _items(service.get("consumes", [])),
                    )
                )
    contracts = state.get("contracts", [])
    if contracts:
        lines.extend(["", "## Contracts", ""])
        for contract in contracts:
            reference = "%s@%s" % (contract.get("id", "unknown"), contract.get("version", "?"))
            lines.append(
                "- %s | kind: %s | owner: %s | status: %s | compatibility: %s | source: %s | hash: %s"
                % (
                    _one_line(reference),
                    _one_line(contract.get("kind", "unknown")),
                    _one_line(contract.get("owner", "unknown")),
                    _one_line(contract.get("status", "draft")),
                    _one_line(contract.get("compatibility", "none")),
                    _one_line(contract.get("source", "unknown")),
                    _one_line(contract.get("source_hash", "pending")),
                )
            )
    lines.extend(
        [
            "",
            "## Runtime",
            "",
            "- Recorded review policy: %s"
            % _one_line(state.get("review_policy", "active-agent")),
            "- Run: %s (%s)"
            % (
                _one_line(state.get("run", {}).get("state", "idle")),
                _one_line(state.get("run", {}).get("id") or "none"),
            ),
            "- Plan approval: %s"
            % (
                "pending"
                if state.get("status") == "plan_pending_approval"
                else "revision %s approved or not required" % state.get("plan_revision", 0)
            ),
            "- Updated: %s" % _one_line(state.get("updated_at", "unknown")),
            "",
        ]
    )
    return "\n".join(lines)


def _evidence_line(evidence: Any) -> str:
    if isinstance(evidence, dict):
        return _one_line(json.dumps(evidence, sort_keys=True, ensure_ascii=False))
    return _one_line(evidence)


def render_tasks(state: Dict[str, Any]) -> str:
    lines: List[str] = [
        "# Tasks — %s" % _one_line(state["feature"]),
        "",
        "Intent: feature | Size: %s" % _one_line(state.get("size", "standard")),
        "Goal: %s" % _one_line(state.get("goal", "")),
        "Out of scope: generated from the approved goal and constraints",
        "Open questions: none",
        "Canonical state: .project/%s/state.json" % _one_line(state["feature"]),
        "",
        "## Tasks",
        "",
    ]
    for task in state.get("tasks", []):
        checked = "x" if task.get("state") == "complete" else " "
        needs = _items(task.get("dependencies", []), "-")
        files = _items(task.get("files", []), "-")
        line = (
            "- [%s] %s %s | owner: %s | scope: %s | needs: %s | files: %s"
            " | state: %s | attempts: %s"
            % (
                checked,
                _one_line(task.get("id", "?")),
                _one_line(task.get("title", "untitled")),
                _one_line(task.get("owner", "implementer")),
                _one_line(task.get("scope", "S")),
                needs,
                files,
                _one_line(task.get("state", "proposed")),
                int(task.get("attempts", 0)),
            )
        )
        if state.get("services") or task.get("service") or task.get("contract_reads") or task.get("contract_writes"):
            line += " | service: %s | layer: %s" % (
                _one_line(task.get("service") or "shared"),
                _one_line(task.get("layer") or "unspecified"),
            )
        lines.append(line)
        description = _one_line(task.get("description", ""))
        if description:
            lines.append("  - Description: " + description)
        for criterion in task.get("acceptance_criteria", []):
            lines.append("  - Accept: " + _one_line(criterion))
        if task.get("requirement_refs"):
            lines.append("  - Requirements: " + _items(task.get("requirement_refs", [])))
        for command in task.get("verification_commands", []):
            lines.append("  - Verify: " + _one_line(json.dumps(command, ensure_ascii=False)))
        if task.get("verification_profiles"):
            lines.append("  - Verification profiles: " + _items(task["verification_profiles"]))
        if task.get("feature_dependency_block"):
            lines.append("  - Blocked: " + _one_line(task["feature_dependency_block"]))
        risks = task.get("risks", [])
        if risks:
            lines.append("  - Risks: " + _items(risks))
        if task.get("contract_reads") or task.get("contract_writes") or task.get("produces"):
            lines.append(
                "  - Contracts: reads %s; writes %s; produces %s"
                % (
                    _items(task.get("contract_reads", [])),
                    _items(task.get("contract_writes", [])),
                    _items(task.get("produces", [])),
                )
            )
        if task.get("data_entities"):
            lines.append("  - Data entities: " + _items(task.get("data_entities", [])))
        if isinstance(task.get("workspace"), dict):
            workspace = task["workspace"]
            lines.append(
                "  - Workspace: phase %s; base %s; patch %s; files %s"
                % (
                    _one_line(workspace.get("phase", "unknown")),
                    _one_line(workspace.get("base_commit", "unknown")),
                    _one_line(workspace.get("patch_digest") or "pending"),
                    _items(workspace.get("changed_files", [])),
                )
            )
        if task.get("deploy_after") or task.get("rollback"):
            lines.append(
                "  - Delivery: deploy after %s; rollback %s"
                % (_items(task.get("deploy_after", [])), _one_line(task.get("rollback") or "none"))
            )
        for evidence in task.get("evidence", []):
            lines.append("  - Evidence: " + _evidence_line(evidence))
        for review in task.get("reviews", []):
            verdict = review.get("verdict", "unknown") if isinstance(review, dict) else review
            policy = (
                review.get("policy", "legacy-unspecified")
                if isinstance(review, dict)
                else "legacy-unspecified"
            )
            lines.append(
                "  - Review (%s): %s" % (_one_line(policy), _one_line(verdict))
            )
    if not state.get("tasks"):
        lines.append("_No plan has been accepted yet._")
    lines.append("")
    return "\n".join(lines)


def write_projections(store: RepositoryStore, state: Dict[str, Any]) -> None:
    directory = store.feature_dir(state["feature"])
    store.write_text_atomic(directory / "plan.md", render_plan(state))
    store.write_text_atomic(directory / "tasks.md", render_tasks(state))
