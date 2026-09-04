#!/usr/bin/env python3
"""Authoritative AI-Kit release references must stay synchronised."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EXPECTED = "0.16.0"
TEXT_REFERENCES = [
    ROOT / ".ai-kit/harness/README.md",
    ROOT / ".ai-kit/modules/contracts.md",
    ROOT / "AGENTS.md",
    ROOT / ".ai-kit/install/templates/AGENTS.md",
]


def main():
    failures = []
    ai_yaml = (ROOT / ".ai-kit/ai.yaml").read_text(encoding="utf-8")
    if "version: " + EXPECTED not in ai_yaml:
        failures.append(".ai-kit/ai.yaml version is not " + EXPECTED)
    if (ROOT / "AGENTS.md").read_bytes() != (ROOT / ".ai-kit/install/templates/AGENTS.md").read_bytes():
        failures.append("root and template AGENTS.md differ")
    for path in TEXT_REFERENCES:
        text = path.read_text(encoding="utf-8")
        if "v0.14" in text or "v0.7" in text:
            failures.append("stale release claim in " + str(path.relative_to(ROOT)))
    if failures:
        raise SystemExit("AI-Kit version checks FAILED: " + "; ".join(failures))
    print("AI-Kit version checks OK: " + EXPECTED)


if __name__ == "__main__":
    main()
