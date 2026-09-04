"""Deterministic validation of IDE-LLM capability proposals."""
from __future__ import annotations
import json
import re
from pathlib import Path

class CapabilityError(ValueError):
    pass

CORE = {"planning", "file_scope", "approval", "testing", "review", "credential_restrictions", "destructive_approval"}
CAPABILITY_ID = re.compile(r"^[a-z][a-z0-9_]*$")

def load_catalog(path=None):
    path = Path(path or Path(__file__).with_name("capabilities.json"))
    try: data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc: raise CapabilityError("invalid capability catalog") from exc
    if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("capabilities"), dict):
        raise CapabilityError("capability catalog schema_version must be 1")
    floor = data.get("safety_floor")
    if not isinstance(floor, list) or not all(isinstance(item, str) for item in floor) or set(floor) != CORE:
        raise CapabilityError("safety floor is incomplete or modified")
    known = set(data["capabilities"])
    if not known or any(not isinstance(key, str) or not CAPABILITY_ID.fullmatch(key) for key in known):
        raise CapabilityError("capability IDs must use lowercase snake_case")
    for key, entry in data["capabilities"].items():
        if not isinstance(entry, dict) or set(entry) != {"requires", "conflicts"}:
            raise CapabilityError("capability %s must contain requires and conflicts" % key)
        for field in ("requires", "conflicts"):
            values = entry[field]
            if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
                raise CapabilityError("capability %s.%s must be a string array" % (key, field))
            if len(values) != len(set(values)) or set(values) - known or key in values:
                raise CapabilityError("capability %s.%s has invalid references" % (key, field))
    visiting, visited = set(), set()
    def visit(key):
        if key in visiting: raise CapabilityError("capability dependency cycle")
        if key in visited: return
        visiting.add(key)
        for dependency in data["capabilities"][key]["requires"]: visit(dependency)
        visiting.remove(key); visited.add(key)
    for key in sorted(known): visit(key)
    return data

def resolve(proposal=None, signals=None, overrides=None, catalog=None):
    catalog = catalog or load_catalog()
    raw_proposal = list(proposal or [])
    signals = list(signals or [])
    overrides = dict(overrides or {})
    if not all(isinstance(item, str) and CAPABILITY_ID.fullmatch(item) for item in raw_proposal):
        raise CapabilityError("proposal must be a capability ID array")
    if not all(isinstance(item, str) and item.strip() for item in signals):
        raise CapabilityError("signals must be non-empty strings")
    if not all(isinstance(value, bool) for value in overrides.values()):
        raise CapabilityError("capability overrides must be booleans")
    proposal = set(raw_proposal)
    known = set(catalog["capabilities"])
    if not proposal.issubset(known): raise CapabilityError("unknown capability: %s" % sorted(proposal - known)[0])
    if any(key not in known | CORE for key in overrides): raise CapabilityError("unknown capability override")
    disabled = {key for key, value in overrides.items() if value is False}
    if CORE & disabled: raise CapabilityError("safety floor cannot be disabled")
    requested = proposal | {key for key, value in overrides.items() if value and key in known}
    if requested and not signals:
        raise CapabilityError("capability proposal requires at least one repository or task signal")
    enabled = set(proposal)
    for key, value in overrides.items():
        if value: enabled.add(key)
        else: enabled.discard(key)
    changed = True
    while changed:
        changed = False
        for key in list(enabled):
            for dep in catalog["capabilities"].get(key, {}).get("requires", []):
                if dep in disabled: raise CapabilityError("override disables required dependency: %s" % dep)
                if dep not in enabled: enabled.add(dep); changed = True
    for key in enabled:
        if set(catalog["capabilities"].get(key, {}).get("conflicts", [])) & enabled:
            raise CapabilityError("conflicting capabilities")
    return {"schema_version": 1, "capabilities": sorted(CORE | enabled), "signals": signals,
            "provenance": {"source": "ide-llm", "proposal": sorted(proposal), "overrides": overrides}}

def effective_view(decision, harness_config):
    """Combine a capability decision with non-secret execution settings."""
    kit = harness_config["kit_policy"]
    task_route = kit["execution"]["task_cli"]
    provider_name = task_route["provider"]
    provider = harness_config["providers"][provider_name]
    return {
        "schema_version": 1,
        "capability_decision": decision,
        "providers": {
            "implementation": {"enabled": task_route["enabled"], "provider": provider_name,
                               "model": task_route.get("model") or provider.get("model")},
            "qa": kit["quality"]["qa"],
            "review": kit["quality"]["review"],
        },
        "permissions": {
            "isolated_worktree_required": kit["execution"]["isolated_worktree"]["required"],
            "provider_execution_enabled": task_route["enabled"],
            "destructive_approval_required": True,
        },
        "timeouts": {"implementation_seconds": int(provider.get("timeout_seconds", 1200))},
        "enabled_gates": sorted(CORE),
    }

def render_human(view):
    decision = view["capability_decision"]
    return "\n".join([
        "Capabilities: %s" % ", ".join(decision["capabilities"]),
        "Signals: %s" % (", ".join(decision["signals"]) or "none"),
        "Implementation provider: %s (enabled=%s)" % (view["providers"]["implementation"]["provider"], str(view["providers"]["implementation"]["enabled"]).lower()),
        "Timeout: %ss" % view["timeouts"]["implementation_seconds"],
        "Required gates: %s" % ", ".join(view["enabled_gates"]),
    ])

def infer_minimum(signals, catalog=None):
    """Return conservative capabilities justified by repository signal names."""
    values = [str(item).lower() for item in (signals or [])]
    required = set()
    if any(".contracts" in item or "openapi" in item or "asyncapi" in item for item in values):
        required.update({"service_ownership", "contract_graph", "contract_compatibility", "integration_qa"})
    def database_signal(item):
        normalized = item.replace("\\", "/")
        tokens = set(re.findall(r"[a-z0-9]+", normalized))
        return bool(
            tokens & {"database", "databases", "db", "migration", "migrations", "ddl", "alembic", "flyway", "liquibase"}
            or "prisma/migrations" in normalized
        )
    if any(database_signal(item) for item in values):
        required.update({"service_ownership", "database_safety"})
    if any("deploy" in item or "kubernetes" in item or "production" in item for item in values):
        required.update({"service_ownership", "release_ordering"})
    return resolve(required, signals, catalog=catalog)

def resolve_plan(plan, signals=None, catalog=None):
    """Apply non-optional capabilities implied by declared plan boundaries."""
    proposal = set(plan.get("capabilities", []))
    required = set()
    reasons = []
    if plan.get("services"):
        required.add("service_ownership"); reasons.append("plan.services")
    if plan.get("contracts"):
        required.update({"service_ownership", "contract_graph", "contract_compatibility", "integration_qa"})
        reasons.append("plan.contracts")
    for task in plan.get("tasks", []):
        if task.get("data_entities") or "database" in task.get("risks", []):
            required.update({"service_ownership", "database_safety"}); reasons.append("task.database")
        if task.get("deploy_after") or "production" in task.get("risks", []):
            required.update({"service_ownership", "release_ordering"}); reasons.append("task.release")
    evidence_signals = list(signals or []) + sorted(set(reasons))
    decision = resolve(proposal | required, evidence_signals, catalog=catalog)
    decision["provenance"]["required_by_plan"] = sorted(set(reasons))
    return decision
