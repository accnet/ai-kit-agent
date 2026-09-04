#!/usr/bin/env python3
"""Parity checks for the coordinator protocol projections."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
REQUIRED = (
    "Codex IDE remains the scheduler",
    "Run `.ai-kit/scripts/dag.py <feature> --json`",
    "at most `orchestration.max_workers`",
    "isolated worktree",
    "workers must not edit `tasks.md`",
    "commit,\n   push, or spawn nested workers",
    "Run QA and G3 only after the implementation dependency barrier is complete",
    "never\ncall an LLM API or create native workers",
)


def main():
    root_text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    template_text = (ROOT / ".ai-kit" / "install" / "templates" / "AGENTS.md").read_text(encoding="utf-8")
    failures = [clause for clause in REQUIRED if clause not in root_text or clause not in template_text]
    if root_text.count("## Native parallel orchestration") != 1 or template_text.count("## Native parallel orchestration") != 1:
        failures.append("missing or duplicate orchestration section")
    if failures:
        print("AI-Kit orchestration docs FAILED: " + "; ".join(failures))
        return 1
    print("AI-Kit orchestration docs OK: root/template coordinator protocol parity")
    return 0


if __name__ == "__main__":
    sys.exit(main())
