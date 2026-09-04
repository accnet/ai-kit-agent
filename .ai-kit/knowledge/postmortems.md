# Postmortems

What went wrong and what it taught us — so the same mistake isn't paid for twice. Newest first.

Format:
```
## <YYYY-MM-DD> <what broke>
- Impact: <what happened, one line>
- Root cause: <the real cause, not the symptom>
- Lesson: <the rule that prevents recurrence>
- Enforced by: <gate/checklist/convention updated, or "not yet">
```

Rules: blameless — describe systems, not culprits. Every postmortem must end in a change: a gate, a checklist item, a convention entry, or an explicit "accepted risk". A lesson without enforcement is a wish.

---

## 2026-09-04 CRLF working-tree files flagged as "trailing whitespace" under git-bash
- Impact: `git-qa.sh check worktree` (and `doctor.sh --full`) failed with `git diff --check` reporting "trailing whitespace" on every line of `harness/engine.py` and `harness/models.py`, even though a byte-level check showed zero trailing spaces.
- Root cause: `core.autocrlf=true` with no `.gitattributes`; the two files (edited on Windows) had CRLF in the working tree while the index held LF. PowerShell's `git` normalized the diff, but the git-bash `git` binary (this machine has multiple git binaries — same class as the 2026-09-03 bash/python3 entry) did not apply autocrlf to `git diff --check`, so the `\r` surfaced as trailing whitespace.
- Lesson: Validate whitespace gates (`git diff --check`, `git-qa.sh check worktree`) with the same git binary the repo hooks/CI run (bash/git-bash), not PowerShell's `git`; and keep working-tree line endings LF to match the index under `core.autocrlf=true`.
- Enforced by: `harness/engine.py` + `harness/models.py` normalized to LF; convention noted here, not yet a gate.

## 2026-09-03 Subprocess tests against bash scripts failed on Windows dev machine
- Impact: A new mechanics-test file's subprocess calls to a bash script intermittently failed (`No such file or directory` from a mangled path; a `UnicodeDecodeError`/`None` stdout on `text=True` capture) depending on which process launched them.
- Root cause: This dev machine has multiple `bash`/`python3` binaries reachable as the bare name (Windows Store stub, WSL, Git-Bash/MSYS); which one `subprocess.run(["bash", ...])` resolves depends on the calling process's own PATH, and an absolute Windows path string (backslashes) passed as an argv element is misparsed by a POSIX bash. Default `text=True` decoding also uses the console's codepage, not UTF-8, and can raise on non-ASCII script output.
- Lesson: When a Python test shells out to a repo script, pass a relative, forward-slash path with `cwd=` set (never an absolute Windows path string as an argv element), and pass `encoding="utf-8", errors="replace"` explicitly instead of relying on `text=True`'s default decoding.
- Enforced by: `.ai-kit/tests/test_project_knowledge.py`'s `run_bootstrap`/`run_context_pack` helpers; convention not yet generalized beyond this file — apply the same pattern in any future subprocess-based AI-Kit test.
