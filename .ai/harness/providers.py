"""Safe structured-output adapters for scripted, Codex, and Claude providers."""

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
        return self.build_command(request, Path("/tmp/ai-kit-schema.json"), Path("/tmp/ai-kit-output.json"))

    def request_root(self, request: ProviderRequest) -> Path:
        return request.working_directory or self.root

    def build_command(self, request: ProviderRequest, schema_path: Path, output_path: Path) -> List[str]:
        raise NotImplementedError

    def output_schema(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        return schema

    def normalize_output(
        self, value: Dict[str, Any], schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        del schema
        return value

    def invoke(self, request: ProviderRequest) -> Dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="ai-kit-provider-") as directory:
            temp = Path(directory)
            schema_path = temp / "schema.json"
            output_path = temp / "output.json"
            schema_path.write_text(
                json.dumps(self.output_schema(request.schema)), encoding="utf-8"
            )
            command = self.build_command(request, schema_path, output_path)
            self._assert_safe_command(command)
            try:
                result = subprocess.run(
                    command,
                    input=request.prompt,
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
                raise ProviderError("provider timed out after %d seconds" % request.timeout_seconds) from exc
            if result.returncode != 0:
                detail = result.stderr.strip()[-2000:]
                raise ProviderError("provider exited %d: %s" % (result.returncode, detail or "no error output"))
            raw = self.extract_output(result.stdout, output_path)
            if len(raw) > request.max_output_chars:
                raise ProviderError("provider output exceeds configured limit")
            value = self.normalize_output(self.parse_output(raw), request.schema)
            try:
                validate(value, request.schema)
            except SchemaError as exc:
                raise ProviderError("provider output violates schema: %s" % exc) from exc
            return value

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

    def build_command(self, request: ProviderRequest, schema_path: Path, output_path: Path) -> List[str]:
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

    def build_command(self, request: ProviderRequest, schema_path: Path, output_path: Path) -> List[str]:
        del schema_path, output_path
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
