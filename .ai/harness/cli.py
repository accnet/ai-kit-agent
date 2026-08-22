#!/usr/bin/env python3
"""Explicit command-line interface for the AI-Kit agent harness."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, Optional

from engine import EngineError, HarnessEngine, NoTaskAvailable
from memory import MemoryError
from models import task_by_id
from policy import ApprovalRequired, PolicyError, task_is_approved
from providers import (
    ClaudeProvider,
    CodexProvider,
    ProviderError,
    ProviderRequest,
    ScriptedProvider,
)
from store import LockError, RepositoryStore, StoreError
from worktrees import GitWorkspaceManager, WorkspaceError


class ConfiguredProvider:
    """Apply repository model, effort, timeout, and output defaults."""

    def __init__(self, provider: Any, config: Dict[str, Any], output_limit: int) -> None:
        self.provider = provider
        self.name = provider.name
        self.model = config.get("model")
        self.reasoning_effort = dict(config.get("reasoning_effort", {}))
        self.timeout = int(config.get("timeout_seconds", 1200))
        self.output_limit = int(output_limit)

    @property
    def loads_project_instructions(self) -> bool:
        return bool(getattr(self.provider, "loads_project_instructions", False))

    def invoke(self, request: ProviderRequest) -> Dict[str, Any]:
        configured = replace(
            request,
            model=request.model or self.model,
            reasoning_effort=(
                request.reasoning_effort
                or self.reasoning_effort.get(request.role)
            ),
            timeout_seconds=self.timeout,
            max_output_chars=self.output_limit,
        )
        return self.provider.invoke(configured)


def load_config(root: Path) -> Dict[str, Any]:
    path = root / ".ai" / "harness" / "config.json"
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EngineError("invalid harness config: %s" % path) from exc
    if config.get("schema_version") != 1 or not isinstance(config.get("providers"), dict):
        raise EngineError("unsupported harness configuration schema")
    kit_path = root / ".ai" / "config.json"
    try:
        kit_config = json.loads(kit_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EngineError("invalid AI-Kit config: %s" % kit_path) from exc
    review = kit_config.get("review")
    if kit_config.get("schema_version") != 1 or not isinstance(review, dict):
        raise EngineError("unsupported AI-Kit configuration schema: %s" % kit_path)
    if review.get("required") is not True:
        raise EngineError("AI-Kit config must keep review.required=true")
    if not isinstance(review.get("independent_enabled"), bool):
        raise EngineError(
            "AI-Kit config review.independent_enabled must be true or false"
        )
    execution = kit_config.get("execution")
    codex_cli = execution.get("codex_cli") if isinstance(execution, dict) else None
    if not isinstance(codex_cli, dict):
        raise EngineError("AI-Kit config execution.codex_cli must be an object")
    if not isinstance(codex_cli.get("enabled"), bool):
        raise EngineError(
            "AI-Kit config execution.codex_cli.enabled must be true or false"
        )
    model = codex_cli.get("model")
    if not isinstance(model, str) or not model.strip():
        raise EngineError(
            "AI-Kit config execution.codex_cli.model must be a non-empty string"
        )
    isolated_worktree = execution.get("isolated_worktree")
    if not isinstance(isolated_worktree, dict):
        raise EngineError(
            "AI-Kit config execution.isolated_worktree must be an object"
        )
    if not isinstance(isolated_worktree.get("required"), bool):
        raise EngineError(
            "AI-Kit config execution.isolated_worktree.required must be true or false"
        )
    quality = kit_config.get("quality")
    quality_providers = quality.get("providers") if isinstance(quality, dict) else None
    expected_providers = {
        "codex-cli": ("codex", "gpt-5.6-sol"),
        "claude-cli": ("claude", "claude-sonnet-5"),
    }
    if not isinstance(quality_providers, dict):
        raise EngineError("AI-Kit config quality.providers must be an object")
    for cli_name, (provider_name, required_model) in expected_providers.items():
        settings = quality_providers.get(cli_name)
        if not isinstance(settings, dict) or settings.get("provider") != provider_name:
            raise EngineError(
                "AI-Kit config quality.providers.%s.provider must be %s"
                % (cli_name, provider_name)
            )
        if settings.get("model") != required_model:
            raise EngineError(
                "AI-Kit config quality.providers.%s.model must be %s"
                % (cli_name, required_model)
            )
    for route_name in ("qa", "review"):
        route = quality.get(route_name)
        if not isinstance(route, dict):
            raise EngineError("AI-Kit config quality.%s must be an object" % route_name)
        if not isinstance(route.get("enabled"), bool):
            raise EngineError(
                "AI-Kit config quality.%s.enabled must be true or false" % route_name
            )
        if route.get("provider") not in expected_providers:
            raise EngineError(
                "AI-Kit config quality.%s.provider must be codex-cli or claude-cli"
                % route_name
            )
    allowed_efforts = {"low", "medium", "high", "xhigh", "max"}
    for provider_name, settings in config["providers"].items():
        if not isinstance(settings, dict):
            raise EngineError("harness provider %s must be an object" % provider_name)
        efforts = settings.get("reasoning_effort", {})
        if not isinstance(efforts, dict):
            raise EngineError(
                "harness provider %s reasoning_effort must be an object"
                % provider_name
            )
        unexpected = set(efforts) - {"planner", "implementer", "reviewer"}
        invalid = {value for value in efforts.values() if value not in allowed_efforts}
        if unexpected or invalid:
            raise EngineError(
                "harness provider %s has invalid per-role reasoning effort"
                % provider_name
            )
    config["kit_policy"] = kit_config
    return config


def provider_from_args(
    args: argparse.Namespace,
    root: Path,
    config: Dict[str, Any],
    *,
    provider_name: Optional[str] = None,
    model: Optional[str] = None,
) -> Any:
    name = provider_name or args.provider
    if not name:
        raise EngineError("--provider is required when no execution policy selects one")
    if name == "scripted":
        if not args.response:
            raise EngineError("--response JSON file is required for the scripted provider")
        try:
            response = json.loads(Path(args.response).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EngineError("cannot read scripted provider response: %s" % args.response) from exc
        return ScriptedProvider([response])
    settings = config["providers"].get(name)
    if not isinstance(settings, dict):
        raise EngineError("provider is not configured: %s" % name)
    settings = dict(settings)
    if model is not None:
        settings["model"] = model
    executable = str(settings.get("executable") or name)
    raw = CodexProvider(root, executable) if name == "codex" else ClaudeProvider(root, executable)
    return ConfiguredProvider(raw, settings, int(config.get("provider_output_limit_chars", 200_000)))


def task_provider_from_args(
    args: argparse.Namespace,
    root: Path,
    config: Dict[str, Any],
    *,
    task_owner: Optional[str] = None,
) -> Any:
    if task_owner == "qa":
        provider = quality_provider_from_args(args, root, config, route_name="qa")
        if provider is not None:
            return provider
        if args.provider is None:
            raise EngineError(
                "QA CLI routing is disabled; pass --provider explicitly or set "
                "quality.qa.enabled=true in .ai/config.json"
            )
        return provider_from_args(args, root, config)
    policy = config["kit_policy"]["execution"]["codex_cli"]
    if policy["enabled"]:
        if args.provider not in {None, "codex"}:
            raise EngineError(
                "Codex CLI task execution is enabled; step only accepts --provider codex"
            )
        if args.response:
            raise EngineError(
                "--response is unavailable while Codex CLI task execution is enabled"
            )
        return provider_from_args(
            args,
            root,
            config,
            provider_name="codex",
            model=policy["model"],
        )
    if args.provider is None:
        raise EngineError(
            "Codex CLI task execution is disabled; pass --provider explicitly or set "
            "execution.codex_cli.enabled=true in .ai/config.json"
        )
    return provider_from_args(args, root, config)


def quality_provider_from_args(
    args: argparse.Namespace,
    root: Path,
    config: Dict[str, Any],
    *,
    route_name: str,
) -> Optional[Any]:
    quality = config["kit_policy"]["quality"]
    route = quality[route_name]
    if not route["enabled"]:
        return None
    cli_name = route["provider"]
    settings = quality["providers"][cli_name]
    provider_name = settings["provider"]
    if args.provider not in {None, provider_name}:
        raise EngineError(
            "%s CLI routing is enabled with %s; conflicting --provider %s is not allowed"
            % (route_name.upper(), cli_name, args.provider)
        )
    if args.response:
        raise EngineError(
            "--response is unavailable while %s CLI routing is enabled"
            % route_name.upper()
        )
    return provider_from_args(
        args,
        root,
        config,
        provider_name=provider_name,
        model=settings["model"],
    )


def review_provider_from_args(
    args: argparse.Namespace, root: Path, config: Dict[str, Any]
) -> Any:
    provider = quality_provider_from_args(
        args, root, config, route_name="review"
    )
    if provider is not None:
        return provider
    return provider_from_args(args, root, config)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="ai-kit-harness",
        description="LLM-first planning and execution with durable control-plane state.",
    )
    result.add_argument("--root", type=Path, default=None, help="AI-Kit repository root")
    sub = result.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="initialize canonical state for an existing feature brief")
    init.add_argument("feature")
    init.add_argument("--goal", required=True)
    init.add_argument("--constraint", action="append", default=[])
    init.add_argument("--verify", action="append", default=[])
    init.add_argument(
        "--requirement",
        action="append",
        default=[],
        metavar="R<N>=TEXT",
        help="declare a requirement that every accepted plan must cover",
    )
    init.add_argument("--size", choices=["trivial", "standard", "large"], default="standard")
    init.add_argument(
        "--review-policy",
        choices=["independent", "active-agent"],
        default=None,
        help="override the configured default; independent must be enabled in .ai/config.json",
    )
    init.add_argument("--actor", default="user")

    plan = sub.add_parser("plan", help="ask an explicitly selected provider to plan or replan")
    plan.add_argument("feature")
    add_provider_args(plan)
    plan.add_argument("--replan", action="store_true")

    next_parser = sub.add_parser("next", help="show the next dependency-safe task without calling a model")
    next_parser.add_argument("feature")

    run = sub.add_parser("run", help="start a durable control session without calling a model")
    run.add_argument("feature")
    run.add_argument("--actor", default="user")

    pause = sub.add_parser("pause", help="pause a running control session")
    pause.add_argument("feature")
    pause.add_argument("--reason", default="")
    pause.add_argument("--actor", default="user")

    resume = sub.add_parser("resume", help="resume a paused or needs-input session")
    resume.add_argument("feature")
    resume.add_argument("--actor", default="user")

    needs_input = sub.add_parser("needs-input", help="persist a blocking input request")
    needs_input.add_argument("feature")
    needs_input.add_argument("--reason", required=True)
    needs_input.add_argument("--actor", default="orchestrator")

    cancel = sub.add_parser("cancel", help="cancel the current control session")
    cancel.add_argument("feature")
    cancel.add_argument("--reason", default="")
    cancel.add_argument("--actor", default="user")

    step = sub.add_parser(
        "step",
        help="execute one task with an explicit provider or the configured Codex CLI policy",
    )
    step.add_argument("feature")
    add_provider_args(step, required=False)
    step.add_argument("--task")

    review = sub.add_parser(
        "review",
        help="review one task with an explicit provider or configured quality route",
    )
    review.add_argument("feature")
    review.add_argument("task")
    add_provider_args(review, required=False)

    approve = sub.add_parser("approve", help="record explicit approval for a risky task")
    approve.add_argument("feature")
    approve.add_argument("task")
    approve.add_argument("--approved-by", required=True)
    approve.add_argument("--note", default="")

    approve_plan = sub.add_parser("approve-plan", help="approve the current large plan revision")
    approve_plan.add_argument("feature")
    approve_plan.add_argument("--approved-by", required=True)
    approve_plan.add_argument("--note", default="")

    approve_contract = sub.add_parser(
        "approve-contract", help="approve and hash the current source of a versioned contract"
    )
    approve_contract.add_argument("feature")
    approve_contract.add_argument("contract", help="contract reference in <id>@<version> form")
    approve_contract.add_argument("--approved-by", required=True)
    approve_contract.add_argument("--note", default="")

    deprecate_contract = sub.add_parser(
        "deprecate-contract", help="explicitly deprecate an approved contract version"
    )
    deprecate_contract.add_argument("feature")
    deprecate_contract.add_argument("contract", help="contract reference in <id>@<version> form")
    deprecate_contract.add_argument("--deprecated-by", required=True)
    deprecate_contract.add_argument("--note", default="")

    remember = sub.add_parser("remember", help="append a durable memory without calling a model")
    remember.add_argument("feature")
    remember.add_argument("--kind", choices=["working", "episodic", "semantic"], required=True)
    remember.add_argument("--content", required=True)
    remember.add_argument("--source")
    remember.add_argument("--tag", action="append", default=[])
    remember.add_argument("--task")
    remember.add_argument("--importance", type=int, choices=range(1, 6), default=3)
    remember.add_argument("--actor", default="user")

    context = sub.add_parser("context", help="retrieve a bounded provenance-aware context pack")
    context.add_argument("feature")
    context.add_argument("--query", required=True)
    context.add_argument("--budget", type=int)
    context.add_argument("--json", action="store_true")

    status = sub.add_parser("status", help="show canonical feature state without calling a model")
    status.add_argument("feature")
    status.add_argument("--full", action="store_true")

    repair = sub.add_parser("repair", help="repair a missing final event or stale projections")
    repair.add_argument("feature")
    repair.add_argument("--actor", default="recovery")

    cleanup = sub.add_parser(
        "cleanup",
        help="remove an owned disposable workspace after completion or explicit abandonment",
    )
    cleanup.add_argument("feature")
    cleanup.add_argument("task")
    cleanup.add_argument(
        "--abandon",
        action="store_true",
        help="explicitly discard evidence for a running or review task",
    )
    cleanup.add_argument("--actor", default="user")
    return result


def add_provider_args(target: argparse.ArgumentParser, *, required: bool = True) -> None:
    target.add_argument(
        "--provider", choices=["codex", "claude", "scripted"], required=required
    )
    target.add_argument("--response", help="offline JSON response file for --provider scripted")


def status_view(state: Dict[str, Any]) -> Dict[str, Any]:
    counts: Dict[str, int] = {}
    approvals = []
    for task in state.get("tasks", []):
        task_state = task.get("state", "unknown")
        counts[task_state] = counts.get(task_state, 0) + 1
        if task.get("approval_required") and task_state == "ready" and not task_is_approved(state, task):
            approvals.append(task["id"])
    workspaces = {
        task["id"]: {
            "phase": task["workspace"].get("phase"),
            "base_commit": task["workspace"].get("base_commit"),
            "patch_digest": task["workspace"].get("patch_digest"),
            "changed_files": task["workspace"].get("changed_files", []),
            "cleanup_pending": task["workspace"].get("cleanup_pending", False),
        }
        for task in state.get("tasks", [])
        if isinstance(task.get("workspace"), dict)
    }
    return {
        "feature": state["feature"],
        "goal": state["goal"],
        "status": state["status"],
        "plan_revision": state.get("plan_revision", 0),
        "run": state.get("run", {"state": "idle"}),
        "requirements": state.get("requirements", []),
        "counts": counts,
        "approval_candidates": approvals,
        "contracts": {
            "%s@%s" % (contract.get("id"), contract.get("version")): contract.get("status")
            for contract in state.get("contracts", [])
        },
        "workspaces": workspaces,
        "last_transition": state.get("last_transition"),
    }


def main(argv: Optional[list] = None) -> int:
    args = parser().parse_args(argv)
    try:
        root = (args.root or Path(__file__).resolve().parents[2]).resolve()
        config = load_config(root)
        store = RepositoryStore(root)
        review_config = config["kit_policy"]["review"]
        isolation_config = config["kit_policy"]["execution"]["isolated_worktree"]
        workspace_manager = (
            GitWorkspaceManager(root) if isolation_config["required"] else None
        )
        engine = HarnessEngine(
            store,
            context_budget=int(config.get("context_budget_chars", 16_000)),
            independent_review_enabled=review_config["independent_enabled"],
            workspace_manager=workspace_manager,
        )

        if args.command == "init":
            requirements = []
            for value in args.requirement:
                requirement_id, separator, text_value = value.partition("=")
                if not separator:
                    raise EngineError("--requirement must use R<N>=TEXT")
                requirements.append({"id": requirement_id, "text": text_value})
            value = engine.initialize(
                args.feature,
                args.goal,
                constraints=args.constraint,
                verification=args.verify,
                requirements=requirements,
                size=args.size,
                review_policy=args.review_policy,
                actor=args.actor,
            )
        elif args.command == "plan":
            provider = provider_from_args(args, root, config)
            value = engine.plan_with_provider(args.feature, provider, replan=args.replan)
        elif args.command == "next":
            task = engine.next_task(args.feature)
            if task is None:
                raise NoTaskAvailable("no dependency-ready task is available")
            value = task
        elif args.command == "run":
            value = engine.start_run(args.feature, actor=args.actor)
        elif args.command == "pause":
            value = engine.pause_run(
                args.feature, actor=args.actor, reason=args.reason
            )
        elif args.command == "resume":
            value = engine.resume_run(args.feature, actor=args.actor)
        elif args.command == "needs-input":
            value = engine.request_input(
                args.feature, actor=args.actor, reason=args.reason
            )
        elif args.command == "cancel":
            value = engine.cancel_run(
                args.feature, actor=args.actor, reason=args.reason
            )
        elif args.command == "step":
            if args.task:
                selected_task = task_by_id(store.load_state(args.feature), args.task)
            else:
                selected_task = engine.next_task(args.feature)
                if selected_task is None:
                    raise NoTaskAvailable("no dependency-ready task is available")
            provider = task_provider_from_args(
                args,
                root,
                config,
                task_owner=selected_task.get("owner"),
            )
            value = engine.execute_with_provider(
                args.feature, provider, task_id=selected_task["id"]
            )
        elif args.command == "review":
            provider = review_provider_from_args(args, root, config)
            value = engine.review_with_provider(args.feature, args.task, provider)
        elif args.command == "approve":
            value = engine.approve_task(
                args.feature, args.task, approved_by=args.approved_by, note=args.note
            )
        elif args.command == "approve-plan":
            value = engine.approve_plan(
                args.feature, approved_by=args.approved_by, note=args.note
            )
        elif args.command == "approve-contract":
            value = engine.approve_contract(
                args.feature,
                args.contract,
                approved_by=args.approved_by,
                note=args.note,
            )
        elif args.command == "deprecate-contract":
            value = engine.deprecate_contract(
                args.feature,
                args.contract,
                deprecated_by=args.deprecated_by,
                note=args.note,
            )
        elif args.command == "remember":
            value = engine.memory.add(
                args.feature,
                args.kind,
                args.content,
                source=args.source,
                tags=args.tag,
                task=args.task,
                importance=args.importance,
                actor=args.actor,
            )
        elif args.command == "context":
            budget = args.budget or int(config.get("context_budget_chars", 16_000))
            value = engine.memory.retrieve(args.feature, args.query, max_chars=budget)
            if not args.json:
                print(engine.memory.render_context(value))
                print("\n[context: %d/%d chars]" % (value["used_chars"], value["budget_chars"]))
                return 0
        elif args.command == "status":
            state = store.load_state(args.feature)
            value = state if args.full else status_view(state)
            value["artifacts"] = engine.artifact_status(args.feature)
        elif args.command == "repair":
            value = engine.repair_artifacts(args.feature, actor=args.actor)
        elif args.command == "cleanup":
            value = engine.cleanup_workspace(
                args.feature,
                args.task,
                abandon=args.abandon,
                actor=args.actor,
            )
        else:
            raise EngineError("unknown command")
        print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))
        return 0
    except (ApprovalRequired, NoTaskAvailable) as exc:
        print("BLOCKED: %s" % exc, file=sys.stderr)
        return 3
    except (
        EngineError,
        MemoryError,
        PolicyError,
        ProviderError,
        StoreError,
        LockError,
        WorkspaceError,
    ) as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2
    except KeyError as exc:
        print("ERROR: %s" % exc.args[0], file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
