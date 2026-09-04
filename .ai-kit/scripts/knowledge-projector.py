#!/usr/bin/env python3
"""knowledge-projector.py — deterministic .knowledge-index/ projector.

Contract: .project/project-knowledge-index/architecture.md
Policy:   .knowledge-index/README.md

Reads canonical sources (.project/<feature>/decisions.md, .ai-kit/knowledge/*,
.contracts/*.schema.json, approved .project/<feature>/architecture.md) and
emits a deterministic, hash-verified .knowledge-index/index.json plus a
bounded .knowledge-index/project-map.md. Never modifies a source file. Never
calls a model or the network. Never evaluates content found in a source.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

SCHEMA_VERSION = 1
GENERATOR_VERSION = "1.0.0"
SUMMARY_CHARS_DEFAULT = 400

# --- canonical source kinds, in architecture.md precedence order ------------

PRECEDENCE = {
    "project-decisions": 1,
    "ai-knowledge": 2,
    "contract": 3,
    "architecture": 4,
}

# --- secret / credential shaped patterns: a match rejects the whole item ----

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)aws_secret_access_key\s*[:=]\s*\S+"),
    re.compile(r"(?i)\b(api[_-]?key|secret|token|password|passwd)\b\s*[:=]\s*['\"]?[A-Za-z0-9/_+.\-]{12,}"),
    re.compile(r"[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{20,}"),  # JWT-shaped
    re.compile(r"://[^/\s:@]+:[^/\s@]+@"),  # user:pass@ embedded in a URL
]


def contains_secret(text: str) -> bool:
    return any(p.search(text) for p in SECRET_PATTERNS)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")
    return slug or "whole"


def keywords_from(*texts: str) -> list[str]:
    words: list[str] = []
    seen: set[str] = set()
    for text in texts:
        for token in re.findall(r"[a-z0-9]{4,}", text.lower()):
            if token not in seen:
                seen.add(token)
                words.append(token)
    return words[:12]


# --- markdown section splitting ---------------------------------------------

HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$", re.MULTILINE)


def split_markdown_sections(text: str) -> list[tuple[str, str]]:
    """Split into (heading_text, section_text) pairs, section_text includes its heading."""
    matches = list(HEADING_RE.finditer(text))
    if not matches:
        return [("whole", text)] if text.strip() else []
    sections: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        heading = m.group(2)
        sections.append((heading, text[start:end]))
    return sections


def dedupe_anchor(anchor: str, used: set[str]) -> str:
    if anchor not in used:
        used.add(anchor)
        return anchor
    n = 2
    while f"{anchor}-{n}" in used:
        n += 1
    used.add(f"{anchor}-{n}")
    return f"{anchor}-{n}"


# --- item construction --------------------------------------------------------

def make_item(kind: str, source_path: str, anchor: str, heading: str, body: bytes,
              summary_chars: int = SUMMARY_CHARS_DEFAULT) -> dict | None:
    text = body.decode("utf-8", errors="replace")
    if contains_secret(text):
        # rejected: excluded entirely, never partially redacted; logged (not
        # the content itself) so a rejection is visible without leaking it
        print(f"KNOWLEDGE-PROJECTOR reject (secret pattern): {kind}:{source_path}#{anchor}", file=sys.stderr)
        return None
    summary = re.sub(r"\s+", " ", text).strip()[:summary_chars]
    if not summary:
        return None  # malformed/empty section: nothing to summarize
    return {
        "id": f"{kind}:{source_path}#{anchor}",
        "topic": heading[:120],
        "summary": summary,
        "source_path": source_path,
        "source_hash": sha256_hex(body),
        "status": "approved",
        "superseded_by": None,
        "precedence": PRECEDENCE[kind],
        "keywords": keywords_from(heading, summary),
        "budget": {"summary_chars": len(summary), "source_bytes": len(body)},
    }


def scan_markdown_file(root: Path, kind: str, path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []  # unreadable/malformed source: not emitted as an active item
    rel = path.relative_to(root).as_posix()
    items: list[dict] = []
    used: set[str] = set()
    for heading, section in split_markdown_sections(text):
        anchor = dedupe_anchor(slugify(heading), used)
        item = make_item(kind, rel, anchor, heading, section.encode("utf-8"))
        if item is not None:
            items.append(item)
    return items


def scan_contract_file(root: Path, path: Path) -> list[dict]:
    try:
        raw = path.read_bytes()
        data = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []  # malformed source: not emitted as an active item
    rel = path.relative_to(root).as_posix()
    title = str(data.get("title") or path.stem)
    description = str(data.get("description") or "")
    text_for_scan = f"{title}\n{description}"
    if contains_secret(text_for_scan):
        print(f"KNOWLEDGE-PROJECTOR reject (secret pattern): contract:{rel}#whole", file=sys.stderr)
        return []
    summary = re.sub(r"\s+", " ", description).strip()[:SUMMARY_CHARS_DEFAULT] or title
    return [{
        "id": f"contract:{rel}#whole",
        "topic": title[:120],
        "summary": summary,
        "source_path": rel,
        "source_hash": sha256_hex(raw),
        "status": "approved",
        "superseded_by": None,
        "precedence": PRECEDENCE["contract"],
        "keywords": keywords_from(title, path.stem),
        "budget": {"summary_chars": len(summary), "source_bytes": len(raw)},
    }]


def declared_source_files(root: Path) -> dict[str, tuple[str, Path]]:
    """Map every in-scope source path -> (kind, absolute path)."""
    sources: dict[str, tuple[str, Path]] = {}
    for p in sorted(root.glob(".project/*/decisions.md")):
        sources[p.relative_to(root).as_posix()] = ("project-decisions", p)
    for name in ("decisions.md", "conventions.md", "postmortems.md"):
        p = root / ".ai-kit/knowledge" / name
        if p.is_file():
            sources[p.relative_to(root).as_posix()] = ("ai-knowledge", p)
    for p in sorted((root / ".contracts").glob("*.schema.json")) if (root / ".contracts").is_dir() else []:
        sources[p.relative_to(root).as_posix()] = ("contract", p)
    for p in sorted(root.glob(".project/*/architecture.md")):
        sources[p.relative_to(root).as_posix()] = ("architecture", p)
    return sources


def scan_all(root: Path) -> list[dict]:
    items: list[dict] = []
    for rel, (kind, path) in declared_source_files(root).items():
        if kind == "contract":
            items.extend(scan_contract_file(root, path))
        else:
            items.extend(scan_markdown_file(root, kind, path))
    items.sort(key=lambda it: (it["precedence"], it["id"]))
    return items


# Scope is defined by pattern membership, not current file existence, so a
# deleted or renamed source is "missing" (-> stale, retained) rather than
# "out-of-scope" (-> dropped). Mirrors declared_source_files()'s patterns.
_SCOPE_PATTERNS = [
    re.compile(r"^\.project/[^/]+/decisions\.md$"),
    re.compile(r"^\.contracts/[^/]+\.schema\.json$"),
    re.compile(r"^\.project/[^/]+/architecture\.md$"),
]
_SCOPE_EXACT = {".ai-kit/knowledge/decisions.md", ".ai-kit/knowledge/conventions.md", ".ai-kit/knowledge/postmortems.md"}


def path_in_declared_scope(rel: str) -> bool:
    if rel in _SCOPE_EXACT:
        return True
    return any(p.match(rel) for p in _SCOPE_PATTERNS)


# --- refresh: reconcile fresh scan against an existing index.json -----------

def refresh_items(root: Path, existing: list[dict]) -> list[dict]:
    fresh = scan_all(root)
    fresh_by_id = {it["id"]: it for it in fresh}

    result: list[dict] = []
    seen_ids: set[str] = set()

    for old in existing:
        old_id = old.get("id")
        seen_ids.add(old_id)
        if not path_in_declared_scope(old.get("source_path", "")):
            continue  # out-of-scope: drop, never carried forward
        if old_id in fresh_by_id:
            result.append(fresh_by_id[old_id])  # re-approved with current content/hash
        else:
            # source or section missing/malformed: cannot verify -> stale, retained
            stale = dict(old)
            stale["status"] = "stale"
            result.append(stale)

    for it in fresh:
        if it["id"] not in seen_ids:
            result.append(it)  # newly discovered approved item

    result.sort(key=lambda it: (it["precedence"], it["id"]))
    return result


# --- project-map.md: bounded, derived from verified structure ---------------

EXCLUDE_TOP = {".git", "__pycache__", "node_modules", ".workspace"}


def first_readme_line(path: Path) -> str:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return ""
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped[:100]
    return ""


def extract_bash_blocks(readme: Path, limit: int = 8) -> list[str]:
    try:
        text = readme.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    blocks = re.findall(r"```bash\n(.*?)```", text, re.DOTALL)
    lines: list[str] = []
    for block in blocks:
        for line in block.strip().splitlines():
            if line.strip() and line.strip() not in lines:
                lines.append(line.strip())
            if len(lines) >= limit:
                return lines
    return lines


def generate_project_map(root: Path) -> str:
    top_entries = []
    for entry in sorted(root.iterdir()):
        if entry.name in EXCLUDE_TOP or (entry.name.startswith(".") and entry.name not in {
            ".ai-kit", ".agents", ".claude", ".codex", ".contracts", ".githooks", ".github",
            ".project", ".knowledge-index",
        }):
            continue
        purpose = ""
        if entry.is_dir():
            readme = entry / "README.md"
            if readme.is_file():
                purpose = first_readme_line(readme)
        top_entries.append((entry.name, purpose))

    commands = extract_bash_blocks(root / "README.md")

    lines = [
        "# Project Map — generated",
        "",
        "Bounded summary of verified repository structure and README-documented",
        "commands. Regenerated by `.ai-kit/scripts/knowledge-projector.py` — do not",
        "hand-edit. Not a copy of full source files. Canonical sources remain",
        "`.project/`, `.contracts/`, and `.ai-kit/knowledge/`.",
        "",
        "## Top-level entries",
        "",
        "| Path | Note |",
        "|---|---|",
    ]
    for name, purpose in top_entries:
        lines.append(f"| `{name}` | {purpose} |")

    if commands:
        lines += ["", "## Commands (from README.md)", "", "```bash"]
        lines += commands
        lines.append("```")

    return "\n".join(lines) + "\n"


# --- atomic write, no partial writes -----------------------------------------

def atomic_write(path: Path, content: str) -> None:
    # write_bytes (not write_text) avoids Windows text-mode CRLF translation
    # and the Python 3.10+-only write_text(newline=...) parameter.
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(content.encode("utf-8"))
    os.replace(tmp, path)


def write_index(kdir: Path, items: list[dict]) -> None:
    from datetime import datetime, timezone
    envelope = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generator_version": GENERATOR_VERSION,
        "items": items,
    }
    atomic_write(kdir / "index.json", json.dumps(envelope, indent=2, ensure_ascii=False) + "\n")


# --- modes ---------------------------------------------------------------------

def load_existing_index(kdir: Path) -> dict:
    path = kdir / "index.json"
    if not path.is_file():
        return {"schema_version": SCHEMA_VERSION, "items": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema_version": SCHEMA_VERSION, "items": []}


def cmd_initial(root: Path, kdir: Path) -> int:
    items = scan_all(root)
    write_index(kdir, items)
    atomic_write(kdir / "project-map.md", generate_project_map(root))
    print(f"KNOWLEDGE-PROJECTOR initial: {len(items)} approved item(s)")
    return 0


def cmd_refresh(root: Path, kdir: Path) -> int:
    existing = load_existing_index(kdir)
    if existing.get("schema_version") != SCHEMA_VERSION:
        print("KNOWLEDGE-PROJECTOR FAIL: existing index.json schema_version mismatch; refusing to refresh", file=sys.stderr)
        return 1
    try:
        items = refresh_items(root, existing.get("items", []))
    except Exception as exc:  # conflict/malformed existing state: fail closed, no write
        print(f"KNOWLEDGE-PROJECTOR FAIL: refresh preflight error: {exc}; no files were written", file=sys.stderr)
        return 1
    write_index(kdir, items)
    atomic_write(kdir / "project-map.md", generate_project_map(root))
    stale = sum(1 for it in items if it["status"] == "stale")
    print(f"KNOWLEDGE-PROJECTOR refresh: {len(items)} item(s), {stale} stale")
    return 0


def cmd_check(root: Path, kdir: Path) -> int:
    existing = load_existing_index(kdir)
    fresh = scan_all(root)
    fresh_ids = {it["id"]: it for it in fresh}
    existing_ids = {it["id"]: it for it in existing.get("items", [])}

    drift = 0
    for id_, it in fresh_ids.items():
        old = existing_ids.get(id_)
        if old is None:
            print(f"KNOWLEDGE-PROJECTOR check: new candidate not yet projected: {id_}")
            drift += 1
        elif old.get("source_hash") != it["source_hash"]:
            print(f"KNOWLEDGE-PROJECTOR check: stale (hash changed): {id_}")
            drift += 1
    for id_, old in existing_ids.items():
        if id_ not in fresh_ids and old.get("status") == "approved":
            print(f"KNOWLEDGE-PROJECTOR check: source missing for approved item: {id_}")
            drift += 1

    if drift:
        print(f"KNOWLEDGE-PROJECTOR check: {drift} drift item(s); run --refresh", file=sys.stderr)
        return 1
    print("KNOWLEDGE-PROJECTOR check: no drift")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--mode", choices=["initial", "refresh"])
    args = parser.parse_args()

    root = Path(args.root).resolve()
    kdir = root / ".knowledge-index"

    if args.check:
        return cmd_check(root, kdir)
    if args.write and args.mode == "initial":
        kdir.mkdir(parents=True, exist_ok=True)
        return cmd_initial(root, kdir)
    if args.write and args.mode == "refresh":
        return cmd_refresh(root, kdir)

    print("usage: knowledge-projector.py --root <path> (--check | --write --mode initial|refresh)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
