#!/usr/bin/env bash
# Optional Git-backed QA for an AI-Kit checkout.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ACTION="${1:-status}"

usage() {
  echo "usage: $0 status | setup [--init] | check [staged|all|worktree]" >&2
  exit 2
}

git_available() {
  command -v git >/dev/null 2>&1
}

repository_root() {
  git -C "$ROOT" rev-parse --show-toplevel 2>/dev/null || true
}

assert_ai_kit_root() {
  local top
  top="$(repository_root)"
  [ -n "$top" ] || return 1
  if [ "$(cd "$top" && pwd)" != "$ROOT" ]; then
    echo "GIT_QA ERROR: Git root is $top, expected AI-Kit root $ROOT" >&2
    exit 2
  fi
}

hook_state() {
  local hooks
  hooks="$(git -C "$ROOT" config --local --get core.hooksPath 2>/dev/null || true)"
  if [ "$hooks" = ".githooks" ]; then
    printf '%s' enabled
  elif [ -n "$hooks" ]; then
    printf 'other:%s' "$hooks"
  else
    printf '%s' disabled
  fi
}

status_action() {
  if ! git_available; then
    echo "GIT_QA status=skip git=unavailable repository=no hooks=unknown"
    return 0
  fi
  local version top branch changed staged
  version="$(git --version | awk '{print $3}')"
  top="$(repository_root)"
  if [ -z "$top" ]; then
    echo "GIT_QA status=skip git=$version repository=no hooks=disabled"
    return 0
  fi
  assert_ai_kit_root
  branch="$(git -C "$ROOT" symbolic-ref --quiet --short HEAD 2>/dev/null || printf '%s' detached)"
  changed="$(git -C "$ROOT" status --porcelain=v1 --untracked-files=normal | wc -l | tr -d ' ')"
  staged="$(git -C "$ROOT" diff --cached --name-only | wc -l | tr -d ' ')"
  echo "GIT_QA status=ready git=$version repository=yes hooks=$(hook_state) branch=$branch changed=$changed staged=$staged"
}

setup_action() {
  local initialize=false
  case "${1:-}" in
    '') ;;
    --init) initialize=true ;;
    *) usage ;;
  esac
  [ "$#" -le 1 ] || usage
  if ! git_available; then
    echo "GIT_QA ERROR: Git is not installed" >&2
    exit 3
  fi
  if [ -z "$(repository_root)" ]; then
    if [ "$initialize" != true ]; then
      echo "GIT_QA ERROR: $ROOT is not a Git repository; rerun setup --init" >&2
      exit 3
    fi
    git -C "$ROOT" init -q
  fi
  assert_ai_kit_root
  if [ ! -x "$ROOT/.githooks/pre-commit" ]; then
    echo "GIT_QA ERROR: .githooks/pre-commit is missing or not executable" >&2
    exit 2
  fi
  git -C "$ROOT" config --local core.hooksPath .githooks
  echo "GIT_QA setup=complete repository=$ROOT hooks=.githooks scope=local"
}

check_action() {
  local mode="${1:-worktree}"
  [ "$#" -le 1 ] || usage
  case "$mode" in staged|all|worktree) ;; *) usage ;; esac
  if ! git_available; then
    echo "GIT_QA status=skip reason=git-unavailable"
    return 0
  fi
  if [ -z "$(repository_root)" ]; then
    echo "GIT_QA status=skip reason=repository-unavailable"
    return 0
  fi
  assert_ai_kit_root
  if [ "$(hook_state)" != enabled ]; then
    echo "GIT_QA ERROR: local core.hooksPath must be .githooks; run git-qa.sh setup" >&2
    exit 1
  fi
  if git -C "$ROOT" diff --name-only --diff-filter=U | grep -q .; then
    echo "GIT_QA FAIL: unresolved merge conflicts" >&2
    exit 1
  fi
  git -C "$ROOT" diff --check
  git -C "$ROOT" diff --cached --check
  bash "$ROOT/.ai/scripts/check-gates.sh" "$mode"
  echo "GIT_QA OK mode=$mode hooks=.githooks"
}

case "$ACTION" in
  status)
    [ "$#" -eq 1 ] || usage
    status_action
    ;;
  setup)
    shift
    setup_action "$@"
    ;;
  check)
    shift
    check_action "$@"
    ;;
  *) usage ;;
esac
