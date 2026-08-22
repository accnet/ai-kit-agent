"""Fail-closed detached Git worktrees and review-before-promotion patches."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


MAX_GIT_OUTPUT = 20_000_000
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")


class WorkspaceError(RuntimeError):
    """Raised when an isolated-worktree invariant does not hold."""


@dataclass(frozen=True)
class WorkspaceRecord:
    repository: str
    workspace: str
    feature: str
    task: str
    run_id: str
    base_commit: str
    allowed_dirty_paths: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        value["allowed_dirty_paths"] = list(self.allowed_dirty_paths)
        return value

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "WorkspaceRecord":
        try:
            return cls(
                repository=str(value["repository"]),
                workspace=str(value["workspace"]),
                feature=str(value["feature"]),
                task=str(value["task"]),
                run_id=str(value["run_id"]),
                base_commit=str(value["base_commit"]),
                allowed_dirty_paths=tuple(value.get("allowed_dirty_paths", [])),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise WorkspaceError("invalid workspace record") from exc


@dataclass(frozen=True)
class PatchArtifact:
    content: bytes
    digest: str
    changed_files: Tuple[str, ...]


class GitWorkspaceManager:
    """Own detached task worktrees without staging or committing the main tree."""

    def __init__(self, root: Path, *, git_executable: str = "git") -> None:
        candidate = Path(root)
        if candidate.is_symlink():
            raise WorkspaceError("repository root cannot be a symlink")
        self.root = candidate.resolve()
        if not (self.root / "AGENTS.md").is_file() or not (self.root / ".ai").is_dir():
            raise WorkspaceError("repository root must contain AGENTS.md and .ai/")
        self.git_executable = str(git_executable)
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", self.root.name).strip("-.") or "repo"
        self.workspace_parent = self.root.parent / (".%s-ai-kit-worktrees" % safe_name)
        self.owner_directory = self.workspace_parent / ".owners"

    def create(
        self,
        feature: str,
        task: str,
        *,
        allowed_dirty_paths: Iterable[str] = (),
    ) -> WorkspaceRecord:
        """Create one detached worktree at the current stable main HEAD."""

        self._validate_identifier(feature, "feature")
        self._validate_identifier(task, "task")
        allowed = tuple(sorted(set(self._normalize_relative(value) for value in allowed_dirty_paths)))
        self._validate_repository()
        base_commit = self._text(self._git(self.root, ["rev-parse", "--verify", "HEAD"])).strip()
        if not re.fullmatch(r"[0-9a-fA-F]{40,64}", base_commit):
            raise WorkspaceError("repository HEAD is missing or invalid; create a baseline commit first")
        dirty = self.main_changed_paths()
        unexpected = self._outside_allowed(dirty, allowed)
        if unexpected:
            raise WorkspaceError("main worktree is dirty outside control paths: %s" % ", ".join(unexpected))
        self._prepare_parent()
        run_id = uuid.uuid4().hex
        workspace = self.workspace_parent / ("%s-%s-%s" % (feature, task, run_id[:12]))
        if workspace.exists() or workspace.is_symlink():
            raise WorkspaceError("refusing to reuse an existing workspace path")
        record = WorkspaceRecord(
            repository=str(self.root),
            workspace=str(workspace),
            feature=feature,
            task=task,
            run_id=run_id,
            base_commit=base_commit,
            allowed_dirty_paths=allowed,
        )
        try:
            self._git(
                self.root,
                ["worktree", "add", "--detach", str(workspace), base_commit],
            )
            self._write_marker(record)
            self.validate_owned(record)
        except Exception:
            if workspace.exists() and not workspace.is_symlink():
                try:
                    self._git(self.root, ["worktree", "remove", "--force", str(workspace)])
                except WorkspaceError:
                    pass
            raise
        return record

    def capture_patch(self, record: WorkspaceRecord) -> PatchArtifact:
        """Stage only the disposable index and export a deterministic binary patch."""

        workspace = self.validate_owned(record)
        self._git(workspace, ["add", "-A", "--", "."])
        content = self._git(
            workspace,
            ["diff", "--cached", "--binary", "--full-index", "--no-ext-diff", "HEAD", "--"],
        )
        names = self._git(
            workspace,
            ["diff", "--cached", "--name-only", "-z", "--diff-filter=ACDMRTUXB", "HEAD", "--"],
        )
        changed = tuple(sorted(self._nul_paths(names)))
        return PatchArtifact(
            content=content,
            digest="sha256:" + hashlib.sha256(content).hexdigest(),
            changed_files=changed,
        )

    def promote(self, record: WorkspaceRecord, expected_digest: str) -> PatchArtifact:
        """Apply the exact reviewed patch to an unchanged main tree without staging."""

        self.validate_owned(record)
        artifact = self.capture_patch(record)
        if artifact.digest != expected_digest:
            raise WorkspaceError("workspace patch changed after review")
        self._validate_repository()
        current_head = self._text(
            self._git(self.root, ["rev-parse", "--verify", "HEAD"])
        ).strip()
        if current_head != record.base_commit:
            raise WorkspaceError("main HEAD changed since workspace creation")
        dirty = self.main_changed_paths()
        unexpected = self._outside_allowed(dirty, record.allowed_dirty_paths)
        if unexpected:
            raise WorkspaceError("main worktree changed before promotion: %s" % ", ".join(unexpected))
        before_index = self._git(self.root, ["diff", "--cached", "--binary", "--", "."])
        self._git(self.root, ["apply", "--check", "--binary", "-"], input_bytes=artifact.content)
        self._git(self.root, ["apply", "--binary", "-"], input_bytes=artifact.content)
        after_index = self._git(self.root, ["diff", "--cached", "--binary", "--", "."])
        if after_index != before_index:
            raise WorkspaceError("promotion unexpectedly changed the main index")
        return artifact

    def cleanup(self, record: WorkspaceRecord) -> None:
        """Remove only a worktree whose external ownership marker matches exactly."""

        workspace = self.validate_owned(record, require_base=False)
        self._git(self.root, ["worktree", "remove", "--force", str(workspace)])
        marker = self.marker_path(record)
        try:
            marker.unlink()
        except FileNotFoundError as exc:
            raise WorkspaceError("workspace ownership marker disappeared during cleanup") from exc
        self._git(self.root, ["worktree", "prune"])

    def validate_owned(
        self, record: WorkspaceRecord, *, require_base: bool = True
    ) -> Path:
        if self.workspace_parent.is_symlink():
            raise WorkspaceError("workspace parent cannot be a symlink")
        if self.owner_directory.is_symlink():
            raise WorkspaceError("workspace owner directory cannot be a symlink")
        if Path(record.repository).resolve() != self.root:
            raise WorkspaceError("workspace record belongs to a different repository")
        self._validate_identifier(record.feature, "feature")
        self._validate_identifier(record.task, "task")
        if not re.fullmatch(r"[0-9a-f]{32}", record.run_id):
            raise WorkspaceError("workspace record has an invalid run id")
        workspace = Path(record.workspace)
        if workspace.is_symlink():
            raise WorkspaceError("workspace path cannot be a symlink")
        try:
            workspace.resolve().relative_to(self.workspace_parent.resolve())
        except ValueError as exc:
            raise WorkspaceError("workspace path escapes the owned parent") from exc
        expected_name = "%s-%s-%s" % (record.feature, record.task, record.run_id[:12])
        if workspace.name != expected_name or workspace.parent != self.workspace_parent:
            raise WorkspaceError("workspace path does not match its ownership record")
        if not workspace.is_dir():
            raise WorkspaceError("owned workspace is missing")
        marker = self.marker_path(record)
        try:
            stored = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WorkspaceError("workspace ownership marker is missing or invalid") from exc
        if stored != record.to_dict():
            raise WorkspaceError("workspace ownership marker does not match")
        top = Path(self._text(self._git(workspace, ["rev-parse", "--show-toplevel"])).strip()).resolve()
        if top != workspace.resolve():
            raise WorkspaceError("owned workspace Git root mismatch")
        head = self._text(self._git(workspace, ["rev-parse", "--verify", "HEAD"])).strip()
        if require_base and head != record.base_commit:
            raise WorkspaceError("owned workspace base commit changed")
        return workspace.resolve()

    def marker_path(self, record: WorkspaceRecord) -> Path:
        return self.owner_directory / (record.run_id + ".json")

    def main_changed_paths(self) -> Tuple[str, ...]:
        changed: List[str] = []
        for arguments in (
            ["diff", "--name-only", "-z", "--", "."],
            ["diff", "--cached", "--name-only", "-z", "--", "."],
            ["ls-files", "--others", "--exclude-standard", "-z", "--", "."],
        ):
            changed.extend(self._nul_paths(self._git(self.root, arguments)))
        return tuple(sorted(set(changed)))

    def _validate_repository(self) -> None:
        top = Path(
            self._text(self._git(self.root, ["rev-parse", "--show-toplevel"])).strip()
        ).resolve()
        if top != self.root:
            raise WorkspaceError("Git top-level does not match the AI-Kit root")

    def _prepare_parent(self) -> None:
        if self.workspace_parent.is_symlink():
            raise WorkspaceError("workspace parent cannot be a symlink")
        try:
            self.workspace_parent.mkdir(mode=0o700, parents=False, exist_ok=True)
        except OSError as exc:
            raise WorkspaceError("cannot prepare workspace parent directory") from exc
        if self.workspace_parent.resolve().parent != self.root.parent.resolve():
            raise WorkspaceError("workspace parent is not the deterministic repository sibling")
        if self.owner_directory.is_symlink():
            raise WorkspaceError("workspace owner directory cannot be a symlink")
        try:
            self.owner_directory.mkdir(mode=0o700, exist_ok=True)
        except OSError as exc:
            raise WorkspaceError("cannot prepare workspace owner directory") from exc

    def _write_marker(self, record: WorkspaceRecord) -> None:
        marker = self.marker_path(record)
        fd, temporary_name = tempfile.mkstemp(
            dir=str(self.owner_directory), prefix=".owner-", suffix=".tmp"
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(record.to_dict(), handle, sort_keys=True, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(str(temporary), str(marker))
        except OSError as exc:
            raise WorkspaceError("cannot persist workspace ownership marker") from exc
        finally:
            if temporary.exists():
                temporary.unlink()

    def _git(
        self,
        cwd: Path,
        arguments: Sequence[str],
        *,
        input_bytes: Optional[bytes] = None,
    ) -> bytes:
        command = [self.git_executable, "-C", str(Path(cwd))] + list(arguments)
        try:
            result = subprocess.run(
                command,
                input=input_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                check=False,
                timeout=120,
            )
        except FileNotFoundError as exc:
            raise WorkspaceError("Git executable is unavailable") from exc
        except subprocess.TimeoutExpired as exc:
            raise WorkspaceError("Git workspace operation timed out") from exc
        if len(result.stdout) > MAX_GIT_OUTPUT or len(result.stderr) > MAX_GIT_OUTPUT:
            raise WorkspaceError("Git workspace output exceeds the safety limit")
        if result.returncode != 0:
            detail = self._text(result.stderr).strip()[-2000:]
            if arguments[:3] == ["rev-parse", "--verify", "HEAD"]:
                raise WorkspaceError("repository HEAD is missing; create a baseline commit first")
            raise WorkspaceError(
                "Git workspace command failed (%s): %s"
                % (" ".join(arguments[:3]), detail or "no error output")
            )
        return result.stdout

    @staticmethod
    def _text(value: bytes) -> str:
        return value.decode("utf-8", errors="replace")

    @staticmethod
    def _nul_paths(value: bytes) -> List[str]:
        return [
            item.decode("utf-8", errors="surrogateescape")
            for item in value.split(b"\0")
            if item
        ]

    @staticmethod
    def _normalize_relative(value: str) -> str:
        raw = str(value).strip().replace("\\", "/").strip("/")
        parts = Path(raw).parts
        if not raw or Path(raw).is_absolute() or ".." in parts:
            raise WorkspaceError("allowed dirty path must be repository-relative")
        return raw

    @staticmethod
    def _outside_allowed(paths: Iterable[str], allowed: Sequence[str]) -> List[str]:
        return sorted(
            path
            for path in paths
            if not any(path == prefix or path.startswith(prefix.rstrip("/") + "/") for prefix in allowed)
        )

    @staticmethod
    def _validate_identifier(value: str, label: str) -> None:
        if not IDENTIFIER.fullmatch(str(value)):
            raise WorkspaceError("%s is not a safe workspace identifier" % label)
