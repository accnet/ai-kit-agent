"""Private call metadata; prompt/output text is never persisted here."""
from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
import time

from prompt_evidence import EvidenceError
from verification import reporter


class CallMetrics:
    def __init__(self, root, feature, role, task=None):
        self.root, self.path = Path(root).resolve(), None
        self.started = time.perf_counter()
        self.data = {"schema_version": 1, "feature": feature, "role": role, "task": task,
                     "provider_calls": 0, "status": "prepared", "phases_ms": {},
                     "provider_subprocess_calls": None, "provider_resume_calls": None,
                     "provider_stdout_bytes": None, "provider_stderr_bytes": None,
                     "tool_output_bytes": None, "llm_usage": None, "quota": None, "cache_hits": None}

    @contextmanager
    def phase(self, name):
        start = time.perf_counter()
        try:
            yield
        finally:
            self.data["phases_ms"][name] = round(self.data["phases_ms"].get(name, 0) +
                                                  (time.perf_counter() - start) * 1000, 3)

    def request(self, request):
        self.data.update(role=request.role, prompt_chars=len(request.prompt),
                         prompt_bytes=len(request.prompt.encode("utf-8")),
                         schema_bytes=len(json.dumps(request.schema, ensure_ascii=False,
                                                     separators=(",", ":")).encode("utf-8")))

    def provider(self, provider):
        self.data["provider"] = provider.name
        observed = getattr(provider, "last_invocation_metrics", None) or {}
        if not isinstance(observed, dict):
            observed = {}
        for target, source in (("provider_subprocess_calls", "subprocess_calls"),
                               ("provider_resume_calls", "resume_calls"),
                               ("provider_stdout_bytes", "stdout_bytes"),
                               ("provider_stderr_bytes", "stderr_bytes")):
            value = observed.get(source)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                self.data[target] = value

    def write(self):
        try:
            self.data["elapsed_ms"] = round((time.perf_counter() - self.started) * 1000, 3)
            for name in (".workspace", ".workspace/qa"):
                directory = self.root / name
                if directory.is_symlink():
                    raise EvidenceError("metrics directory cannot traverse a symlink")
                directory.mkdir(mode=0o700, exist_ok=True)
            if self.path is None:
                directory = Path(tempfile.mkdtemp(prefix="call-", dir=str(self.root / ".workspace/qa")))
                self.path = directory / "metrics.json"
            if self.path.is_symlink() or self.path.parent.is_symlink():
                raise EvidenceError("metrics path cannot traverse a symlink")
            reporter.write_private_json(self.path, self.data)
        except OSError as exc:
            raise EvidenceError("cannot persist call metrics") from exc
