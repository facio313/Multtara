#!/usr/bin/env bash
# Multtara — Pilgrimage-style agent worktrees
# Usage: ./scripts/setup-worktrees.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

git fetch origin

mkdir -p worktrees

for b in cursor codex anthropic; do
  if git worktree list --porcelain | grep -q "worktrees/$b"; then
    echo "remove existing worktree: worktrees/$b"
    git worktree remove --force "worktrees/$b" || true
    rm -rf "worktrees/$b"
  fi
  if ! git show-ref --verify --quiet "refs/heads/$b"; then
    git branch "$b" "origin/$b" 2>/dev/null || git branch "$b" origin/main
  else
    git branch -f "$b" "origin/$b" 2>/dev/null || git branch -f "$b" origin/main
  fi
  git worktree add "worktrees/$b" "$b"
  git -C "worktrees/$b" branch --set-upstream-to="origin/$b" "$b" 2>/dev/null || true
  echo "ready: worktrees/$b ($b)"
done

if ! git show-ref --verify --quiet refs/heads/dev; then
  git branch dev origin/dev 2>/dev/null || git branch dev origin/main
fi

echo
git worktree list
echo
git branch -vv
