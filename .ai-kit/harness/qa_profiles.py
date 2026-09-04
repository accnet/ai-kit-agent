"""Immutable QA-profile resolution backed by the repository validator."""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import json
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple


class QaProfileError(ValueError):
    pass


@dataclass(frozen=True)
class QaProfile:
    identifier: str
    command: Tuple[str, ...]
    cwd: str
    timeout_seconds: int
    evidence: Tuple[Tuple[str, object], ...]

    def evidence_metadata(self) -> Dict[str, object]:
        return dict(self.evidence)


def _validator():
    path = Path(__file__).resolve().parents[1] / "scripts" / "qa_profiles.py"
    spec = importlib.util.spec_from_file_location("_ai_kit_qa_profile_validator", path)
    if spec is None or spec.loader is None:
        raise QaProfileError("cannot load QA profile validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate


def validate(root: Path, path: Optional[Path] = None):
    """Expose the same validator syntax to harness callers and legacy scripts."""

    return _validator()(Path(root).resolve(), path)


class QaProfileResolver:
    def __init__(self, root: Path, path: Optional[Path] = None) -> None:
        self.root = Path(root).resolve()
        self.path = Path(path or self.root / ".ai-kit/qa-profiles.json")

    def resolve(self, identifiers: Iterable[str]) -> Tuple[QaProfile, ...]:
        values = list(identifiers)
        if len(values) != len(set(values)):
            raise QaProfileError("duplicate verification profile identifier")
        errors = _validator()(self.root, self.path)
        if errors:
            raise QaProfileError("; ".join(errors))
        try:
            profiles = json.loads(self.path.read_text(encoding="utf-8"))["profiles"]
        except (OSError, ValueError, KeyError) as exc:
            raise QaProfileError("cannot read QA profiles: %s" % exc) from exc
        resolved = []
        for identifier in values:
            if not isinstance(identifier, str) or identifier not in profiles:
                raise QaProfileError("unknown verification profile: %s" % identifier)
            profile = profiles[identifier]
            evidence = tuple(
                (key, tuple(value) if isinstance(value, list) else value)
                for key, value in sorted(profile["evidence"].items())
            )
            resolved.append(QaProfile(identifier, tuple(profile["command"]), profile["cwd"], profile["timeout_seconds"], evidence))
        return tuple(resolved)
