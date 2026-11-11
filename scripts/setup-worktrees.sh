#!/usr/bin/env bash
set -euo pipefail
if [[ $# -gt 0 ]]; then
  echo 'Usage: scripts/setup-worktrees.sh (prepares dev only; no force/reset mode)' >&2
  exit 2
fi
root="$(cd "$(dirname "$0")/.." && pwd -P)"
git -C "$root" fetch origin main
existing="$(git -C "$root" worktree list --porcelain | awk '/^worktree / {path=substr($0,10)} /^branch refs\/heads\/dev$/ {print path}')"
if [[ -n "$existing" ]]; then
  printf 'Preserved existing dev checkout: %s\n' "$existing"
  exit 0
fi
target="$root/worktrees/dev"
[[ ! -e "$target" && ! -L "$target" ]] || { echo 'Refusing to overwrite existing dev path.' >&2; exit 1; }
if ! git -C "$root" show-ref --verify --quiet refs/heads/dev; then
  if git -C "$root" show-ref --verify --quiet refs/remotes/origin/dev; then
    git -C "$root" branch --track dev origin/dev
  else
    git -C "$root" branch dev origin/main
  fi
fi
git -C "$root" worktree add "$target" dev
printf 'Use dev for local execution: %s\n' "$target"
