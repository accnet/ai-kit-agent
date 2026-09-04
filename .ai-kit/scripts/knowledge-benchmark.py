#!/usr/bin/env python3
"""knowledge-benchmark.py — repeatable baseline-vs-index-first benchmark.

Compares context-pack.sh's KNOWLEDGE HITS output with .knowledge-index/
present (index-first, top-K) against the same command with .knowledge-index/
temporarily hidden (baseline: live grep over .ai-kit/knowledge/), over a fixed,
deterministically-derived set of existing tasks in this repository.

Reports measured baseline/optimized/median/range values. Never prints a
fixed percentage claim — see .project/project-knowledge-index/benchmark.md
for the recorded run this script produced.
"""
from __future__ import annotations

import json
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTEXT_PACK = ".ai-kit/scripts/context-pack.sh"
PROJECTOR = ROOT / ".ai-kit/scripts/knowledge-projector.py"
KIDX = ROOT / ".knowledge-index"

MAX_TASKS = 8


def fixed_task_set() -> list[tuple[str, str]]:
    """Deterministic: first task id of each feature's tasks.md, sorted by feature name."""
    tasks: list[tuple[str, str]] = []
    for tasks_md in sorted(ROOT.glob(".project/*/tasks.md")):
        feature = tasks_md.parent.name
        text = tasks_md.read_text(encoding="utf-8")
        m = re.search(r"^- \[.\] (T\w+)\s", text, re.MULTILINE)
        if m:
            tasks.append((feature, m.group(1)))
    return tasks[:MAX_TASKS]


def run_pack(feature: str, task_id: str) -> tuple[str, float]:
    start = time.perf_counter()
    result = subprocess.run(
        ["bash", CONTEXT_PACK, feature, task_id],
        cwd=str(ROOT), capture_output=True, check=False,
        encoding="utf-8", errors="replace",
    )
    elapsed = time.perf_counter() - start
    m = re.search(r"=== KNOWLEDGE HITS ===\n(.*?)\n=== NEXT ===", result.stdout, re.DOTALL)
    section = m.group(1) if m else ""
    return section, elapsed


def summarize(values: list[float]) -> dict:
    return {
        "min": round(min(values), 4),
        "median": round(statistics.median(values), 4),
        "max": round(max(values), 4),
    }


def main() -> int:
    tasks = fixed_task_set()
    if not tasks:
        print("no fixed tasks found; nothing to benchmark", file=sys.stderr)
        return 1

    # --- one-time initial-bootstrap cost -------------------------------------
    bootstrap_start = time.perf_counter()
    subprocess.run(
        [sys.executable, str(PROJECTOR), "--root", str(ROOT), "--check"],
        capture_output=True, check=False, encoding="utf-8", errors="replace",
    )
    bootstrap_elapsed = time.perf_counter() - bootstrap_start
    index_bytes = len(KIDX.joinpath("index.json").read_bytes()) if KIDX.joinpath("index.json").is_file() else 0

    # --- per-task baseline (index hidden) vs optimized (index present) ------
    per_task = []
    had_index = KIDX.is_dir()
    hidden = KIDX.with_name(".knowledge-index.benchmark-hidden")
    try:
        for feature, task_id in tasks:
            optimized_text, optimized_time = run_pack(feature, task_id)
            if had_index:
                KIDX.rename(hidden)
            baseline_text, baseline_time = run_pack(feature, task_id)
            if had_index:
                hidden.rename(KIDX)
            per_task.append({
                "feature": feature, "task": task_id,
                "baseline_chars": len(baseline_text), "optimized_chars": len(optimized_text),
                "baseline_seconds": round(baseline_time, 4), "optimized_seconds": round(optimized_time, 4),
            })
    finally:
        if hidden.is_dir() and not KIDX.is_dir():
            hidden.rename(KIDX)

    baseline_sizes = [t["baseline_chars"] for t in per_task]
    optimized_sizes = [t["optimized_chars"] for t in per_task]
    baseline_times = [t["baseline_seconds"] for t in per_task]
    optimized_times = [t["optimized_seconds"] for t in per_task]
    reductions = [
        round((b - o) / b, 4) if b > 0 else None
        for b, o in zip(baseline_sizes, optimized_sizes)
    ]
    reductions = [r for r in reductions if r is not None]

    report = {
        "task_count": len(per_task),
        "initial_bootstrap": {
            "check_seconds": round(bootstrap_elapsed, 4),
            "index_json_bytes": index_bytes,
        },
        "retrieval_size_chars": {
            "baseline": summarize(baseline_sizes) if baseline_sizes else None,
            "optimized": summarize(optimized_sizes) if optimized_sizes else None,
        },
        "elapsed_seconds": {
            "baseline": summarize(baseline_times) if baseline_times else None,
            "optimized": summarize(optimized_times) if optimized_times else None,
        },
        "size_reduction_ratio": summarize(reductions) if reductions else None,
        "per_task": per_task,
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
