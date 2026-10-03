#!/usr/bin/env bash
# Static integrity validation for the AI-Kit distribution.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
fail=0

error() { echo "VALIDATE FAIL: $*" >&2; fail=1; }

required=(
  AGENTS.md CLAUDE.md .gitignore
  .ai-kit/ai.yaml .ai-kit/config.json .ai-kit/models.yaml .ai-kit/rules.yaml .ai-kit/modules/INDEX.md
  .project/INDEX.md .githooks/pre-commit .github/workflows/gates.yml
  .ai-kit/scripts/check-gates.sh .ai-kit/scripts/sync-skills.sh
  .ai-kit/scripts/validate-kit.sh .ai-kit/scripts/doctor.sh .ai-kit/scripts/harness.sh .ai-kit/scripts/git-qa.sh
  .ai-kit/harness/cli.py .ai-kit/harness/config.json .ai-kit/tests/run.sh .ai-kit/tests/test_harness.py .ai-kit/tests/test_install.sh
  .ai-kit/tests/manifest.json .ai-kit/tests/test_manifest.py .ai-kit/scripts/consistency.py .ai-kit/tests/test_ai_kit_consistency.py
  .ai-kit/qa-profiles.json .ai-kit/scripts/qa_profiles.py
  .ai-kit/scripts/context_pack.py .ai-kit/scripts/knowledge_retrieval.py .ai-kit/scripts/knowledge-projector.py
  .ai-kit/harness/call_metrics.py
  .ai-kit/modules/testing/stacks.md .ai-kit/modules/testing/javascript.md
  .ai-kit/modules/testing/node.md .ai-kit/modules/testing/next.md .ai-kit/modules/testing/express.md
  .ai-kit/install/install.sh .ai-kit/install/manifest.txt .ai-kit/install/README.md
  .ai-kit/install/templates/AGENTS.md .ai-kit/install/templates/CLAUDE.md
  .ai-kit/install/templates/pre-commit .ai-kit/install/templates/gates.yml
  .ai-kit/install/templates/project-index.md .ai-kit/install/templates/gitignore.entries
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
done < <(find .ai-kit/modules -type f -name '*.md' ! -name INDEX.md -print0)
[ "$module_count" -eq 30 ] || error "expected 30 routed modules/references, found $module_count"

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
done < <(find .ai-kit/skills -mindepth 2 -maxdepth 2 -type f -name SKILL.md -print0)
[ "$skill_count" -eq "${#expected_skills[@]}" ] || error "expected ${#expected_skills[@]} canonical skills, found $skill_count"
for skill_name in "${expected_skills[@]}"; do
  [ -f ".ai-kit/skills/$skill_name/SKILL.md" ] || error "missing canonical skill: $skill_name"
done

.ai-kit/scripts/sync-skills.sh --check || fail=1

cmp -s AGENTS.md .ai-kit/install/templates/AGENTS.md || error "installer AGENTS.md template drift"
cmp -s CLAUDE.md .ai-kit/install/templates/CLAUDE.md || error "installer CLAUDE.md template drift"
cmp -s .githooks/pre-commit .ai-kit/install/templates/pre-commit || error "installer pre-commit template drift"
cmp -s .github/workflows/gates.yml .ai-kit/install/templates/gates.yml || error "installer gates workflow template drift"

manifest_count=0
install_destinations=$'\n'
while IFS='|' read -r source destination mode kind; do
  case "$source" in ''|\#*) continue ;; esac
  manifest_count=$((manifest_count+1))
  [ -f ".ai-kit/install/templates/$source" ] || error "installer manifest source missing: $source"
  case "$destination" in ''|/*|*..*) error "unsafe installer destination: $destination" ;; esac
  case "$mode" in 0644|0755) ;; *) error "invalid installer mode for $destination: $mode" ;; esac
  case "${kind:-managed}" in managed|seed) ;; *) error "invalid installer kind for $destination: $kind" ;; esac
  case "$install_destinations" in
    *$'\n'"$destination"$'\n'*) error "duplicate installer destination: $destination" ;;
    *) install_destinations="${install_destinations}${destination}"$'\n' ;;
  esac
done < .ai-kit/install/manifest.txt
[ "$manifest_count" -eq 5 ] || error "expected 5 installer manifest entries, found $manifest_count"

while IFS= read -r -d '' file; do
  if ! LC_ALL=C tr -d '\000' < "$file" | cmp -s - "$file"; then
    error "NUL byte found in $file"
  fi
done < <(find AGENTS.md CLAUDE.md .gitignore .ai-kit .agents .claude .githooks .github .project -type f ! -path '*/__pycache__/*' ! -name '*.pyc' -print0)

while IFS= read -r -d '' script; do
  bash -n "$script" || error "invalid shell syntax: $script"
  [ -x "$script" ] || error "script is not executable: $script"
done < <(find .ai-kit/scripts .ai-kit/tests .ai-kit/install .githooks -type f \( -name '*.sh' -o -name 'pre-commit' \) -print0 2>/dev/null)

deprecated_hits="$(grep -RInE --exclude='validate-kit.sh' 'Attempt 4|Review → QA|\.codex/prompts/' AGENTS.md .ai-kit .claude 2>/dev/null || true)"
[ -z "$deprecated_hits" ] || error "deprecated or contradictory workflow text remains: $(printf '%s' "$deprecated_hits" | tr '\n' ';')"

grep -q '^routing_mode: harness$' .ai-kit/models.yaml || error "models.yaml must enable explicit harness routing"
grep -qE '^test_command: .+$' .ai-kit/ai.yaml || error "ai.yaml missing test_command"
grep -qE '^git_qa_command: .+$' .ai-kit/ai.yaml || error "ai.yaml missing git_qa_command"

if ! python3 - .ai-kit/harness/*.py .ai-kit/tests/test_harness.py <<'PY'
import pathlib
import sys

for source in sys.argv[1:]:
    path = pathlib.Path(source)
    compile(path.read_bytes(), str(path), "exec")
PY
then
  error "harness Python syntax validation failed"
fi
if ! python3 - .ai-kit/scripts/dag.py .ai-kit/scripts/consistency.py .ai-kit/scripts/qa_profiles.py .ai-kit/tests/test_manifest.py .ai-kit/tests/test_ai_kit_consistency.py .ai-kit/tests/test_ai_kit_cross_feature.py .ai-kit/tests/test_qa_profiles.py <<'PY'
import pathlib
import sys

for source in sys.argv[1:]:
    path = pathlib.Path(source)
    compile(path.read_bytes(), str(path), "exec")
PY
then
  error "AI-Kit consistency/manifest Python syntax validation failed"
fi
if ! python3 .ai-kit/scripts/qa_profiles.py >/dev/null; then
  error "AI-Kit QA profile validation failed"
fi
if ! python3 -c 'import json; json.load(open(".ai-kit/harness/config.json", encoding="utf-8"))'; then
  error "invalid harness config JSON"
fi
if ! python3 -c 'import json; c=json.load(open(".ai-kit/config.json", encoding="utf-8")); r=c.get("review"); e=c.get("execution"); x=e.get("task_cli") if isinstance(e, dict) else None; q=c.get("quality"); p=q.get("providers") if isinstance(q, dict) else None; qa=q.get("qa") if isinstance(q, dict) else None; rv=q.get("review") if isinstance(q, dict) else None; assert c.get("schema_version") == 1 and isinstance(r, dict) and r.get("required") is True and isinstance(r.get("independent_enabled"), bool) and isinstance(x, dict) and isinstance(x.get("enabled"), bool) and x.get("provider") == "grok" and x.get("model") is None and isinstance(p, dict) and p.get("codex-cli") == {"provider":"codex","model":"gpt-5.6-sol"} and p.get("claude-cli") == {"provider":"claude","model":"claude-sonnet-5"} and isinstance(qa, dict) and isinstance(qa.get("enabled"), bool) and qa.get("provider") in p and isinstance(rv, dict) and isinstance(rv.get("enabled"), bool) and rv.get("provider") in p'; then
  error "invalid AI-Kit config: require valid review, execution, and QA/Review CLI routing policies"
fi

if ! python3 .ai-kit/scripts/consistency.py >/dev/null; then
  error "AI-Kit session/worker-policy consistency check failed"
fi

if [ "$fail" -ne 0 ]; then exit 1; fi
echo "AI-Kit validation OK: 30 modules/references, 8 canonical skills, synchronized projections, harness runtime"
