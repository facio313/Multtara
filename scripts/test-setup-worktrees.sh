#!/usr/bin/env bash
set -euo pipefail
script="$(cd "$(dirname "$0")" && pwd)/setup-worktrees.sh"
fixture=$(mktemp -d)
trap 'rm -rf "$fixture"' EXIT
mkdir -p "$fixture/repo/scripts"
git init -q -b main "$fixture/origin"
git -C "$fixture/origin" -c user.name=Test -c user.email=test@example.invalid commit -qm baseline --allow-empty
git clone -q "$fixture/origin" "$fixture/repo-clone"
mkdir "$fixture/repo-clone/scripts"
cp "$script" "$fixture/repo-clone/scripts/setup-worktrees.sh"
bash "$fixture/repo-clone/scripts/setup-worktrees.sh"
[[ "$(git -C "$fixture/repo-clone/worktrees/dev" branch --show-current)" == dev ]]
[[ "$(git -C "$fixture/repo-clone" branch --show-current)" == main ]]
printf 'keep\n' > "$fixture/repo-clone/worktrees/dev/local.txt"
bash "$fixture/repo-clone/scripts/setup-worktrees.sh"
[[ "$(cat "$fixture/repo-clone/worktrees/dev/local.txt")" == keep ]]
if bash "$fixture/repo-clone/scripts/setup-worktrees.sh" --force 2>/dev/null; then exit 1; fi
[[ "$(git -C "$fixture/repo-clone" for-each-ref --format='%(refname:short)' refs/heads | sort | tr '\n' ' ')" == 'dev main ' ]]
echo 'dev worktree preservation: ok'
