"""Safe filesystem persistence for canonical state and append-only history."""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from models import SCHEMA_VERSION, utc_now, validate_state


FEATURE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


class StoreError(RuntimeError):
    """Raised when durable state cannot be read or written safely."""


class LockError(StoreError):
    """Raised when another harness process owns the feature transition lock."""


def validate_feature(feature: str) -> str:
    value = str(feature).strip()
    if not FEATURE_RE.fullmatch(value) or value in {".", ".."}:
        raise StoreError(
            "invalid feature id; use 1-64 lowercase letters, digits, '.', '_' or '-'"
        )
    return value


def default_root() -> Path:
    return Path(__file__).resolve().parents[2]


class RepositoryStore:
    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = Path(root or default_root()).resolve()
        if not (self.root / "AGENTS.md").is_file() or not (self.root / ".ai").is_dir():
            raise StoreError("repository root must contain AGENTS.md and .ai/")

    def _inside(self, path: Path) -> Path:
        resolved = path.resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise StoreError("path escapes repository root: %s" % resolved) from exc
        return resolved

    def feature_dir(self, feature: str) -> Path:
        return self._inside(self.root / ".project" / validate_feature(feature))

    def intent_dir(self, feature: str) -> Path:
        return self._inside(self.root / "features" / validate_feature(feature))

    def state_path(self, feature: str) -> Path:
        return self.feature_dir(feature) / "state.json"

    def load_state(self, feature: str) -> Dict[str, Any]:
        path = self.state_path(feature)
        if not path.is_file():
            raise StoreError("state not found: %s" % path.relative_to(self.root))
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StoreError("invalid state file: %s" % path.relative_to(self.root)) from exc
        try:
            validate_state(state)
        except ValueError as exc:
            raise StoreError("invalid canonical state: %s" % exc) from exc
        if state.get("feature") != validate_feature(feature):
            raise StoreError("state feature does not match requested feature")
        return state

    def write_json_atomic(self, path: Path, value: Any) -> None:
        path = self._inside(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = None
        temporary = None
        try:
            handle = tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=str(path.parent),
                prefix=".%s." % path.name,
                suffix=".tmp",
                delete=False,
            )
            temporary = Path(handle.name)
            json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            handle.close()
            handle = None
            os.replace(str(temporary), str(path))
            self._fsync_dir(path.parent)
        except (OSError, TypeError, ValueError) as exc:
            raise StoreError("failed atomic write: %s" % path.relative_to(self.root)) from exc
        finally:
            if handle is not None:
                handle.close()
            if temporary is not None and temporary.exists():
                temporary.unlink()

    def write_text_atomic(self, path: Path, content: str) -> None:
        path = self._inside(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            dir=str(path.parent), prefix=".%s." % path.name, suffix=".tmp"
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(str(temporary), str(path))
            self._fsync_dir(path.parent)
        except OSError as exc:
            raise StoreError("failed atomic write: %s" % path.relative_to(self.root)) from exc
        finally:
            if temporary.exists():
                temporary.unlink()

    def save_state(self, feature: str, state: Dict[str, Any]) -> None:
        if state.get("feature") != validate_feature(feature):
            raise StoreError("refusing to save state under a different feature")
        if state.get("schema_version") != SCHEMA_VERSION:
            raise StoreError("refusing to save unsupported state schema")
        try:
            validate_state(state)
        except ValueError as exc:
            raise StoreError("refusing to save invalid canonical state: %s" % exc) from exc
        self.write_json_atomic(self.state_path(feature), state)

    def append_record(self, feature: str, filename: str, record: Dict[str, Any]) -> None:
        if filename not in {"events.jsonl", "memory.jsonl"}:
            raise StoreError("unsupported append-only record file")
        path = self._inside(self.feature_dir(feature) / filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            encoded = json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            with path.open("a", encoding="utf-8") as handle:
                handle.write(encoded + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        except (OSError, TypeError, ValueError) as exc:
            raise StoreError("failed to append %s" % path.relative_to(self.root)) from exc

    def append_event(
        self,
        feature: str,
        event: str,
        actor: str,
        *,
        task: Optional[str] = None,
        detail: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        sequence: Optional[int] = None,
    ) -> Dict[str, Any]:
        record: Dict[str, Any] = {
            "ts": utc_now(),
            "event": str(event),
            "feature": validate_feature(feature),
            "actor": str(actor),
        }
        if task:
            record["task"] = str(task)
        if detail:
            record["detail"] = str(detail)
        if data:
            record["data"] = data
        if sequence is not None:
            record["sequence"] = int(sequence)
        self.append_record(feature, "events.jsonl", record)
        return record

    def read_records(self, feature: str, filename: str) -> List[Dict[str, Any]]:
        if filename not in {"events.jsonl", "memory.jsonl"}:
            raise StoreError("unsupported append-only record file")
        path = self.feature_dir(feature) / filename
        if not path.exists():
            return []
        records: List[Dict[str, Any]] = []
        number = 0
        try:
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("record is not an object")
                records.append(value)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise StoreError("invalid %s record at line %d" % (filename, number)) from exc
        return records

    @contextmanager
    def lock(self, feature: str) -> Iterator[None]:
        feature = validate_feature(feature)
        lock_dir = self._inside(self.root / ".workspace" / "harness")
        lock_dir.mkdir(parents=True, exist_ok=True)
        path = self._inside(lock_dir / (feature + ".lock"))
        fd = None
        for _ in range(2):
            try:
                fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                break
            except FileExistsError as exc:
                status = self.lock_status(feature)
                if not status["stale"]:
                    raise LockError("feature is locked by pid=%s" % status.get("pid", "unknown")) from exc
                try:
                    observed = path.stat()
                    current = path.stat()
                except FileNotFoundError:
                    continue
                if (
                    observed.st_dev != current.st_dev
                    or observed.st_ino != current.st_ino
                    or observed.st_mtime_ns != current.st_mtime_ns
                ):
                    continue
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
        if fd is None:
            raise LockError("could not recover stale feature lock")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"pid": os.getpid(), "created_at": utc_now()}, handle)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            yield
        finally:
            try:
                path.unlink()
            except FileNotFoundError:
                pass

    def lock_status(self, feature: str) -> Dict[str, Any]:
        path = self._inside(self.root / ".workspace" / "harness" / (validate_feature(feature) + ".lock"))
        if not path.exists():
            return {"locked": False, "stale": False, "pid": None, "age_seconds": 0}
        try:
            age = max(0.0, time.time() - path.stat().st_mtime)
            record = json.loads(path.read_text(encoding="utf-8"))
            pid = int(record.get("pid", 0))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pid = 0
            age = max(0.0, time.time() - path.stat().st_mtime) if path.exists() else 0.0
        alive = self._pid_alive(pid)
        # Do not reap a just-created, not-yet-populated lock file.
        stale = (pid > 0 and not alive) or (pid <= 0 and age > 30.0)
        return {
            "locked": True,
            "stale": stale,
            "pid": pid or None,
            "alive": alive,
            "age_seconds": round(age, 3),
        }

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False
        return True

    @staticmethod
    def _fsync_dir(path: Path) -> None:
        try:
            fd = os.open(str(path), os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError:
            # Some filesystems (notably Windows mounts) do not support dir fsync.
            pass
