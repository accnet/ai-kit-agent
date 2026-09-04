"""Durable, provenance-aware memory and deterministic bounded retrieval."""

from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from models import MEMORY_KINDS, utc_now
from store import RepositoryStore, StoreError


TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_.-]*", re.IGNORECASE)
PINNED_SOURCES = (
    "AGENTS.md",
    "features/{feature}/brief.md",
    ".project/{feature}/architecture.md",
    ".project/{feature}/decisions.md",
    ".ai-kit/knowledge/conventions.md",
)


class MemoryError(RuntimeError):
    """Raised for invalid memory records or retrieval requests."""


def _hash_bytes(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _tokens(value: str) -> Set[str]:
    return {token.lower() for token in TOKEN_RE.findall(value)}


class MemoryStore:
    def __init__(self, store: RepositoryStore) -> None:
        self.store = store

    def add(
        self,
        feature: str,
        kind: str,
        content: str,
        *,
        source: Optional[str] = None,
        tags: Optional[Iterable[str]] = None,
        task: Optional[str] = None,
        importance: int = 1,
        actor: str = "user",
    ) -> Dict[str, Any]:
        kind = str(kind).strip().lower()
        if kind not in MEMORY_KINDS:
            raise MemoryError("memory kind must be working, episodic, or semantic")
        content = str(content).strip()
        if not content:
            raise MemoryError("memory content cannot be empty")
        if len(content) > 50_000:
            raise MemoryError("memory content exceeds 50000 characters")
        if importance not in {1, 2, 3, 4, 5}:
            raise MemoryError("memory importance must be between 1 and 5")

        provenance = self._provenance(source, content)
        record: Dict[str, Any] = {
            "id": "M-" + uuid.uuid4().hex[:16],
            "ts": utc_now(),
            "kind": kind,
            "content": content,
            "tags": sorted({_tag for _tag in (str(tag).strip() for tag in (tags or [])) if _tag}),
            "importance": importance,
            "actor": str(actor),
            "provenance": provenance,
        }
        if task:
            record["task"] = str(task)
        self.store.append_record(feature, "memory.jsonl", record)
        return record

    def retrieve(
        self,
        feature: str,
        query: str,
        *,
        kinds: Optional[Sequence[str]] = None,
        max_chars: int = 12_000,
        limit: int = 20,
        include_project_sources: bool = True,
        include_project_instructions: bool = True,
    ) -> Dict[str, Any]:
        if max_chars < 256 or max_chars > 200_000:
            raise MemoryError("context budget must be between 256 and 200000 characters")
        if limit < 1 or limit > 100:
            raise MemoryError("memory limit must be between 1 and 100")
        selected_kinds = set(kinds or MEMORY_KINDS)
        if not selected_kinds.issubset(MEMORY_KINDS):
            raise MemoryError("unknown memory kind in retrieval filter")

        query_tokens = _tokens(query)
        candidates: List[Tuple[int, int, Dict[str, Any]]] = []
        records = self.store.read_records(feature, "memory.jsonl")
        for index, record in enumerate(records):
            if record.get("kind") not in selected_kinds:
                continue
            content = str(record.get("content", ""))
            searchable = content + " " + " ".join(record.get("tags", []))
            overlap = len(query_tokens & _tokens(searchable))
            importance = int(record.get("importance", 1))
            kind_bonus = {"working": 3, "episodic": 2, "semantic": 1}.get(record.get("kind"), 0)
            score = overlap * 100 + importance * 10 + kind_bonus
            if not query_tokens:
                score += index
            enriched = dict(record)
            enriched["score"] = score
            enriched["stale"] = self._is_stale(record.get("provenance", {}))
            candidates.append((score, index, enriched))

        candidates.sort(key=lambda item: (-item[0], -item[1], str(item[2].get("id", ""))))
        entries: List[Dict[str, Any]] = []
        used = 0
        deferred_sources: List[Dict[str, Any]] = []
        excluded_sources: List[str] = []

        if include_project_sources:
            source_budget = max(128, int(max_chars * 0.55))
            for template in PINNED_SOURCES:
                relative = template.format(feature=feature)
                if relative == "AGENTS.md" and not include_project_instructions:
                    excluded_sources.append(relative)
                    continue
                entry = self._file_entry(relative)
                if entry is None:
                    continue
                content_size = len(str(entry.get("content", "")))
                if content_size <= source_budget - used:
                    entries.append(entry)
                    used += content_size
                else:
                    deferred_sources.append(entry)

        if used < max_chars:
            for _, _, record in candidates[:limit]:
                used = self._bounded_add(entries, record, used, max_chars)
                if used >= max_chars:
                    break

        if used < max_chars:
            for entry in deferred_sources:
                used = self._bounded_add(entries, entry, used, max_chars)
                if used >= max_chars:
                    break

        truncated_sources = [
            str(entry.get("provenance", {}).get("ref", "unknown"))
            for entry in entries
            if entry.get("truncated")
        ]
        return {
            "query": str(query),
            "budget_chars": max_chars,
            "used_chars": used,
            "entries": entries,
            "excluded_sources": excluded_sources,
            "truncated_sources": truncated_sources,
        }

    def render_context(self, result: Dict[str, Any]) -> str:
        blocks: List[str] = []
        for entry in result.get("entries", []):
            provenance = entry.get("provenance", {})
            header = "[%s | %s | stale=%s]" % (
                entry.get("kind", "source"),
                provenance.get("ref", "unknown"),
                str(bool(entry.get("stale", False))).lower(),
            )
            blocks.append(header + "\n" + str(entry.get("content", "")))
        return "\n\n".join(blocks)

    def _provenance(self, source: Optional[str], content: str) -> Dict[str, str]:
        if source is None:
            return {"type": "manual", "ref": "conversation", "hash": _hash_bytes(content.encode("utf-8"))}
        relative = Path(str(source))
        if relative.is_absolute() or ".." in relative.parts:
            raise MemoryError("memory source must be a repository-relative path")
        path = self.store._inside(self.store.root / relative)
        if not path.is_file():
            raise MemoryError("memory source file does not exist: %s" % relative)
        return {
            "type": "file",
            "ref": relative.as_posix(),
            "hash": _hash_bytes(path.read_bytes()),
        }

    def _is_stale(self, provenance: Dict[str, Any]) -> bool:
        if provenance.get("type") != "file":
            return False
        relative = Path(str(provenance.get("ref", "")))
        if relative.is_absolute() or ".." in relative.parts:
            return True
        try:
            path = self.store._inside(self.store.root / relative)
        except StoreError:
            return True
        if not path.is_file():
            return True
        return _hash_bytes(path.read_bytes()) != provenance.get("hash")

    def _file_entry(self, relative: str) -> Optional[Dict[str, Any]]:
        path = self.store._inside(self.store.root / relative)
        if not path.is_file():
            return None
        content = path.read_text(encoding="utf-8", errors="replace")
        return {
            "id": "source:" + relative,
            "kind": "source",
            "content": content,
            "importance": 5,
            "score": 10_000,
            "stale": False,
            "provenance": {
                "type": "file",
                "ref": relative,
                "hash": _hash_bytes(path.read_bytes()),
            },
        }

    @staticmethod
    def _bounded_add(
        entries: List[Dict[str, Any]], entry: Dict[str, Any], used: int, max_chars: int
    ) -> int:
        remaining = max_chars - used
        if remaining <= 0:
            return used
        content = str(entry.get("content", ""))
        if not content:
            return used
        selected = dict(entry)
        if len(content) > remaining:
            if remaining < 80:
                return used
            selected["content"] = content[: remaining - 20].rstrip() + "\n[context truncated]"
            selected["truncated"] = True
        entries.append(selected)
        return used + len(str(selected["content"]))
