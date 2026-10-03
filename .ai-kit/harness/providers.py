"""Safe structured-output adapters for scripted, Codex, Claude, and Grok providers."""

from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union

from schemas import SchemaError, validate


BYPASS_FRAGMENTS = ("bypass-approvals", "bypasspermissions", "skip-permissions", "ignore-rules")
REASONING_EFFORTS = {"low", "medium", "high", "xhigh", "max"}


class ProviderError(RuntimeError):
    """Raised when a provider cannot return safe schema-valid output."""


@dataclass(frozen=True)
class ProviderRequest:
    role: str
    prompt: str
    schema: Dict[str, Any]
    model: Optional[str] = None
    reasoning_effort: Optional[str] = None
    timeout_seconds: int = 900
    max_output_chars: int = 200_000
    working_directory: Optional[Path] = None

    def __post_init__(self) -> None:
        if self.role not in {"planner", "implementer", "reviewer"}:
            raise ProviderError("provider role must be planner, implementer, or reviewer")
        if not self.prompt.strip():
            raise ProviderError("provider prompt cannot be empty")
        if self.reasoning_effort is not None and self.reasoning_effort not in REASONING_EFFORTS:
            raise ProviderError(
                "provider reasoning effort must be low, medium, high, xhigh, or max"
            )
        if self.timeout_seconds < 1 or self.timeout_seconds > 7200:
            raise ProviderError("provider timeout must be between 1 and 7200 seconds")
        if self.max_output_chars < 256 or self.max_output_chars > 2_000_000:
            raise ProviderError("provider output limit must be between 256 and 2000000 characters")
        if self.working_directory is not None:
            candidate = Path(self.working_directory)
            if not candidate.is_absolute():
                candidate = Path.cwd() / candidate
            if any(path.is_symlink() for path in (candidate, *candidate.parents)):
                raise ProviderError("provider working directory cannot use symlinks")
            if not candidate.is_dir():
                raise ProviderError("provider working directory must be an existing directory")
            object.__setattr__(self, "working_directory", candidate.resolve(strict=True))


class ScriptedProvider:
    """Offline provider used by tests and deterministic operator workflows."""

    name = "scripted"
    loads_project_instructions = False

    def __init__(self, responses: Iterable[Union[str, Dict[str, Any]]]) -> None:
        self._responses = list(responses)
        self.calls: List[ProviderRequest] = []

    def invoke(self, request: ProviderRequest) -> Dict[str, Any]:
        self.calls.append(request)
        if not self._responses:
            raise ProviderError("scripted provider has no response remaining")
        response = self._responses.pop(0)
        if isinstance(response, str):
            if len(response) > request.max_output_chars:
                raise ProviderError("provider output exceeds configured limit")
            try:
                value = json.loads(response)
            except json.JSONDecodeError as exc:
                raise ProviderError("provider returned invalid JSON") from exc
        else:
            value = response
            if len(json.dumps(value, ensure_ascii=False)) > request.max_output_chars:
                raise ProviderError("provider output exceeds configured limit")
        try:
            validate(value, request.schema)
        except SchemaError as exc:
            raise ProviderError("provider output violates schema: %s" % exc) from exc
        return value


class SubprocessProvider:
    name = "subprocess"

    def __init__(self, root: Path, executable: str) -> None:
        self.root = Path(root).resolve()
        self.executable = executable

    def command_preview(self, request: ProviderRequest) -> List[str]:
        return self.build_command(
            request,
            Path("/tmp/ai-kit-schema.json"),
            Path("/tmp/ai-kit-output.json"),
            Path("/tmp/ai-kit-prompt.md"),
        )

    def request_root(self, request: ProviderRequest) -> Path:
        return request.working_directory or self.root

    def build_command(
        self,
        request: ProviderRequest,
        schema_path: Path,
        output_path: Path,
        prompt_path: Path,
    ) -> List[str]:
        raise NotImplementedError

    def stdin_input(self, request: ProviderRequest) -> Optional[str]:
        return request.prompt

    def output_schema(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        return schema

    def normalize_output(
        self, value: Dict[str, Any], schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        del schema
        return value

    def invoke(self, request: ProviderRequest) -> Dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="ai-kit-provider-") as directory:
            self._reset_metrics()
            temp = Path(directory)
            schema_path = temp / "schema.json"
            output_path = temp / "output.json"
            prompt_path = temp / "prompt.md"
            schema_path.write_text(
                json.dumps(self.output_schema(request.schema)), encoding="utf-8"
            )
            prompt_path.write_text(request.prompt, encoding="utf-8")
            command = self.build_command(request, schema_path, output_path, prompt_path)
            raw = self._run_subprocess(request, command, output_path)
            value = self.normalize_output(self.parse_output(raw), request.schema)
            try:
                validate(value, request.schema)
            except SchemaError as exc:
                raise ProviderError("provider output violates schema: %s" % exc) from exc
            return value

    def _run_subprocess(
        self,
        request: ProviderRequest,
        command: Sequence[str],
        output_path: Path,
    ) -> str:
        """Run one provider command and return its bounded raw output."""

        self._assert_safe_command(command)
        if not hasattr(self, "last_invocation_metrics"):
            self._reset_metrics()
        self.last_invocation_metrics["subprocess_calls"] += 1
        self.last_invocation_metrics["resume_calls"] = max(0, self.last_invocation_metrics["subprocess_calls"] - 1)
        try:
            result = subprocess.run(
                command,
                input=self.stdin_input(request),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(self.request_root(request)),
                timeout=request.timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ProviderError("provider executable not found: %s" % self.executable) from exc
        except subprocess.TimeoutExpired as exc:
            self._count_streams(exc.stdout, exc.stderr)
            raise ProviderError("provider timed out after %d seconds" % request.timeout_seconds) from exc
        self._count_streams(result.stdout, result.stderr)
        if result.returncode != 0:
            detail = result.stderr.strip()[-2000:]
            raise ProviderError("provider exited %d: %s" % (result.returncode, detail or "no error output"))
        raw = self.extract_output(result.stdout, output_path)
        if len(raw) > request.max_output_chars:
            raise ProviderError("provider output exceeds configured limit")
        return raw

    def _reset_metrics(self):
        self.last_invocation_metrics = {"subprocess_calls": 0, "resume_calls": 0,
                                        "stdout_bytes": 0, "stderr_bytes": 0}

    def _count_streams(self, stdout, stderr):
        for name, value in (("stdout_bytes", stdout), ("stderr_bytes", stderr)):
            self.last_invocation_metrics[name] += len(value if isinstance(value, bytes)
                                                      else (value or "").encode("utf-8"))

    def extract_output(self, stdout: str, output_path: Path) -> str:
        return output_path.read_text(encoding="utf-8") if output_path.is_file() else stdout

    def parse_output(self, raw: str) -> Dict[str, Any]:
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProviderError("provider returned invalid JSON") from exc
        if not isinstance(value, dict):
            raise ProviderError("provider output must be a JSON object")
        return value

    @staticmethod
    def _assert_safe_command(command: Sequence[str]) -> None:
        joined = " ".join(command).lower()
        if any(fragment in joined for fragment in BYPASS_FRAGMENTS):
            raise ProviderError("provider command contains a forbidden bypass flag")


class CodexProvider(SubprocessProvider):
    name = "codex"
    loads_project_instructions = True

    def __init__(self, root: Path, executable: str = "codex") -> None:
        super().__init__(root, executable)

    def output_schema(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        return _codex_strict_schema(schema)

    def normalize_output(
        self, value: Dict[str, Any], schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        normalized = _strip_optional_nulls(value, schema)
        if not isinstance(normalized, dict):
            raise ProviderError("provider output must be a JSON object")
        return normalized

    def build_command(
        self,
        request: ProviderRequest,
        schema_path: Path,
        output_path: Path,
        prompt_path: Path,
    ) -> List[str]:
        del prompt_path
        sandbox = "workspace-write" if request.role == "implementer" else "read-only"
        command = [
            self.executable,
            "exec",
            "--cd",
            str(self.request_root(request)),
            "--sandbox",
            sandbox,
            "--skip-git-repo-check",
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(output_path),
        ]
        if request.model:
            command.extend(["--model", request.model])
        if request.reasoning_effort:
            command.extend(
                ["--config", 'model_reasoning_effort="%s"' % request.reasoning_effort]
            )
        command.append("-")
        self._assert_safe_command(command)
        return command


def _codex_strict_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Convert canonical optional properties to OpenAI strict nullable fields."""

    result = dict(schema)
    if schema.get("type") == "object" and isinstance(schema.get("properties"), dict):
        canonical_required = set(schema.get("required", []))
        properties: Dict[str, Any] = {}
        for name, child in schema["properties"].items():
            converted = _codex_strict_schema(child)
            properties[name] = (
                converted
                if name in canonical_required
                else {"anyOf": [converted, {"type": "null"}]}
            )
        result["properties"] = properties
        result["required"] = list(properties)
        result["additionalProperties"] = False
    if schema.get("type") == "array" and isinstance(schema.get("items"), dict):
        result["items"] = _codex_strict_schema(schema["items"])
    return result


def _strip_optional_nulls(value: Any, schema: Dict[str, Any]) -> Any:
    """Restore canonical omission semantics after a strict Codex response."""

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        result: Dict[str, Any] = {}
        for name, child in value.items():
            child_schema = properties.get(name, {})
            if child is None and name in properties and name not in required:
                continue
            result[name] = _strip_optional_nulls(child, child_schema)
        return result
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        return [_strip_optional_nulls(item, schema["items"]) for item in value]
    return value


class ClaudeProvider(SubprocessProvider):
    name = "claude"
    loads_project_instructions = True

    def __init__(self, root: Path, executable: str = "claude") -> None:
        super().__init__(root, executable)

    def build_command(
        self,
        request: ProviderRequest,
        schema_path: Path,
        output_path: Path,
        prompt_path: Path,
    ) -> List[str]:
        del schema_path, output_path, prompt_path
        planning = request.role in {"planner", "reviewer"}
        tools = (
            "Read,Glob,Grep"
            if request.role == "planner"
            else (
                "Read,Glob,Grep,Bash"
                if request.role == "reviewer"
                else "Read,Glob,Grep,Edit,Write,Bash"
            )
        )
        command = [
            self.executable,
            "--print",
            "--output-format",
            "json",
            "--permission-mode",
            "plan" if planning else "acceptEdits",
            "--tools",
            tools,
            "--json-schema",
            json.dumps(request.schema, separators=(",", ":")),
        ]
        if request.model:
            command.extend(["--model", request.model])
        if request.reasoning_effort:
            command.extend(["--effort", request.reasoning_effort])
        self._assert_safe_command(command)
        return command

    def extract_output(self, stdout: str, output_path: Path) -> str:
        del output_path
        return stdout

    def parse_output(self, raw: str) -> Dict[str, Any]:
        try:
            wrapper = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProviderError("provider returned invalid JSON") from exc
        if not isinstance(wrapper, dict):
            raise ProviderError("Claude output wrapper must be a JSON object")
        structured = wrapper.get("structured_output")
        if isinstance(structured, dict):
            return structured
        result = wrapper.get("result")
        if isinstance(result, str):
            try:
                parsed = json.loads(result)
            except json.JSONDecodeError as exc:
                raise ProviderError("Claude result did not contain structured JSON") from exc
            if isinstance(parsed, dict):
                return parsed
        return wrapper


class GrokProvider(SubprocessProvider):
    """Grok Build adapter with bounded continuation for incomplete headless sessions."""

    name = "grok"
    loads_project_instructions = True
    max_turns = 20
    max_resumes = 1

    def __init__(self, root: Path, executable: str = "grok") -> None:
        super().__init__(root, executable)

    def build_command(
        self,
        request: ProviderRequest,
        schema_path: Path,
        output_path: Path,
        prompt_path: Path,
    ) -> List[str]:
        # Grok's JSON-schema mode treats every intermediate reasoning message
        # as a schema response and cancels before tool execution.  The
        # harness therefore enforces the canonical schema after the session,
        # while asking the agent for a final JSON object in the prompt.
        del schema_path, output_path
        return self._command(request, prompt_path)

    def _command(
        self,
        request: ProviderRequest,
        prompt_path: Path,
        *,
        session_id: Optional[str] = None,
    ) -> List[str]:
        command = [self.executable]
        if session_id:
            command.extend(["--resume", session_id])
        command.extend([
            "--prompt-file",
            str(prompt_path),
            "--cwd",
            str(self.request_root(request)),
            "--output-format",
            "json",
            "--permission-mode",
            "acceptEdits" if request.role == "implementer" else "plan",
            # Headless Grok sessions otherwise wait for an interactive
            # permission response; in CI/IDE execution that actor is reaped,
            # yielding a cancelled response before the task can finish.
            "--always-approve",
            # Grok emits an intermediate structured object for each reasoning
            # turn.  Repository tasks need enough turns to load their bounded
            # skill/context, edit, verify, and then produce final evidence.
            "--max-turns",
            str(self.max_turns),
        ])
        if request.model:
            command.extend(["--model", request.model])
        if request.reasoning_effort:
            command.extend(["--reasoning-effort", request.reasoning_effort])
        self._assert_safe_command(command)
        return command

    def invoke(self, request: ProviderRequest) -> Dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="ai-kit-provider-") as directory:
            temp = Path(directory)
            schema_path = temp / "schema.json"
            output_path = temp / "output.json"
            prompt_path = temp / "prompt.md"
            self._reset_metrics()
            schema_path.write_text(json.dumps(request.schema), encoding="utf-8")
            prompt_path.write_text(request.prompt, encoding="utf-8")

            raw = self._run_subprocess(
                request,
                self.build_command(request, schema_path, output_path, prompt_path),
                output_path,
            )
            diagnostics: List[str] = []
            for attempt in range(self.max_resumes + 1):
                terminal = self._terminal_metadata(raw)
                value = self.normalize_output(self.parse_output(raw), request.schema)
                try:
                    validate(value, request.schema)
                    return value
                except SchemaError as exc:
                    detail = self._terminal_diagnostic(terminal, str(exc))
                    diagnostics.append(detail)
                    session_id = terminal.get("session_id") if terminal else None
                    if (
                        attempt >= self.max_resumes
                        or not self._is_incomplete_terminal(terminal)
                        or not session_id
                    ):
                        if self._is_incomplete_terminal(terminal):
                            raise ProviderError(
                                "Grok session incomplete; %s" % "; ".join(diagnostics)
                            ) from exc
                        raise ProviderError(
                            "Grok terminal output did not contain a schema-valid final result; %s"
                            % "; ".join(diagnostics)
                        ) from exc

                    prompt_path.write_text(
                        self._resume_prompt(request.schema), encoding="utf-8"
                    )
                    raw = self._run_subprocess(
                        request,
                        self._command(request, prompt_path, session_id=session_id),
                        output_path,
                    )

        raise ProviderError("Grok provider exhausted without a terminal result")

    def _run_subprocess(
        self,
        request: ProviderRequest,
        command: Sequence[str],
        output_path: Path,
    ) -> str:
        """Preserve Grok's non-envelope turn-limit failure as a typed diagnostic."""

        try:
            return super()._run_subprocess(request, command, output_path)
        except ProviderError as exc:
            message = str(exc)
            if "max turn" in message.lower():
                raise ProviderError(
                    "Grok session incomplete; stop_reason=max_turns session_id=unknown cli=%s"
                    % message
                ) from exc
            raise

    @staticmethod
    def _resume_prompt(schema: Dict[str, Any]) -> str:
        return (
            "Continue the existing bounded task now. Do not repeat context gathering or describe "
            "progress. Finish any remaining tool work, run the required verification, and then return "
            "exactly one final JSON object matching this schema:\n"
            + json.dumps(schema, separators=(",", ":"))
        )

    @staticmethod
    def _terminal_metadata(raw: str) -> Optional[Dict[str, str]]:
        try:
            wrapper = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not isinstance(wrapper, dict):
            return None
        stop_reason = wrapper.get("stopReason", wrapper.get("stop_reason", ""))
        session_id = wrapper.get("sessionId", wrapper.get("session_id", ""))
        return {
            "stop_reason": str(stop_reason).strip().lower(),
            "session_id": str(session_id).strip(),
        }

    @staticmethod
    def _is_incomplete_terminal(terminal: Optional[Dict[str, str]]) -> bool:
        if not terminal:
            return False
        return terminal.get("stop_reason") in {
            "cancelled",
            "max_turns",
            "max_turns_reached",
            "max_turn_requests",
        }

    @staticmethod
    def _terminal_diagnostic(
        terminal: Optional[Dict[str, str]], schema_error: str
    ) -> str:
        if not terminal:
            return "stop_reason=unknown session_id=unknown schema=%s" % schema_error
        return "stop_reason=%s session_id=%s schema=%s" % (
            terminal.get("stop_reason") or "unknown",
            terminal.get("session_id") or "unknown",
            schema_error,
        )

    def stdin_input(self, request: ProviderRequest) -> Optional[str]:
        del request
        return None

    def extract_output(self, stdout: str, output_path: Path) -> str:
        del output_path
        return stdout

    def parse_output(self, raw: str) -> Dict[str, Any]:
        value = super().parse_output(raw)
        # Grok Build currently emits camelCase envelope keys (`structuredOutput`
        # and `text`) while older builds used the snake_case/result keys. Accept
        # both wire formats and normalize them before schema validation.
        for key in ("structured_output", "structuredOutput"):
            structured = value.get(key)
            if isinstance(structured, dict):
                return structured
        for key in ("result", "text"):
            result = value.get(key)
            if isinstance(result, str):
                try:
                    parsed = json.loads(result)
                except json.JSONDecodeError:
                    # Some Grok Build releases stream several complete JSON
                    # objects into the `text` field (one per reasoning turn).
                    # Decode all adjacent objects and keep the final one,
                    # which is the only object that represents the completed
                    # task rather than an intermediate progress update.
                    decoder = json.JSONDecoder()
                    parsed = None
                    parsed_length = 0
                    # The final response can contain a short progress
                    # sentence before the JSON object. Scan each opening
                    # brace and retain the largest complete object. Retaining
                    # the last object would select a nested `evidence` or
                    # `memory` item from an otherwise valid final result.
                    for index, character in enumerate(result):
                        if character != "{":
                            continue
                        try:
                            candidate, end = decoder.raw_decode(result[index:])
                        except json.JSONDecodeError:
                            continue
                        if isinstance(candidate, dict) and end > parsed_length:
                            parsed = candidate
                            parsed_length = end
                    if parsed is None:
                        continue
                if isinstance(parsed, dict):
                    return parsed
        return value
