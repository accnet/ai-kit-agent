#!/usr/bin/env bash
# Static integrity validation for the AI-Kit distribution.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
fail=0

error() { echo "VALIDATE FAIL: $*" >&2; fail=1; }

required=(
  AGENTS.md CLAUDE.md .gitignore
  .ai/ai.yaml .ai/config.json .ai/models.yaml .ai/rules.yaml .ai/modules/INDEX.md
  .project/INDEX.md .githooks/pre-commit .github/workflows/gates.yml
  .ai/scripts/check-gates.sh .ai/scripts/sync-skills.sh
  .ai/scripts/validate-kit.sh .ai/scripts/doctor.sh .ai/scripts/harness.sh .ai/scripts/git-qa.sh
  .ai/harness/cli.py .ai/harness/config.json .ai/tests/run.sh .ai/tests/test_harness.py
)
for path in "${required[@]}"; do [ -e "$path" ] || error "missing $path"; done

if [ -f CLAUDE.md ] && [ "$(tr -d '\r\n' < CLAUDE.md)" != '@AGENTS.md' ]; then
  error "CLAUDE.md must contain only @AGENTS.md"
fi

module_count=0
while IFS= read -r -d '' module; do
  module_count=$((module_count+1))
  [ "$(sed -n '1p' "$module")" = '---' ] || { error "$module missing opening frontmatter"; continue; }
  [ "$(sed -n '4p' "$module")" = '---' ] || error "$module frontmatter must close on line 4"
  sed -n '2p' "$module" | grep -qE '^name: [a-z0-9-]+$' || error "$module has invalid name"
  sed -n '3p' "$module" | grep -qE '^description: .+' || error "$module has invalid description"
done < <(find .ai/modules -type f -name '*.md' ! -name INDEX.md -print0)
[ "$module_count" -eq 23 ] || error "expected 23 routed modules, found $module_count"

skill_count=0
expected_skills=(
  ai-kit-assess-architecture
  ai-kit-design-contract
  ai-kit-implement
  ai-kit-migrate-data
  ai-kit-plan
  ai-kit-review
  ai-kit-status
  ai-kit-validate-quality
)
while IFS= read -r -d '' skill; do
  skill_count=$((skill_count+1))
  [ "$(sed -n '1p' "$skill")" = '---' ] || error "$skill missing opening frontmatter"
  sed -n '2p' "$skill" | grep -qE '^name: ai-kit-[a-z0-9-]+$' || error "$skill has invalid name"
  sed -n '3p' "$skill" | grep -qE '^description: .+' || error "$skill has invalid description"
  [ "$(sed -n '4p' "$skill")" = '---' ] || error "$skill frontmatter must close on line 4"
done < <(find .ai/skills -mindepth 2 -maxdepth 2 -type f -name SKILL.md -print0)
[ "$skill_count" -eq "${#expected_skills[@]}" ] || error "expected ${#expected_skills[@]} canonical skills, found $skill_count"
for skill_name in "${expected_skills[@]}"; do
  [ -f ".ai/skills/$skill_name/SKILL.md" ] || error "missing canonical skill: $skill_name"
done

.ai/scripts/sync-skills.sh --check || fail=1

while IFS= read -r -d '' file; do
  if ! LC_ALL=C tr -d '\000' < "$file" | cmp -s - "$file"; then
    error "NUL byte found in $file"
  fi
done < <(find AGENTS.md CLAUDE.md .gitignore .ai .agents .claude .githooks .github .project -type f ! -path '*/__pycache__/*' ! -name '*.pyc' -print0)

while IFS= read -r -d '' script; do
  bash -n "$script" || error "invalid shell syntax: $script"
  [ -x "$script" ] || error "script is not executable: $script"
done < <(find .ai/scripts .ai/tests .githooks -type f \( -name '*.sh' -o -name 'pre-commit' \) -print0 2>/dev/null)

deprecated_hits="$(grep -RInE --exclude='validate-kit.sh' 'Attempt 4|Review → QA|\.codex/prompts/' AGENTS.md .ai .claude 2>/dev/null || true)"
[ -z "$deprecated_hits" ] || error "deprecated or contradictory workflow text remains: $(printf '%s' "$deprecated_hits" | tr '\n' ';')"

grep -q '^routing_mode: harness$' .ai/models.yaml || error "models.yaml must enable explicit harness routing"
grep -qE '^test_command: .+$' .ai/ai.yaml || error "ai.yaml missing test_command"
grep -qE '^git_qa_command: .+$' .ai/ai.yaml || error "ai.yaml missing git_qa_command"

if ! PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile .ai/harness/*.py .ai/tests/test_harness.py; then
  error "harness Python syntax validation failed"
fi
if ! python3 -c 'import json; json.load(open(".ai/harness/config.json", encoding="utf-8"))'; then
  error "invalid harness config JSON"
fi
if ! python3 -c 'import json; c=json.load(open(".ai/config.json", encoding="utf-8")); r=c.get("review"); e=c.get("execution"); x=e.get("codex_cli") if isinstance(e, dict) else None; q=c.get("quality"); p=q.get("providers") if isinstance(q, dict) else None; qa=q.get("qa") if isinstance(q, dict) else None; rv=q.get("review") if isinstance(q, dict) else None; assert c.get("schema_version") == 1 and isinstance(r, dict) and r.get("required") is True and isinstance(r.get("independent_enabled"), bool) and isinstance(x, dict) and isinstance(x.get("enabled"), bool) and isinstance(x.get("model"), str) and x.get("model").strip() and isinstance(p, dict) and p.get("codex-cli") == {"provider":"codex","model":"gpt-5.6-sol"} and p.get("claude-cli") == {"provider":"claude","model":"claude-sonnet-5"} and isinstance(qa, dict) and isinstance(qa.get("enabled"), bool) and qa.get("provider") in p and isinstance(rv, dict) and isinstance(rv.get("enabled"), bool) and rv.get("provider") in p'; then
  error "invalid AI-Kit config: require valid review, execution, and QA/Review CLI routing policies"
fi

if [ "$fail" -ne 0 ]; then exit 1; fi
echo "AI-Kit validation OK: 23 modules, 8 canonical skills, synchronized projections, harness runtime"
