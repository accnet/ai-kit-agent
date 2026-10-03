#!/usr/bin/env python3
"""Read-only structured task scopes and live-verified knowledge."""
from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath
import re
import sys

from knowledge_retrieval import render_knowledge, retrieve_knowledge
from task_state import TASK_ID, TaskStateError, resolve


def safe_scope(root, relative):
    relative = relative.replace("\\", "/")
    if not relative or ":" in relative or PurePosixPath(relative).is_absolute() or ".." in PurePosixPath(relative).parts:
        raise ValueError("scope must stay within the repository")
    cursor = root
    for part in PurePosixPath(relative).parts:
        if any(char in part for char in "*?["):
            break
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError("scope cannot traverse a symlink")
    if not cursor.resolve().is_relative_to(root):
        raise ValueError("scope escapes repository")


def build_pack(root, feature, task_id):
    root = Path(root).resolve()
    if not TASK_ID.fullmatch(task_id):
        raise ValueError("invalid task ID")
    relative = ".project/%s/tasks.md" % feature
    safe_scope(root, relative)
    safe_scope(root, ".project/%s/state.json" % feature)
    task = resolve(root, feature, require_projection=True)["tasks"].get(task_id)
    if task is None:
        raise ValueError("task not found")
    source = (root / relative).read_text(encoding="utf-8").splitlines()
    start = next(index for index, line in enumerate(source) if re.match(r"^- \[[ xX]\]\s*" + task_id + r"\s", line))
    lines = ["=== TASK ===", source[start]]
    for line in source[start + 1:]:
        if not line.startswith("  "):
            break
        lines.append(line)
    lines.extend(["", "=== PLAN HEADER ==="])
    lines.extend(line for line in source[:15] if line.startswith(("Intent:", "Goal:", "Out of scope:", "Open questions:")))
    lines.extend(["", "=== BRIEF ==="])
    brief = "features/%s/brief.md" % feature
    safe_scope(root, brief)
    lines.append((root / brief).read_text(encoding="utf-8") if (root / brief).is_file() else
                 "(no brief; requirements supplied through the user conversation)")
    lines.extend(["", "=== FILES IN SCOPE ==="])
    shown = set()
    for pattern in task["files"]:
        safe_scope(root, pattern)
        matches = sorted(root.glob(pattern.replace("\\", "/")))
        if not matches:
            lines.append("--- %s (not created yet) ---" % pattern)
        for match in matches:
            relative = match.relative_to(root).as_posix()
            safe_scope(root, relative)
            if relative in shown:
                continue
            shown.add(relative)
            if match.is_dir():
                lines.append("--- %s/ (directory listing) ---" % relative)
                lines.extend(sorted(child.name for child in match.iterdir())[:40])
            elif match.is_file():
                content = match.read_text(encoding="utf-8", errors="replace").splitlines()
                lines.append("--- %s (%d lines) ---" % (relative, len(content)))
                lines.extend(content if len(content) <= 200 else content[:120])
                if len(content) > 200:
                    lines.append("... (truncated at 120/%d; read the rest on demand)" % len(content))
    if not task["files"]:
        lines.append("(no files scope)")
    lines.extend(["", "=== KNOWLEDGE HITS ===", render_knowledge(retrieve_knowledge(root, feature + " " + task["title"])),
                  "", "=== NEXT ===", "This is tier 1 (never cut). Load modules per .ai-kit/modules/INDEX.md; read adjacent source on demand."])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("feature")
    parser.add_argument("task")
    args = parser.parse_args()
    try:
        print(build_pack(Path.cwd(), args.feature, args.task), end="")
    except (OSError, ValueError, TaskStateError) as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
