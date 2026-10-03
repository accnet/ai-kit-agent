"""Shared read-only knowledge retrieval with live section verification."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path, PurePosixPath
import re

_spec = importlib.util.spec_from_file_location("_retrieval_projector", Path(__file__).with_name("knowledge-projector.py"))
projector = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(projector)


def tokens(value):
    return set(re.findall(r"[a-z0-9]{4,}", value.lower()))


def _safe_source(root, relative):
    if (not isinstance(relative, str) or "\\" in relative or ":" in relative or
            PurePosixPath(relative).is_absolute() or ".." in PurePosixPath(relative).parts or
            not projector.path_in_declared_scope(relative)):
        return None
    cursor = root
    for part in PurePosixPath(relative).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            return None
    return cursor if cursor.resolve().is_relative_to(root) else None


def _scan(root, relative, read_cache):
    path = _safe_source(root, relative)
    if path is None or not path.is_file():
        return []
    try:
        if relative not in read_cache:
            read_cache[relative] = path.read_bytes()
    except OSError:
        return []
    if relative.startswith(".contracts/"):
        return projector.scan_contract_file(root, path, raw=read_cache[relative])
    kind = "ai-knowledge" if relative.startswith(".ai-kit/") else (
        "architecture" if relative.endswith("/architecture.md") else "project-decisions")
    return projector.scan_markdown_file(root, kind, path, raw=read_cache[relative])


def _valid_item(item):
    return (isinstance(item, dict) and all(isinstance(item.get(key), str) for key in
            ("id", "topic", "summary", "source_path", "source_hash", "status")) and
            isinstance(item.get("keywords"), list) and all(isinstance(word, str) for word in item["keywords"]) and
            isinstance(item.get("precedence"), int) and not isinstance(item.get("precedence"), bool) and
            item.get("status") in {"approved", "stale", "superseded", "rejected"} and
            re.fullmatch(r"[a-f0-9]{64}", item.get("source_hash", "")) is not None and
            projector.path_in_declared_scope(item.get("source_path", "")))


def retrieve_knowledge(root, query, *, limit=5, read_cache=None):
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("knowledge limit must be between 1 and 100")
    root, keywords = Path(root).resolve(), tokens(query)
    read_cache = {} if read_cache is None else read_cache
    cache, pointers, candidates = {}, {}, []

    def live(relative):
        if relative not in cache:
            cache[relative] = {item["id"]: item for item in _scan(root, relative, read_cache)}
        return cache[relative]

    mode = "index"
    try:
        path = root / ".knowledge-index/index.json"
        if path.is_symlink() or path.parent.is_symlink():
            raise ValueError("unsafe index")
        index = json.loads(path.read_text(encoding="utf-8"))
        items = index.get("items")
        if (index.get("schema_version") != 1 or index.get("disabled") or index.get("enabled") is False or
                not isinstance(items, list) or not items or not all(_valid_item(item) for item in items)):
            raise ValueError("invalid or disabled index")
    except (OSError, ValueError, TypeError, AttributeError):
        mode, items = "fallback", []
        for name in ("decisions.md", "conventions.md", "postmortems.md"):
            items.extend(live(".ai-kit/knowledge/" + name).values())
    for item in items:
        score = len(keywords & set(item["keywords"]))
        if not score or item["status"] not in {"approved", "stale"} or item.get("superseded_by"):
            continue
        relative = item["source_path"]
        if _safe_source(root, relative) is None:
            continue
        actual = live(relative).get(item["id"])
        if (item["status"] != "approved" or not actual or actual["source_hash"] != item["source_hash"] or
                not item["summary"] or actual["summary"][:len(item["summary"])] != item["summary"]):
            pointers[relative] = {"source_path": relative, "reason": "stale or unverifiable"}
            continue
        candidates.append(dict(actual, summary=item["summary"], score=score,
                               matched_keywords=sorted(keywords & set(item["keywords"]))))
    candidates.sort(key=lambda item: (-item["score"], item["precedence"], item["id"]))
    groups = {}
    for item in candidates:
        groups.setdefault(projector.slugify(item["topic"]), []).append(item)
    for item in candidates:
        item["conflict"] = len({entry["summary"] for entry in groups[projector.slugify(item["topic"])]}) > 1
    return {"mode": mode, "entries": candidates[:limit],
            "pointers": [pointers[key] for key in sorted(pointers)][:limit],
            "omitted": max(0, len(candidates) - limit)}


def render_knowledge(result):
    lines = []
    for item in result["entries"]:
        marker = "CONFLICT: " if item["conflict"] else ""
        if result["mode"] == "fallback":
            words = item["matched_keywords"]
            lines.append("--- matches for '%s' (%s) ---" % (words[0] if words else "knowledge", item["source_path"]))
        else:
            lines.append("--- %s%s (source: %s, status: approved) ---" % (marker, item["topic"], item["source_path"]))
        lines.append(item["summary"])
    for item in result["pointers"]:
        lines.append("--- stale: see %s directly (%s) ---" % (item["source_path"], item["reason"]))
    if result["omitted"]:
        lines.append("... (%d more relevant item(s) not shown)" % result["omitted"])
    return "\n".join(lines) or "(no relevant verified knowledge)"
