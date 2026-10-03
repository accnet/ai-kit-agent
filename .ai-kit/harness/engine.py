"""LLM-first orchestration loop with deterministic control-plane transitions."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from memory import MemoryStore
from dependencies import CrossFeatureDependencyResolver
from models import (
    APPROVAL_REQUIRED_RISKS,
    REMEDIATION_GATES,
    REMEDIATION_SEVERITIES,
    contract_by_ref,
    contract_ref,
    new_state,
    task_by_id,
    touch,
    utc_now,
)
from policy import (
    MAX_ATTEMPTS,
    ApprovalRequired,
    PolicyError,
    next_schedulable,
    normalize_contract_graph,
    normalize_plan,
    refresh_readiness,
    canonical_digest,
    changed_files_in_scope,
    changed_paths,
    snapshot_repository,
    source_digest,
    plan_revision_digest,
    task_action_digest,
    validate_contract_readiness,
    validate_scope_roots,
    validate_remediation_links,
    validate_success,
)
from projection import render_plan, render_tasks, write_projections
from compatibility import CompatibilityError, compare as compare_contracts
from capability_config import resolve_plan as resolve_plan_capabilities
try:
    from project_contracts import adapter_for
except ImportError:
    adapter_for = None
from providers import ProviderError, ProviderRequest
from verification import run_verification
from schemas import EXECUTION_SCHEMA, PLAN_SCHEMA, REVIEW_SCHEMA
from store import RepositoryStore, StoreError
from worktrees import GitWorkspaceManager, PatchArtifact, WorkspaceError, WorkspaceRecord


class EngineError(RuntimeError):
    """Raised when the requested orchestration transition is not valid."""


class NoTaskAvailable(EngineError):
    """Raised when no dependency-ready task can run."""


RUN_TRANSITIONS: Dict[str, set] = {
    "running": {"paused", "needs_input", "cancelled"},
    "paused": {"running", "cancelled"},
    "needs_input": {"running", "cancelled"},
    "cancelled": set(),
    "completed": set(),
    "idle": set(),
}


class HarnessEngine:
    def __init__(
        self,
        store: RepositoryStore,
        *,
        context_budget: int = 16_000,
        independent_review_enabled: bool = False,
        workspace_manager: Optional[GitWorkspaceManager] = None,
    ) -> None:
        self.store = store
        self.memory = MemoryStore(store)
        self.context_budget = context_budget
        self.independent_review_enabled = independent_review_enabled
        self.workspace_manager = workspace_manager

    def initialize(
        self,
        feature: str,
        goal: str,
        *,
        constraints: Optional[List[str]] = None,
        verification: Optional[List[str]] = None,
        requirements: Optional[List[Dict[str, str]]] = None,
        size: str = "standard",
        review_policy: Optional[str] = None,
        actor: str = "user",
        capabilities: Optional[Sequence[str]] = None,
        capability_signals: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        if not goal.strip():
            raise EngineError("goal cannot be empty")
        requirement_ids = []
        for requirement in requirements or []:
            if not isinstance(requirement, dict):
                raise EngineError("requirements must contain id/text objects")
            requirement_id = str(requirement.get("id", "")).strip()
            requirement_text = str(requirement.get("text", "")).strip()
            if not re.fullmatch(r"R[1-9][0-9]*", requirement_id) or not requirement_text:
                raise EngineError("requirements need an R<n> id and non-empty text")
            requirement_ids.append(requirement_id)
        if len(requirement_ids) != len(set(requirement_ids)):
            raise EngineError("requirement IDs must be unique")
        if size not in {"trivial", "standard", "large"}:
            raise EngineError("size must be trivial, standard, or large")
        if review_policy is None:
            review_policy = (
                "independent" if self.independent_review_enabled else "active-agent"
            )
        if review_policy not in {"independent", "active-agent"}:
            raise EngineError("review policy must be independent or active-agent")
        if review_policy == "independent" and not self.independent_review_enabled:
            raise EngineError(
                "independent review is disabled by .ai-kit/config.json; "
                "set review.independent_enabled to true to enable it"
            )
        if not (self.store.intent_dir(feature) / "brief.md").is_file():
            raise EngineError("features/%s/brief.md must exist before harness initialization" % feature)
        with self.store.lock(feature):
            if self.store.state_path(feature).exists():
                raise EngineError("feature already has canonical state")
            state = new_state(
                feature,
                goal,
                constraints=constraints,
                verification=verification,
                requirements=requirements,
                size=size,
                review_policy=review_policy,
            )
            if capabilities is not None:
                from capability_config import resolve
                decision = resolve(capabilities, capability_signals or [])
                decision_path = self.store.feature_dir(feature) / "capabilities.json"
                state["capability_decision"] = decision
                self.store.write_json_atomic(decision_path, decision)
            self._commit(state, "initialized", actor, detail="canonical state created")
            return state

    def plan_with_provider(self, feature: str, provider: Any, *, actor: str = "planner", replan: bool = False) -> Dict[str, Any]:
        state = self.store.load_state(feature)
        context = self.memory.retrieve(
            feature,
            state["goal"],
            max_chars=self.context_budget,
            include_project_instructions=not self._provider_loads_project_instructions(provider),
        )
        request = ProviderRequest(
            "planner",
            self._plan_prompt(state, self.memory.render_context(context), replan=replan),
            PLAN_SCHEMA,
        )
        result = provider.invoke(request)
        return self.apply_plan(feature, result, provider_name=provider.name, actor=actor, replan=replan)

    def apply_plan(
        self,
        feature: str,
        plan: Dict[str, Any],
        *,
        provider_name: str = "scripted",
        actor: str = "planner",
        replan: bool = False,
    ) -> Dict[str, Any]:
        with self.store.lock(feature):
            state = self.store.load_state(feature)
            if state["status"] not in (
                {"initialized", "plan_pending_approval", "needs_replan", "blocked", "planned"}
                if replan
                else {"initialized"}
            ):
                raise EngineError("feature state %s cannot accept this plan transition" % state["status"])
            completed = {
                task["id"]: task for task in state.get("tasks", []) if task.get("state") == "complete"
            }
            previous = {task["id"]: task for task in state.get("tasks", [])}
            tasks = normalize_plan(
                plan,
                size=state.get("size", "standard"),
                completed_tasks=completed if replan else None,
                required_requirements=[
                    requirement["id"] for requirement in state.get("requirements", [])
                ],
            )
            graph = normalize_contract_graph(plan)
            decision_signals = []
            prior_proposal = []
            decision_path = self.store.feature_dir(feature) / "capabilities.json"
            if decision_path.is_file():
                try:
                    prior_decision = json.loads(decision_path.read_text(encoding="utf-8"))
                    decision_signals = prior_decision.get("signals", [])
                    prior_proposal = prior_decision.get("provenance", {}).get("proposal", [])
                except (OSError, json.JSONDecodeError, AttributeError):
                    decision_signals = []
            capability_plan = dict(plan)
            capability_plan["capabilities"] = sorted(set(plan.get("capabilities", [])) | set(prior_proposal))
            capability_decision = resolve_plan_capabilities(capability_plan, decision_signals)
            if replan:
                self._validate_completed_contracts(
                    completed,
                    state.get("contracts", []),
                    graph["contracts"],
                )
            contracts, preserved_approvals = self._merge_contract_state(
                state.get("contracts", []),
                graph["contracts"],
                state.get("contract_approvals", []),
                preserve=replan,
            )
            if replan:
                for task in tasks:
                    prior = previous.get(task["id"])
                    if prior and prior.get("state") != "complete":
                        task["attempts"] = int(prior.get("attempts", 0))
                        task["reviews"] = list(prior.get("reviews", []))
                        if task["attempts"] >= MAX_ATTEMPTS:
                            task["state"] = "escalated"
                # A revised unfinished contract needs fresh, per-task approval.
                state["approvals"] = [
                    record for record in state.get("approvals", []) if record.get("task") in completed
                ]
            state["program_id"] = graph["program_id"]
            state["workstream_id"] = graph["workstream_id"]
            state["parent_feature"] = graph["parent_feature"]
            state["feature_dependencies"] = list(plan.get("feature_dependencies", []))
            state["capability_decision"] = capability_decision
            state["services"] = graph["services"]
            state["contracts"] = contracts
            state["contract_approvals"] = preserved_approvals
            remediations = {item.get("id"): item for item in state.get("remediations", [])}
            for task in tasks:
                remediation_id = task.get("remediation_id")
                if remediation_id and remediation_id in remediations and remediations[remediation_id].get("fix_task") is None:
                    remediations[remediation_id]["fix_task"] = task["id"]
            validate_remediation_links(state, tasks)
            state["tasks"] = tasks
            self.store.write_json_atomic(decision_path, capability_decision)
            self._refresh_feature_barriers(state)
            state["plan_revision"] = int(state.get("plan_revision", 0)) + 1
            state["plan_summary"] = plan["summary"]
            pending_plan_approval = state.get("size") == "large"
            if tasks and all(task["state"] == "complete" for task in tasks):
                state["status"] = "complete"
            elif any(task["state"] == "escalated" for task in tasks):
                state["status"] = "blocked"
            elif pending_plan_approval:
                state["status"] = "plan_pending_approval"
            else:
                state["status"] = "planned"
            self._provider_history(
                state, provider_name, "planner", None, "proposed" if pending_plan_approval else "accepted"
            )
            self._commit(
                state,
                "plan_proposed" if pending_plan_approval else ("replanned" if replan else "plan_accepted"),
                actor,
                detail=plan["summary"],
                data={"revision": state["plan_revision"], "tasks": len(tasks)},
            )
            self.memory.add(
                feature,
                "episodic",
                ("Replan" if replan else "Plan") + " accepted: " + plan["summary"],
                tags=["plan", "revision-%d" % state["plan_revision"]],
                actor=actor,
                importance=4,
            )
            return state

    def record_remediation(
        self,
        feature: str,
        source_task: str,
        *,
        source_gate: str,
        severity: str,
        criterion: str,
        summary: str,
        retry: bool = False,
        actor: str = "coordinator",
    ) -> Dict[str, Any]:
        """Record a QA/review finding and optionally retry its source task."""

        if source_gate not in REMEDIATION_GATES:
            raise EngineError("source_gate must be qa or review")
        if severity not in REMEDIATION_SEVERITIES:
            raise EngineError("severity must be minor, major, or blocker")
        criterion = criterion.strip()
        summary = summary.strip()
        if not criterion or not summary:
            raise EngineError("criterion and summary cannot be empty")
        with self.store.lock(feature):
            state = self.store.load_state(feature)
            task = task_by_id(state, source_task)
            if criterion not in task.get("acceptance_criteria", []):
                raise EngineError("criterion must exactly match an acceptance criterion on %s" % source_task)
            if retry and task.get("state") in {"complete", "escalated"}:
                raise EngineError("completed or escalated task %s cannot be retried" % source_task)
            if any(
                item.get("source_task") == source_task
                and item.get("criterion") == criterion
                and item.get("status") == "open"
                for item in state.get("remediations", [])
            ):
                raise EngineError("an open remediation already exists for %s" % source_task)
            numbers = []
            for item in state.get("remediations", []):
                identifier = str(item.get("id", ""))
                suffix = identifier[4:] if identifier.startswith("REM-") else ""
                if suffix.isdigit():
                    numbers.append(int(suffix))
            identifier = "REM-%d" % (max(numbers or [0]) + 1)
            record = {
                "id": identifier,
                "source_gate": source_gate,
                "source_task": source_task,
                "severity": severity,
                "criterion": criterion,
                "summary": summary,
                "status": "open",
                "fix_task": None,
                "attempts": 0,
                "created_at": utc_now(),
                "resolved_at": None,
            }
            state.setdefault("remediations", []).append(record)
            if retry:
                self._fail_in_state(state, task, summary)
                record["attempts"] = task.get("attempts", 0)
            self._commit(
                state,
                "remediation_recorded",
                actor,
                task=source_task,
                detail=summary,
                data={"remediation_id": identifier, "retry": retry, "severity": severity},
            )
            return state

    def resolve_remediation(
        self, feature: str, remediation_id: str, *, actor: str = "coordinator"
    ) -> Dict[str, Any]:
        """Resolve a finding only after its linked fix task is complete."""

        with self.store.lock(feature):
            state = self.store.load_state(feature)
            matches = [item for item in state.get("remediations", []) if item.get("id") == remediation_id]
            if len(matches) != 1:
                raise EngineError("unknown remediation: %s" % remediation_id)
            record = matches[0]
            if record.get("status") != "open":
                raise EngineError("remediation %s is not open" % remediation_id)
            fix_task = record.get("fix_task")
            if not fix_task:
                raise EngineError("remediation %s has no linked fix task" % remediation_id)
            task = task_by_id(state, fix_task)
            if task.get("state") != "complete":
                raise EngineError("fix task %s must be complete before resolution" % fix_task)
            if task.get("review_required", True) and not any(
                isinstance(review, dict) and review.get("verdict") == "approve"
                for review in task.get("reviews", [])
            ):
                raise EngineError("fix task %s requires approved G3 review before resolution" % fix_task)
            record["status"] = "resolved"
            record["resolved_at"] = utc_now()
            self._commit(
                state,
                "remediation_resolved",
                actor,
                task=fix_task,
                detail=remediation_id,
                data={"remediation_id": remediation_id},
            )
            return state

    def approve_plan(
        self, feature: str, *, approved_by: str, note: str = ""
    ) -> Dict[str, Any]:
        if not approved_by.strip():
            raise EngineError("approved_by cannot be empty")
        with self.store.lock(feature):
            state = self.store.load_state(feature)
            if state.get("status") != "plan_pending_approval":
                raise EngineError("current plan revision does not require approval")
            revision = int(state.get("plan_revision", 0))
            revision_digest = plan_revision_digest(state)
            state.setdefault("plan_approvals", []).append(
                {
                    "revision": revision,
                    "revision_digest": revision_digest,
                    "approved_by": approved_by,
                    "note": note,
                    "at": utc_now(),
                }
            )
            refresh_readiness(state["tasks"])
            state["status"] = "planned"
            self._commit(
                state,
                "plan_approved",
                approved_by,
                detail=note,
                data={"revision": revision, "revision_digest": revision_digest},
            )
            return state

    def next_task(self, feature: str) -> Optional[Dict[str, Any]]:
        state = self.store.load_state(feature)
        return next_schedulable(state, root=self.store.root)

    def artifact_status(self, feature: str) -> Dict[str, Any]:
        state = self.store.load_state(feature)
        expected = int(state.get("event_sequence", 0))
        events = self.store.read_records(feature, "events.jsonl")
        sequences = [event.get("sequence") for event in events if isinstance(event.get("sequence"), int)]
        expected_sequences = list(range(1, expected + 1))
        directory = self.store.feature_dir(feature)
        plan_path = directory / "plan.md"
        tasks_path = directory / "tasks.md"
        plan_matches = plan_path.is_file() and plan_path.read_text(encoding="utf-8") == render_plan(state)
        tasks_matches = tasks_path.is_file() and tasks_path.read_text(encoding="utf-8") == render_tasks(state)
        return {
            "event_sequence": expected,
            "event_sequences": sequences,
            "events_match": sequences == expected_sequences,
            "plan_projection_matches": plan_matches,
            "tasks_projection_matches": tasks_matches,
            "needs_repair": sequences != expected_sequences or not plan_matches or not tasks_matches,
            "lock": self.store.lock_status(feature),
        }

    def repair_artifacts(self, feature: str, *, actor: str = "recovery") -> Dict[str, Any]:
        with self.store.lock(feature):
            state = self.store.load_state(feature)
            status = self.artifact_status(feature)
            expected = status["event_sequence"]
            sequences = status["event_sequences"]
            if sequences != list(range(1, max(0, expected))):
                if sequences != list(range(1, expected + 1)):
                    raise EngineError("event history has a non-repairable gap or duplicate")
            if sequences == list(range(1, max(0, expected))) and expected > 0:
                transition = state.get("last_transition", {})
                self.store.append_event(
                    feature,
                    transition.get("event", "recovered_transition"),
                    actor,
                    task=transition.get("task"),
                    detail="reconstructed from canonical state",
                    data={"recovered": True},
                    sequence=expected,
                )
            write_projections(self.store, state)
        return self.artifact_status(feature)

    def approve_task(
        self, feature: str, task_id: str, *, approved_by: str, note: str = ""
    ) -> Dict[str, Any]:
        if not approved_by.strip():
            raise EngineError("approved_by cannot be empty")
        with self.store.lock(feature):
            state = self.store.load_state(feature)
            task = task_by_id(state, task_id)
            risks = sorted(set(task.get("risks", [])) & APPROVAL_REQUIRED_RISKS)
            if not risks:
                raise EngineError("task %s does not require explicit approval" % task_id)
            action_digest = task_action_digest(state, task)
            state.setdefault("approvals", []).append(
                {
                    "task": task_id,
                    "risks": risks,
                    "action_digest": action_digest,
                    "approved_by": approved_by,
                    "note": note,
                    "at": utc_now(),
                }
            )
            self._commit(
                state,
                "task_approved",
                approved_by,
                task=task_id,
                detail=note,
                data={"risks": risks, "action_digest": action_digest},
            )
            return state

    def start_run(self, feature: str, *, actor: str = "user") -> Dict[str, Any]:
        """Start a durable orchestration session without invoking a provider."""

        with self.store.lock(feature):
            state = self.store.load_state(feature)
            run = state.setdefault("run", {"state": "idle"})
            if run.get("state") not in {"idle", "cancelled", "completed"}:
                raise EngineError("run is already %s" % run.get("state"))
            if state.get("status") in {"initialized", "plan_pending_approval", "complete"}:
                raise EngineError("feature state %s cannot start a run" % state.get("status"))
            now = utc_now()
            state["run"] = {
                "id": str(uuid.uuid4()),
                "state": "running",
                "started_at": now,
                "updated_at": now,
                "reason": "",
            }
            self._commit(state, "run_started", actor, data={"run_id": state["run"]["id"]})
            return state

    def pause_run(self, feature: str, *, actor: str = "user", reason: str = "") -> Dict[str, Any]:
        return self._transition_run(feature, "paused", actor=actor, reason=reason)

    def resume_run(self, feature: str, *, actor: str = "user") -> Dict[str, Any]:
        return self._transition_run(feature, "running", actor=actor, reason="")

    def request_input(self, feature: str, *, actor: str = "orchestrator", reason: str) -> Dict[str, Any]:
        if not reason.strip():
            raise EngineError("needs-input requires a reason")
        return self._transition_run(feature, "needs_input", actor=actor, reason=reason)

    def cancel_run(self, feature: str, *, actor: str = "user", reason: str = "") -> Dict[str, Any]:
        return self._transition_run(feature, "cancelled", actor=actor, reason=reason)

    def _transition_run(
        self, feature: str, target: str, *, actor: str, reason: str
    ) -> Dict[str, Any]:
        with self.store.lock(feature):
            state = self.store.load_state(feature)
            run = state.get("run", {"state": "idle"})
            current = run.get("state", "idle")
            if target not in RUN_TRANSITIONS.get(current, set()):
                raise EngineError("run transition %s -> %s is not allowed" % (current, target))
            run["state"] = target
            run["updated_at"] = utc_now()
            run["reason"] = reason.strip()
            event = {
                "paused": "run_paused",
                "running": "run_resumed",
                "needs_input": "run_needs_input",
                "cancelled": "run_cancelled",
            }[target]
            self._commit(
                state,
                event,
                actor,
                detail=run["reason"],
                data={"run_id": run.get("id")},
            )
            return state

    def request_structured_input(
        self,
        feature: str,
        *,
        actor: str = "orchestrator",
        reason: str,
        questions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Open a durable, host-neutral structured input_request, then
        transition the run to needs_input via the existing RUN_TRANSITIONS
        table. See .project/structured-user-input/architecture.md.

        Never mutates tasks/contracts/plan_approvals and never calls
        plan_with_provider or approve_plan — an answer that changes scope
        must go through the existing replan path, not this method.
        """

        if not reason.strip():
            raise EngineError("structured input request requires a reason")
        if not questions:
            raise EngineError("structured input request requires at least one question")
        with self.store.lock(feature):
            state = self.store.load_state(feature)
            run = state.get("run", {"state": "idle"})
            current = run.get("state", "idle")
            if "needs_input" not in RUN_TRANSITIONS.get(current, set()):
                raise EngineError("run transition %s -> needs_input is not allowed" % current)
            numbers = []
            for item in state.get("input_requests", []):
                identifier = str(item.get("id", ""))
                suffix = identifier[3:] if identifier.startswith("IN-") else ""
                if suffix.isdigit():
                    numbers.append(int(suffix))
            identifier = "IN-%d" % (max(numbers or [0]) + 1)
            now = utc_now()
            record = {
                "id": identifier,
                "reason": reason.strip(),
                "questions": questions,
                "schema_hash": canonical_digest({"questions": questions}),
                "plan_revision": int(state.get("plan_revision", 0)),
                "status": "pending",
                "answers": None,
                "answered_by": None,
                "answered_at": None,
                "created_at": now,
            }
            state.setdefault("input_requests", []).append(record)
            run["state"] = "needs_input"
            run["updated_at"] = now
            run["reason"] = reason.strip()
            run["input_request_id"] = identifier
            state["run"] = run
            self._commit(
                state,
                "run_needs_input",
                actor,
                detail=run["reason"],
                data={"run_id": run.get("id"), "input_request_id": identifier},
            )
            return state

    def answer_input(
        self,
        feature: str,
        request_id: str,
        *,
        actor: str,
        answers: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Validate and persist an answer to a pending input_request, then
        resume the run via the existing RUN_TRANSITIONS table. See
        .project/structured-user-input/architecture.md #4 for the exact
        five-step validation order this method implements.
        """

        if not actor.strip():
            raise EngineError("answer_input requires an actor")
        with self.store.lock(feature):
            state = self.store.load_state(feature)
            matches = [item for item in state.get("input_requests", []) if item.get("id") == request_id]
            if len(matches) != 1 or matches[0].get("status") != "pending":
                raise EngineError("unknown or non-pending input_request: %s" % request_id)
            record = matches[0]

            expected_hash = canonical_digest({"questions": record["questions"]})
            if record.get("schema_hash") != expected_hash:
                raise EngineError(
                    "input_request %s schema_hash mismatch — the stored question set was modified" % request_id
                )

            current_revision = int(state.get("plan_revision", 0))
            request_revision = int(record.get("plan_revision", 0))
            if request_revision != current_revision:
                raise EngineError(
                    "input_request %s is stale: requested at plan_revision %d, current is %d"
                    % (request_id, request_revision, current_revision)
                )

            for question in record["questions"]:
                q_id = question["id"]
                answer = answers.get(q_id)
                if question.get("required") and (
                    not isinstance(answer, dict)
                    or (not answer.get("selected") and not str(answer.get("freeform", "")).strip())
                ):
                    raise EngineError("input_request %s: question %s requires an answer" % (request_id, q_id))
                if answer is None:
                    continue
                valid_option_ids = {option["id"] for option in question.get("options", [])}
                selected = answer.get("selected") or []
                if not isinstance(selected, list):
                    raise EngineError("input_request %s: question %s selected must be an array" % (request_id, q_id))
                unknown = set(selected) - valid_option_ids
                if unknown:
                    raise EngineError(
                        "input_request %s: question %s references unknown option id(s): %s"
                        % (request_id, q_id, ", ".join(sorted(unknown)))
                    )
                if question.get("type") == "single_select" and len(selected) > 1:
                    raise EngineError("input_request %s: question %s allows only one selection" % (request_id, q_id))
                if str(answer.get("freeform", "")).strip() and not question.get("allow_freeform"):
                    raise EngineError("input_request %s: question %s does not allow a freeform answer" % (request_id, q_id))

            now = utc_now()
            record["status"] = "answered"
            record["answers"] = answers
            record["answered_by"] = actor.strip()
            record["answered_at"] = now

            run = state.get("run", {"state": "idle"})
            current = run.get("state", "idle")
            if "running" not in RUN_TRANSITIONS.get(current, set()):
                raise EngineError("run transition %s -> running is not allowed" % current)
            run["state"] = "running"
            run["updated_at"] = now
            run["reason"] = ""
            run["input_request_id"] = None
            state["run"] = run

            self._commit(
                state,
                "run_resumed",
                actor,
                detail="answered %s" % request_id,
                data={"run_id": run.get("id"), "input_request_id": request_id},
            )
            return state

    def approve_contract(
        self,
        feature: str,
        reference: str,
        *,
        approved_by: str,
        note: str = "",
    ) -> Dict[str, Any]:
        """Approve the current on-disk source for one versioned contract."""

        if not approved_by.strip():
            raise EngineError("approved_by cannot be empty")
        with self.store.lock(feature):
            state = self.store.load_state(feature)
            try:
                contract = contract_by_ref(state, reference)
            except KeyError as exc:
                raise EngineError(exc.args[0]) from exc
            writers = [
                task
                for task in state.get("tasks", [])
                if reference in task.get("contract_writes", [])
            ]
            unfinished = [task["id"] for task in writers if task.get("state") != "complete"]
            if unfinished:
                raise EngineError(
                    "contract %s cannot be approved before writer tasks complete: %s"
                    % (reference, ", ".join(unfinished))
                )
            compatibility_result = None
            previous_source = contract.get("previous_source")
            if previous_source:
                try:
                    old_path = (self.store.root / previous_source).resolve()
                    new_path = (self.store.root / contract["source"]).resolve()
                    old_path.relative_to(self.store.root.resolve())
                    new_path.relative_to(self.store.root.resolve())
                    old_doc = json.loads(old_path.read_text(encoding="utf-8"))
                    new_doc = json.loads(new_path.read_text(encoding="utf-8"))
                    if adapter_for and contract.get("kind") in {"schema", "api", "event", "data", "workflow"}:
                        compatibility_result = adapter_for(contract["kind"]).analyze(old_doc, new_doc)
                    else:
                        compatibility_result = compare_contracts(old_doc, new_doc)
                except (OSError, ValueError, json.JSONDecodeError, CompatibilityError) as exc:
                    raise EngineError("contract compatibility analysis failed: %s" % exc) from exc
                if compatibility_result["classification"] == "breaking" and contract.get("change_type") != "breaking":
                    raise EngineError("contract %s has undeclared breaking compatibility changes" % reference)
            digest = source_digest(self.store.root, contract["source"])
            contract["status"] = "approved"
            contract["source_hash"] = digest
            record = {
                "contract": reference,
                "source_hash": digest,
                "approved_by": approved_by,
                "note": note,
                "at": utc_now(),
            }
            if compatibility_result is not None:
                record["compatibility"] = compatibility_result
            state.setdefault("contract_approvals", []).append(record)
            refresh_readiness(state["tasks"])
            if state.get("status") not in {"complete", "blocked", "plan_pending_approval"}:
                state["status"] = "planned"
            self._commit(
                state,
                "contract_approved",
                approved_by,
                detail=note,
                data={"contract": reference, "source_hash": digest, "compatibility": compatibility_result},
            )
            return state

    def deprecate_contract(
        self,
        feature: str,
        reference: str,
        *,
        deprecated_by: str,
        note: str = "",
    ) -> Dict[str, Any]:
        """Explicitly stop new work from consuming one approved contract version."""

        if not deprecated_by.strip():
            raise EngineError("deprecated_by cannot be empty")
        with self.store.lock(feature):
            state = self.store.load_state(feature)
            try:
                contract = contract_by_ref(state, reference)
            except KeyError as exc:
                raise EngineError(exc.args[0]) from exc
            if contract.get("status") != "approved":
                raise EngineError("only an approved contract can be deprecated: %s" % reference)
            contract["status"] = "deprecated"
            self._commit(
                state,
                "contract_deprecated",
                deprecated_by,
                detail=note,
                data={"contract": reference, "source_hash": contract.get("source_hash")},
            )
            return state

    def execute_with_provider(
        self,
        feature: str,
        provider: Any,
        *,
        task_id: Optional[str] = None,
        actor: str = "implementer",
    ) -> Dict[str, Any]:
        workspace_record: Optional[WorkspaceRecord] = None
        with self.store.lock(feature):
            state = self.store.load_state(feature)
            run_state = state.get("run", {}).get("state", "idle")
            if run_state in {"paused", "needs_input", "cancelled"}:
                raise EngineError(
                    "run is %s; resume or start a new run before stepping" % run_state
                )
            try:
                task = (
                    task_by_id(state, task_id)
                    if task_id
                    else next_schedulable(state, root=self.store.root)
                )
            except ApprovalRequired:
                raise
            if task is None or task.get("state") != "ready":
                raise NoTaskAvailable("no dependency-ready task is available")
            if task_id and next_schedulable_for_id(state, task_id, root=self.store.root) is None:
                raise NoTaskAvailable("task %s is blocked, unapproved, or not ready" % task_id)
            validate_scope_roots(self.store.root, task)
            if self.workspace_manager is not None:
                previous = task.get("workspace")
                if isinstance(previous, dict) and previous.get("phase") not in {
                    "discarded",
                    "promoted",
                }:
                    prior_record = WorkspaceRecord.from_dict(previous)
                    self.workspace_manager.cleanup(prior_record)
                workspace_record = self.workspace_manager.create(
                    feature,
                    task["id"],
                    allowed_dirty_paths=[
                        ".project/%s" % feature,
                        ".workspace/harness/%s.lock" % feature,
                        ".workspace/qa",
                    ],
                )
                task["workspace"] = {
                    **workspace_record.to_dict(),
                    "phase": "created",
                    "patch_digest": None,
                    "changed_files": [],
                    "created_at": utc_now(),
                    "verified_at": None,
                    "promoted_at": None,
                }
            for reference in task.get("contract_writes", []):
                contract = contract_by_ref(state, reference)
                contract["status"] = "draft"
                contract["source_hash"] = "pending"
            if task.get("contract_writes"):
                written = set(task["contract_writes"])
                state["contract_approvals"] = [
                    record
                    for record in state.get("contract_approvals", [])
                    if record.get("contract") not in written
                ]
            task["state"] = "running"
            state["status"] = "running"
            self._commit(state, "task_started", actor, task=task["id"], detail=task["title"])

        execution_root = (
            self.workspace_manager.validate_owned(workspace_record)
            if self.workspace_manager is not None and workspace_record is not None
            else self.store.root
        )
        context = self.memory.retrieve(
            feature,
            "%s %s" % (task["title"], task["description"]),
            max_chars=self.context_budget,
            include_project_instructions=not self._provider_loads_project_instructions(provider),
        )
        request = ProviderRequest(
            "implementer",
            self._execution_prompt(state, task, self.memory.render_context(context)),
            EXECUTION_SCHEMA,
            working_directory=execution_root if workspace_record is not None else None,
        )
        control_backup = self._capture_control_files(feature)
        before = snapshot_repository(execution_root)
        main_before = (
            snapshot_repository(self.store.root) if workspace_record is not None else before
        )
        try:
            result = provider.invoke(request)
        except ProviderError as exc:
            actual = changed_paths(before, snapshot_repository(execution_root))
            main_actual = (
                changed_paths(main_before, snapshot_repository(self.store.root))
                if workspace_record is not None
                else actual
            )
            detail = str(exc)
            if not changed_files_in_scope(task, actual):
                detail += "; provider mutated files outside scope: " + ", ".join(actual)
            if workspace_record is not None and main_actual:
                detail += "; provider mutated main worktree: " + ", ".join(main_actual)
            if any(path.startswith(".project/%s/" % feature) for path in main_actual):
                self._restore_control_files(feature, control_backup)
            phase, cleanup_error = self._discard_workspace(workspace_record)
            if cleanup_error:
                detail += "; " + cleanup_error
            self._record_failure(
                feature,
                task["id"],
                actor,
                detail,
                provider_name=provider.name,
                workspace_phase=phase,
            )
            raise

        actual_changed = changed_paths(before, snapshot_repository(execution_root))
        main_actual = (
            changed_paths(main_before, snapshot_repository(self.store.root))
            if workspace_record is not None
            else []
        )
        if main_actual:
            detail = "provider mutated main worktree during isolated execution: " + ", ".join(
                main_actual
            )
            if any(path.startswith(".project/%s/" % feature) for path in main_actual):
                self._restore_control_files(feature, control_backup)
            phase, cleanup_error = self._discard_workspace(workspace_record)
            if cleanup_error:
                detail += "; " + cleanup_error
            self._record_failure(
                feature,
                task["id"],
                actor,
                detail,
                provider_name=provider.name,
                workspace_phase=phase,
            )
            raise PolicyError(detail)
        if not changed_files_in_scope(task, actual_changed):
            detail = "provider mutated files outside task scope: " + ", ".join(actual_changed)
            if workspace_record is None and any(
                path.startswith(".project/%s/" % feature) for path in actual_changed
            ):
                self._restore_control_files(feature, control_backup)
            phase, cleanup_error = self._discard_workspace(workspace_record)
            if cleanup_error:
                detail += "; " + cleanup_error
            self._record_failure(
                feature,
                task["id"],
                actor,
                detail,
                provider_name=provider.name,
                workspace_phase=phase,
            )
            raise PolicyError(detail)
        written_sources = [
            contract_by_ref(state, reference)["source"]
            for reference in task.get("contract_writes", [])
        ]
        missing_sources = sorted(set(written_sources) - set(actual_changed))
        if result.get("outcome") == "success" and missing_sources:
            detail = "contract writer did not mutate declared sources: " + ", ".join(missing_sources)
            phase, cleanup_error = self._discard_workspace(workspace_record)
            if cleanup_error:
                detail += "; " + cleanup_error
            self._record_failure(
                feature,
                task["id"],
                actor,
                detail,
                provider_name=provider.name,
                workspace_phase=phase,
            )
            raise PolicyError(detail)

        verification_results: List[Dict[str, Any]] = []
        verification_failure = ""
        if result.get("outcome") == "success" and (
            task.get("verification_commands") or task.get("verification_profiles")
        ):
            verification_before = snapshot_repository(execution_root)
            verification_results = self._run_verification_commands(task, root=execution_root)
            verification_changed = changed_paths(
                verification_before, snapshot_repository(execution_root)
            )
            if verification_changed:
                verification_failure = "verification mutated repository files: " + ", ".join(
                    verification_changed
                )
            elif any(not item["passed"] for item in verification_results):
                verification_failure = "independent verification failed"

        artifact: Optional[PatchArtifact] = None
        if workspace_record is not None and result.get("outcome") == "success":
            try:
                artifact = self.workspace_manager.capture_patch(workspace_record)
            except WorkspaceError as exc:
                detail = str(exc)
                phase, cleanup_error = self._discard_workspace(workspace_record)
                if cleanup_error:
                    detail += "; " + cleanup_error
                self._record_failure(
                    feature,
                    task["id"],
                    actor,
                    detail,
                    provider_name=provider.name,
                    workspace_phase=phase,
                )
                raise
            if sorted(actual_changed) != list(artifact.changed_files):
                verification_failure = (
                    "workspace snapshot and Git patch changed paths differ: snapshot=%s patch=%s"
                    % (", ".join(actual_changed), ", ".join(artifact.changed_files))
                )
            elif sorted(set(result.get("changed_files", []))) != list(artifact.changed_files):
                verification_failure = "provider changed_files does not match the captured patch"

        with self.store.lock(feature):
            state = self.store.load_state(feature)
            task = task_by_id(state, task["id"])
            if task.get("state") != "running":
                raise EngineError("task changed state while provider was running")
            outcome = result["outcome"]
            if outcome == "success":
                try:
                    validate_success(task, result)
                    if verification_failure:
                        raise PolicyError(verification_failure)
                except PolicyError as exc:
                    task["verification_evidence"] = verification_results
                    phase, cleanup_error = self._discard_workspace(workspace_record)
                    if cleanup_error:
                        task.setdefault("workspace", {})["last_error"] = cleanup_error
                    if phase:
                        task.setdefault("workspace", {})["phase"] = phase
                    self._fail_in_state(state, task, str(exc))
                    self._provider_history(state, provider.name, "implementer", task["id"], "rejected")
                    self._commit(state, "gate_fail", actor, task=task["id"], detail=str(exc))
                    raise
                task["evidence"] = result["evidence"]
                task["verification_evidence"] = verification_results
                task["changed_files"] = result["changed_files"]
                task["actual_changed_files"] = (
                    list(artifact.changed_files) if artifact is not None else actual_changed
                )
                task["execution_summary"] = result["summary"]
                task["implementation_provider"] = provider.name
                if artifact is not None:
                    task["workspace"].update(
                        {
                            "phase": "review",
                            "patch_digest": artifact.digest,
                            "changed_files": list(artifact.changed_files),
                            "verified_at": utc_now(),
                        }
                    )
                task["state"] = (
                    "review"
                    if artifact is not None or task.get("review_required", True)
                    else "complete"
                )
                state["status"] = "awaiting_review" if task["state"] == "review" else "running"
                self._provider_history(state, provider.name, "implementer", task["id"], "success")
                self._commit(state, "execution_evidence", actor, task=task["id"], detail=result["summary"])
            elif outcome == "needs_replan":
                phase, cleanup_error = self._discard_workspace(workspace_record)
                if phase:
                    task.setdefault("workspace", {})["phase"] = phase
                if cleanup_error:
                    task.setdefault("workspace", {})["last_error"] = cleanup_error
                task["state"] = "failed"
                task["attempts"] = int(task.get("attempts", 0)) + 1
                task["last_failure"] = result["summary"]
                state["status"] = "needs_replan"
                self._provider_history(state, provider.name, "implementer", task["id"], "needs_replan")
                self._commit(state, "needs_replan", actor, task=task["id"], detail=result["summary"])
            else:
                phase, cleanup_error = self._discard_workspace(workspace_record)
                if phase:
                    task.setdefault("workspace", {})["phase"] = phase
                if cleanup_error:
                    task.setdefault("workspace", {})["last_error"] = cleanup_error
                self._fail_in_state(state, task, result["summary"])
                self._provider_history(state, provider.name, "implementer", task["id"], "failed")
                self._commit(state, "task_failed", actor, task=task["id"], detail=result["summary"])

        for item in result.get("memory", []):
            self.memory.add(
                feature,
                item["kind"],
                item["content"],
                tags=item["tags"],
                task=task["id"],
                actor=actor,
                importance=3,
            )
        return self.store.load_state(feature)

    def review_with_provider(
        self, feature: str, task_id: str, provider: Any, *, actor: str = "reviewer"
    ) -> Dict[str, Any]:
        state = self.store.load_state(feature)
        task = task_by_id(state, task_id)
        if task.get("state") != "review":
            raise EngineError("task %s is not awaiting review" % task_id)
        workspace_record: Optional[WorkspaceRecord] = None
        review_root = self.store.root
        expected_patch_digest: Optional[str] = None
        if self.workspace_manager is not None:
            workspace = task.get("workspace")
            if not isinstance(workspace, dict):
                raise EngineError("isolated task is missing workspace metadata")
            workspace_record = WorkspaceRecord.from_dict(workspace)
            review_root = self.workspace_manager.validate_owned(workspace_record)
            expected_patch_digest = workspace.get("patch_digest")
            if workspace.get("phase") != "review" or not isinstance(
                expected_patch_digest, str
            ):
                raise EngineError("isolated task workspace is not ready for review")
        effective_review_policy = (
            "independent"
            if self.independent_review_enabled
            and state.get("review_policy") == "independent"
            else "active-agent"
        )
        if (
            effective_review_policy == "independent"
            and task.get("implementation_provider") == provider.name
        ):
            raise PolicyError(
                "independent review requires a provider different from %s" % provider.name
            )
        context = self.memory.retrieve(
            feature,
            "%s review evidence" % task["title"],
            max_chars=self.context_budget,
            include_project_instructions=not self._provider_loads_project_instructions(provider),
        )
        request = ProviderRequest(
            "reviewer",
            self._review_prompt(
                state,
                task,
                self.memory.render_context(context),
                review_policy=effective_review_policy,
            ),
            REVIEW_SCHEMA,
            working_directory=review_root if workspace_record is not None else None,
        )
        control_backup = self._capture_control_files(feature)
        before = snapshot_repository(review_root)
        main_before = (
            snapshot_repository(self.store.root) if workspace_record is not None else before
        )
        try:
            result = provider.invoke(request)
        except Exception as exc:
            actual_changed = changed_paths(before, snapshot_repository(review_root))
            main_changed = (
                changed_paths(main_before, snapshot_repository(self.store.root))
                if workspace_record is not None
                else []
            )
            if actual_changed or main_changed:
                detail = (
                    self._review_mutation_detail(actual_changed, main_changed)
                    if workspace_record is not None
                    else "review provider mutated repository files: %s"
                    % ", ".join(actual_changed)
                )
                if workspace_record is not None:
                    if any(
                        path.startswith(".project/%s/" % feature)
                        for path in main_changed
                    ):
                        self._restore_control_files(feature, control_backup)
                    phase, cleanup_error = self._discard_workspace(workspace_record)
                    if cleanup_error:
                        detail += "; " + cleanup_error
                    self._record_review_failure(
                        feature,
                        task_id,
                        actor,
                        provider.name,
                        detail,
                        workspace_phase=phase,
                    )
                raise PolicyError(detail) from exc
            raise
        actual_changed = changed_paths(before, snapshot_repository(review_root))
        main_changed = (
            changed_paths(main_before, snapshot_repository(self.store.root))
            if workspace_record is not None
            else []
        )
        if actual_changed or main_changed:
            detail = (
                self._review_mutation_detail(actual_changed, main_changed)
                if workspace_record is not None
                else "review provider mutated repository files: %s"
                % ", ".join(actual_changed)
            )
            if workspace_record is not None:
                if any(
                    path.startswith(".project/%s/" % feature) for path in main_changed
                ):
                    self._restore_control_files(feature, control_backup)
                phase, cleanup_error = self._discard_workspace(workspace_record)
                if cleanup_error:
                    detail += "; " + cleanup_error
                self._record_review_failure(
                    feature,
                    task_id,
                    actor,
                    provider.name,
                    detail,
                    workspace_phase=phase,
                )
            raise PolicyError(detail)
        with self.store.lock(feature):
            state = self.store.load_state(feature)
            task = task_by_id(state, task_id)
            if task.get("state") != "review":
                raise EngineError("task changed state while reviewer was running")
            task.setdefault("reviews", []).append(
                {
                    "provider": provider.name,
                    "policy": effective_review_policy,
                    "verdict": result["verdict"],
                    "summary": result["summary"],
                    "findings": result["findings"],
                    "at": utc_now(),
                }
            )
            verdict = result["verdict"]
            severe = any(item["severity"] in {"major", "blocker"} for item in result["findings"])
            checked = set(result.get("evidence_checked", []))
            missing_checks = [
                criterion for criterion in task.get("acceptance_criteria", []) if criterion not in checked
            ]
            if verdict == "approve" and severe:
                raise PolicyError("review cannot approve with major or blocker findings")
            if verdict == "approve" and missing_checks:
                raise PolicyError(
                    "review did not check acceptance evidence for: %s" % "; ".join(missing_checks)
                )
            if verdict == "approve":
                if workspace_record is not None:
                    try:
                        promoted = self.workspace_manager.promote(
                            workspace_record, expected_patch_digest
                        )
                    except WorkspaceError as exc:
                        task["workspace"]["phase"] = "failed"
                        task["workspace"]["last_error"] = str(exc)
                        self._provider_history(
                            state, provider.name, "reviewer", task_id, "promotion_failed"
                        )
                        self._commit(
                            state,
                            "promotion_failed",
                            actor,
                            task=task_id,
                            detail=str(exc),
                        )
                        raise
                    if (
                        promoted.digest != expected_patch_digest
                        or list(promoted.changed_files)
                        != task.get("workspace", {}).get("changed_files")
                    ):
                        raise PolicyError("promoted patch metadata does not match reviewed evidence")
                    task["workspace"]["phase"] = "promoted"
                    task["workspace"]["promoted_at"] = utc_now()
                    try:
                        self.workspace_manager.cleanup(workspace_record)
                    except WorkspaceError as exc:
                        task["workspace"]["cleanup_pending"] = True
                        task["workspace"]["last_error"] = str(exc)
                task["state"] = "complete"
                refresh_readiness(state["tasks"])
                state["status"] = "complete" if all(t["state"] == "complete" for t in state["tasks"]) else "planned"
                if state["status"] == "complete" and state.get("run", {}).get("state") == "running":
                    state["run"]["state"] = "completed"
                    state["run"]["updated_at"] = utc_now()
                event = "task_completed"
            elif verdict == "revise":
                phase, cleanup_error = self._discard_workspace(workspace_record)
                if phase:
                    task.setdefault("workspace", {})["phase"] = phase
                if cleanup_error:
                    task.setdefault("workspace", {})["last_error"] = cleanup_error
                self._fail_in_state(state, task, result["summary"])
                state["status"] = "blocked" if task["state"] == "escalated" else "planned"
                event = "review_revision"
            else:
                phase, cleanup_error = self._discard_workspace(workspace_record)
                if phase:
                    task.setdefault("workspace", {})["phase"] = phase
                if cleanup_error:
                    task.setdefault("workspace", {})["last_error"] = cleanup_error
                task["state"] = "escalated"
                state["status"] = "blocked"
                event = "review_blocked"
            self._provider_history(state, provider.name, "reviewer", task_id, verdict)
            self._commit(state, event, actor, task=task_id, detail=result["summary"])
        self.memory.add(
            feature,
            "episodic",
            "Review %s for %s: %s" % (result["verdict"], task_id, result["summary"]),
            tags=["review", task_id, result["verdict"]],
            task=task_id,
            actor=actor,
            importance=4,
        )
        return self.store.load_state(feature)

    def cleanup_workspace(
        self,
        feature: str,
        task_id: str,
        *,
        abandon: bool = False,
        actor: str = "user",
    ) -> Dict[str, Any]:
        """Clean one owned workspace, requiring explicit abandonment of live evidence."""

        if self.workspace_manager is None:
            raise EngineError("isolated worktree management is disabled")
        with self.store.lock(feature):
            state = self.store.load_state(feature)
            task = task_by_id(state, task_id)
            workspace = task.get("workspace")
            if not isinstance(workspace, dict):
                raise EngineError("task %s has no owned workspace" % task_id)
            active = task.get("state") in {"running", "review"}
            if active and not abandon:
                raise EngineError(
                    "task %s workspace contains live %s evidence; pass --abandon explicitly"
                    % (task_id, task.get("state"))
                )
            record = WorkspaceRecord.from_dict(workspace)
            workspace_path = Path(record.workspace)
            if not workspace_path.exists() and not workspace_path.is_symlink():
                if workspace.get("phase") not in {"promoted", "discarded"}:
                    raise WorkspaceError("owned workspace is missing")
                changed = bool(
                    workspace.get("cleanup_pending") or workspace.get("last_error")
                )
                workspace["cleanup_pending"] = False
                workspace.pop("last_error", None)
                if changed:
                    self._commit(
                        state,
                        "workspace_reconciled",
                        actor,
                        task=task_id,
                        detail="terminal workspace was already absent; cleanup state cleared",
                    )
                return state
            self.workspace_manager.cleanup(record)
            previous_phase = workspace.get("phase")
            workspace["phase"] = (
                "promoted" if previous_phase == "promoted" else "discarded"
            )
            workspace["cleanup_pending"] = False
            workspace.pop("last_error", None)
            detail = "owned workspace removed"
            event = "workspace_cleaned"
            if active:
                detail = "owned workspace and live evidence explicitly abandoned"
                self._fail_in_state(state, task, detail)
                event = "workspace_abandoned"
            self._commit(state, event, actor, task=task_id, detail=detail)
            return state

    def _record_failure(
        self,
        feature: str,
        task_id: str,
        actor: str,
        detail: str,
        provider_name: str,
        *,
        workspace_phase: Optional[str] = None,
    ) -> None:
        with self.store.lock(feature):
            state = self.store.load_state(feature)
            task = task_by_id(state, task_id)
            if workspace_phase and isinstance(task.get("workspace"), dict):
                task["workspace"]["phase"] = workspace_phase
            self._fail_in_state(state, task, detail)
            self._provider_history(state, provider_name, "implementer", task_id, "provider_error")
            self._commit(state, "provider_error", actor, task=task_id, detail=detail)

    def _record_review_failure(
        self,
        feature: str,
        task_id: str,
        actor: str,
        provider_name: str,
        detail: str,
        *,
        workspace_phase: Optional[str] = None,
    ) -> None:
        with self.store.lock(feature):
            state = self.store.load_state(feature)
            task = task_by_id(state, task_id)
            if task.get("state") != "review":
                raise EngineError("task changed state while reviewer was running")
            if workspace_phase and isinstance(task.get("workspace"), dict):
                task["workspace"]["phase"] = workspace_phase
            self._fail_in_state(state, task, detail)
            self._provider_history(
                state, provider_name, "reviewer", task_id, "repository_mutation"
            )
            self._commit(state, "review_mutation", actor, task=task_id, detail=detail)

    def _discard_workspace(
        self, record: Optional[WorkspaceRecord]
    ) -> tuple[Optional[str], str]:
        if record is None or self.workspace_manager is None:
            return None, ""
        try:
            self.workspace_manager.cleanup(record)
        except WorkspaceError as exc:
            return "failed", "workspace cleanup failed: %s" % exc
        return "discarded", ""

    @staticmethod
    def _review_mutation_detail(
        workspace_changed: List[str], main_changed: List[str]
    ) -> str:
        details = []
        if workspace_changed:
            details.append("review provider mutated isolated files: %s" % ", ".join(workspace_changed))
        if main_changed:
            details.append("review provider mutated main worktree: %s" % ", ".join(main_changed))
        return "; ".join(details)

    def _capture_control_files(self, feature: str) -> Dict[str, Optional[str]]:
        directory = self.store.feature_dir(feature)
        backup: Dict[str, Optional[str]] = {}
        for name in ("state.json", "events.jsonl", "memory.jsonl", "plan.md", "tasks.md"):
            path = directory / name
            backup[name] = path.read_text(encoding="utf-8") if path.is_file() else None
        return backup

    def _restore_control_files(self, feature: str, backup: Dict[str, Optional[str]]) -> None:
        directory = self.store.feature_dir(feature)
        for name, content in backup.items():
            path = directory / name
            if content is None:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
            else:
                self.store.write_text_atomic(path, content)

    @staticmethod
    def _fail_in_state(state: Dict[str, Any], task: Dict[str, Any], detail: str) -> None:
        task["attempts"] = int(task.get("attempts", 0)) + 1
        task["last_failure"] = detail
        task["state"] = "escalated" if task["attempts"] >= MAX_ATTEMPTS else "failed"
        refresh_readiness(state["tasks"])
        state["status"] = "blocked" if task["state"] == "escalated" else "planned"

    def _commit(
        self,
        state: Dict[str, Any],
        event: str,
        actor: str,
        *,
        task: Optional[str] = None,
        detail: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        state["event_sequence"] = int(state.get("event_sequence", 0)) + 1
        touch(state, event, task=task) if task else touch(state, event)
        self.store.save_state(state["feature"], state)
        self.store.append_event(
            state["feature"],
            event,
            actor,
            task=task,
            detail=detail,
            data=data,
            sequence=state["event_sequence"],
        )
        write_projections(self.store, state)

    @staticmethod
    def _provider_history(
        state: Dict[str, Any], provider: str, role: str, task: Optional[str], outcome: str
    ) -> None:
        state.setdefault("provider_history", []).append(
            {"provider": provider, "role": role, "task": task, "outcome": outcome, "at": utc_now()}
        )

    def _refresh_feature_barriers(self, state: Dict[str, Any]) -> None:
        """Apply read-only cross-feature barrier results to local readiness."""

        dependencies = state.get("feature_dependencies", [])
        results = CrossFeatureDependencyResolver(self.store.root, state["feature"]).resolve(dependencies)
        state["feature_dependency_results"] = [
            {"feature": item.feature, "task": item.task, "satisfied": item.satisfied,
             "source": item.source, "diagnostic": item.diagnostic}
            for item in results
        ]
        if all(item.satisfied for item in results):
            refresh_readiness(state["tasks"])
            return
        reason = next((item.diagnostic for item in results if not item.satisfied), "feature dependency is incomplete")
        for task in state["tasks"]:
            if task.get("state") == "ready":
                task["state"] = "proposed"
            task["feature_dependency_block"] = reason

    def _run_verification_commands(
        self, task: Dict[str, Any], *, root: Optional[Path] = None
    ) -> List[Dict[str, Any]]:
        return run_verification(task, Path(root or self.store.root), self.store.root)

    def _merge_contract_state(
        self,
        previous: List[Dict[str, Any]],
        proposed: List[Dict[str, Any]],
        approvals: List[Dict[str, Any]],
        *,
        preserve: bool,
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Preserve approval only for an unchanged, still-matching contract."""

        previous_by_ref = {contract_ref(item): item for item in previous}
        merged: List[Dict[str, Any]] = []
        preserved_refs = set()
        for raw in proposed:
            contract = dict(raw)
            reference = contract_ref(contract)
            prior = previous_by_ref.get(reference)
            public_keys = (
                "id",
                "kind",
                "version",
                "owner",
                "source",
                "producers",
                "consumers",
                "compatibility",
                "change_type",
                "invariants",
                "verification",
                "rollout",
                "rollback",
            )
            unchanged = bool(
                preserve
                and prior
                and prior.get("status") == "approved"
                and all(prior.get(key) == contract.get(key) for key in public_keys)
            )
            if unchanged:
                try:
                    unchanged = source_digest(self.store.root, contract["source"]) == prior.get(
                        "source_hash"
                    )
                except PolicyError:
                    unchanged = False
            if unchanged:
                contract["status"] = "approved"
                contract["source_hash"] = prior["source_hash"]
                preserved_refs.add(reference)
            else:
                contract["status"] = "draft"
                contract["source_hash"] = "pending"
            merged.append(contract)
        return merged, [
            record for record in approvals if record.get("contract") in preserved_refs
        ]

    @staticmethod
    def _validate_completed_contracts(
        completed: Dict[str, Dict[str, Any]],
        previous: List[Dict[str, Any]],
        proposed: List[Dict[str, Any]],
    ) -> None:
        """Keep contracts referenced by completed tasks immutable across replans."""

        required = {
            reference
            for task in completed.values()
            for reference in (
                task.get("contract_reads", [])
                + task.get("contract_writes", [])
                + task.get("produces", [])
            )
        }
        previous_by_ref = {contract_ref(item): item for item in previous}
        proposed_by_ref = {contract_ref(item): item for item in proposed}
        public_keys = (
            "id",
            "kind",
            "version",
            "owner",
            "source",
            "producers",
            "consumers",
            "compatibility",
            "change_type",
            "invariants",
            "verification",
            "rollout",
            "rollback",
        )
        for reference in sorted(required):
            prior = previous_by_ref.get(reference)
            candidate = proposed_by_ref.get(reference)
            if prior is None or candidate is None:
                raise PolicyError(
                    "replan cannot remove contract %s referenced by a completed task" % reference
                )
            if any(prior.get(key) != candidate.get(key) for key in public_keys):
                raise PolicyError(
                    "replan cannot alter contract %s referenced by a completed task" % reference
                )

    @staticmethod
    def _plan_prompt(state: Dict[str, Any], context: str, *, replan: bool) -> str:
        existing = (
            json.dumps(
                {
                    "services": state.get("services", []),
                    "contracts": state.get("contracts", []),
                    "tasks": state.get("tasks", []),
                },
                ensure_ascii=False,
                indent=2,
            )
            if replan
            else "{}"
        )
        return (
            "You are the reasoning-plane planner. Generate a minimal executable task graph; "
            "the harness will validate and persist it. For multi-service work, declare the service "
            "registry, versioned contracts, one service per implementation task, contract read/write "
            "sets, data ownership, rollout, and rollback. Contract writers are Architect-owned and "
            "consumers depend on them. If no public cross-service contracts are created, leave contracts "
            "empty and omit contract_reads, contract_writes, and produces on tasks. Do not perform implementation.\n\n"
            "Goal: %s\nConstraints: %s\nVerification: %s\nExisting tasks for replan: %s\n\n"
            "Requirement registry (every ID must be covered by task requirement_refs): %s\n"
            "Relevant context with provenance:\n%s"
            % (
                state["goal"],
                state.get("constraints", []),
                state.get("verification", []),
                existing,
                state.get("requirements", []),
                context,
            )
        )

    @staticmethod
    def _execution_prompt(state: Dict[str, Any], task: Dict[str, Any], context: str) -> str:
        graph = HarnessEngine._task_graph_context(state, task)
        workflow, owner_contract = HarnessEngine._execution_profile(task)
        return (
            "Use the `%s` skill and follow the `%s` owner contract for this task. Load those "
            "task-specific files on demand; do not load unrelated skills or agent contracts. "
            "Implement exactly one bounded task. Do not expand file scope. The harness owns "
            "`.project/`, `features/`, and `.workspace/`; do not edit them. Run checks that prove "
            "each acceptance criterion. After all tool work is complete, return exactly one JSON "
            "object that validates against the final-result schema below; do not emit progress JSON "
            "objects. Never change an undeclared service or contract.\n\nFinal-result schema:\n%s"
            "\n\nGoal: %s\n\nService/contract graph: %s\n\nContext:\n%s\n\nTask: %s"
            % (
                workflow,
                owner_contract,
                json.dumps(EXECUTION_SCHEMA, ensure_ascii=False, separators=(",", ":")),
                state["goal"],
                graph,
                context,
                json.dumps(task, ensure_ascii=False, indent=2),
            )
        )

    @staticmethod
    def _review_prompt(
        state: Dict[str, Any],
        task: Dict[str, Any],
        context: str,
        *,
        review_policy: str = "active-agent",
    ) -> str:
        graph = HarnessEngine._task_graph_context(state, task)
        review_instruction = (
            "Independently review the task"
            if review_policy == "independent"
            else "Perform an active-agent review of the task; do not label it independent"
        )
        return (
            "%s against its contract, security, correctness, consistency, "
            "and evidence, including service ownership and contract compatibility. Do not edit files. "
            "When Bash is available, use it only for non-mutating verification such as tests and "
            "Git diff/status inspection. For an isolated workspace, the exact review patch is staged "
            "only in that disposable workspace; inspect it with `git diff --cached`. After all checks, "
            "return exactly one JSON object that validates against the final-review schema below; do not "
            "emit progress JSON objects.\n\nFinal-review schema:\n%s\n\n"
            "Goal: %s\n\nService/contract graph: %s\n\nContext:\n%s\n\nTask and evidence: %s"
            % (
                review_instruction,
                json.dumps(REVIEW_SCHEMA, ensure_ascii=False, separators=(",", ":")),
                state["goal"],
                graph,
                context,
                json.dumps(task, ensure_ascii=False, indent=2),
            )
        )

    @staticmethod
    def _provider_loads_project_instructions(provider: Any) -> bool:
        return bool(getattr(provider, "loads_project_instructions", False))

    @staticmethod
    def _execution_profile(task: Dict[str, Any]) -> tuple[str, str]:
        owner = str(task.get("owner") or "backend")
        if owner == "architect":
            workflow = (
                "ai-kit-design-contract"
                if task.get("contract_writes")
                else "ai-kit-assess-architecture"
            )
        else:
            workflow = {
                "database": "ai-kit-migrate-data",
                "qa": "ai-kit-validate-quality",
                "reviewer": "ai-kit-review",
            }.get(owner, "ai-kit-implement")
        return workflow, ".ai-kit/agents/%s.md" % owner

    @staticmethod
    def _task_graph_context(state: Dict[str, Any], task: Dict[str, Any]) -> str:
        references = set(
            task.get("contract_reads", [])
            + task.get("contract_writes", [])
            + task.get("produces", [])
        )
        service_ids = {task.get("service")} if task.get("service") else set()
        contracts = [
            contract
            for contract in state.get("contracts", [])
            if contract_ref(contract) in references
        ]
        for contract in contracts:
            service_ids.update(contract.get("producers", []))
            service_ids.update(contract.get("consumers", []))
        services = [
            service for service in state.get("services", []) if service.get("id") in service_ids
        ]
        return json.dumps(
            {"services": services, "contracts": contracts}, ensure_ascii=False, indent=2
        )


def next_schedulable_for_id(
    state: Dict[str, Any], task_id: str, *, root: Optional[Any] = None
) -> Optional[Dict[str, Any]]:
    """Return a specific ready task only when dependencies and approvals pass."""

    refresh_readiness(state.get("tasks", []))
    task = task_by_id(state, task_id)
    if task.get("state") != "ready":
        return None
    from policy import task_is_approved

    if not task_is_approved(state, task):
        return None
    validate_contract_readiness(state, task, root=root)
    return task
