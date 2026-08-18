#!/usr/bin/env bash
# Multtara — safe agent worktree bootstrap
# Usage: ./scripts/setup-worktrees.sh [--force]
set -euo pipefail

FORCE=0

usage() {
  cat <<'EOF'
Usage: ./scripts/setup-worktrees.sh [--force]

Without --force, the script creates only missing worktrees and refuses to move
an existing local branch. Existing correctly registered worktrees are preserved.

With --force, clean registered worktrees may be rebuilt. Every commit that
could become unreachable is first retained below:

  refs/backup/setup-worktrees/<UTC timestamp>-<pid>/

Modified, untracked, or ignored files are never removed, including with
--force. Preserve them explicitly before retrying.
EOF
}

die() {
  echo "error: $*" >&2
  exit 1
}

case "${1:-}" in
  "") ;;
  --force) FORCE=1 ;;
  -h|--help)
    usage
    exit 0
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

if [ "$#" -gt 1 ]; then
  usage >&2
  exit 2
fi

SCRIPT_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
CURRENT_ROOT="$(git -C "$SCRIPT_ROOT" rev-parse --show-toplevel 2>/dev/null)" \
  || die "the script must be run from a Git worktree"
CURRENT_ROOT="$(cd "$CURRENT_ROOT" && pwd -P)"

COMMON_GIT_DIR="$(git -C "$CURRENT_ROOT" rev-parse --path-format=absolute --git-common-dir)"
COMMON_GIT_DIR="$(cd "$COMMON_GIT_DIR" && pwd -P)"
case "$COMMON_GIT_DIR" in
  */.git) ;;
  *) die "expected the shared Git directory to end in /.git: $COMMON_GIT_DIR" ;;
esac

MAIN_ROOT="$(cd "$(dirname "$COMMON_GIT_DIR")" && pwd -P)"
[ "$CURRENT_ROOT" = "$MAIN_ROOT" ] || die \
  "run this command from the primary repository ($MAIN_ROOT), not from an agent worktree ($CURRENT_ROOT)"

PRIMARY_ROOT="$(git -C "$MAIN_ROOT" rev-parse --show-toplevel 2>/dev/null)" \
  || die "cannot resolve the primary repository"
PRIMARY_ROOT="$(cd "$PRIMARY_ROOT" && pwd -P)"
[ "$PRIMARY_ROOT" = "$MAIN_ROOT" ] || die "primary repository path validation failed"

WORKTREES_ROOT="$MAIN_ROOT/worktrees"
if [ -L "$WORKTREES_ROOT" ]; then
  die "refusing a symlinked worktree directory: $WORKTREES_ROOT"
fi
mkdir -p "$WORKTREES_ROOT"
WORKTREES_ROOT="$(cd "$WORKTREES_ROOT" && pwd -P)"
[ "$WORKTREES_ROOT" = "$MAIN_ROOT/worktrees" ] || die "worktree directory escaped the repository"

git -C "$MAIN_ROOT" remote get-url origin >/dev/null 2>&1 \
  || die "the origin remote is required"
git -C "$MAIN_ROOT" fetch origin

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
BACKUP_PREFIX="refs/backup/setup-worktrees/$RUN_ID"

registered_worktree_path() {
  git -C "$MAIN_ROOT" worktree list --porcelain | awk -v wanted="$1" '
    $1 == "worktree" {
      path = substr($0, length("worktree ") + 1)
    }
    $1 == "branch" && $2 == wanted {
      print path
      exit
    }
  '
}

registered_path_head() {
  git -C "$MAIN_ROOT" worktree list --porcelain | awk -v wanted="$1" '
    $1 == "worktree" {
      path = substr($0, length("worktree ") + 1)
      head = ""
    }
    $1 == "HEAD" {
      head = $2
    }
    path == wanted && ($1 == "branch" || $1 == "detached") {
      print head
      exit
    }
  '
}

registered_path_branch() {
  git -C "$MAIN_ROOT" worktree list --porcelain | awk -v wanted="$1" '
    $1 == "worktree" {
      path = substr($0, length("worktree ") + 1)
    }
    path == wanted && $1 == "branch" {
      print $2
      exit
    }
  '
}

desired_ref_for() {
  if git -C "$MAIN_ROOT" show-ref --verify --quiet "refs/remotes/origin/$1"; then
    echo "refs/remotes/origin/$1"
  elif git -C "$MAIN_ROOT" show-ref --verify --quiet refs/remotes/origin/main; then
    echo refs/remotes/origin/main
  else
    die "neither origin/$1 nor origin/main exists"
  fi
}

assert_exact_target() {
  local branch="$1"
  local target="$2"
  [ "$target" = "$WORKTREES_ROOT/$branch" ] \
    || die "resolved target does not match the approved path for $branch: $target"
  [ ! -L "$target" ] || die "refusing a symlinked target: $target"
}

assert_clean_worktree() {
  local target="$1"
  local worktree_status
  # Ignored files are included because they may contain local credentials such
  # as .env. A commit backup ref cannot recover them after directory removal.
  worktree_status="$(git -C "$target" status --porcelain --untracked-files=all --ignored)" \
    || die "cannot inspect worktree state: $target"
  if [ -n "$worktree_status" ]; then
    die "refusing to remove worktree $target with modified, untracked, or ignored files; preserve them explicitly"
  fi
}

describe_local_divergence() {
  local branch="$1"
  local desired_ref="$2"
  local ahead
  local unpushed
  ahead="$(git -C "$MAIN_ROOT" rev-list --count "$desired_ref..refs/heads/$branch")"
  unpushed="$(git -C "$MAIN_ROOT" rev-list --count "refs/heads/$branch" --not --remotes)"
  echo "local $branch differs from $desired_ref (ahead=$ahead, unpushed=$unpushed)" >&2
}

backup_commit() {
  local label="$1"
  local commit="$2"
  local backup_ref="$BACKUP_PREFIX/$label"
  git -C "$MAIN_ROOT" update-ref "$backup_ref" "$commit"
  echo "backup: $backup_ref -> $commit"
}

# Preflight every target before changing any worktree. This avoids a half-rebuilt
# fleet when a later target contains local work that must be preserved.
for branch in cursor codex anthropic; do
  target="$WORKTREES_ROOT/$branch"
  expected_branch_ref="refs/heads/$branch"
  assert_exact_target "$branch" "$target"

  branch_path="$(registered_worktree_path "$expected_branch_ref")"
  if [ -n "$branch_path" ] && [ "$branch_path" != "$target" ]; then
    die "$branch is checked out outside its approved path: $branch_path"
  fi

  target_head="$(registered_path_head "$target")"
  target_branch="$(registered_path_branch "$target")"
  if [ -n "$target_head" ]; then
    [ -d "$target" ] || die "registered worktree path is missing: $target"
    resolved_target="$(git -C "$target" rev-parse --show-toplevel 2>/dev/null)" \
      || die "registered target is not a usable Git worktree: $target"
    resolved_target="$(cd "$resolved_target" && pwd -P)"
    [ "$resolved_target" = "$target" ] \
      || die "registered target resolved outside its approved path: $resolved_target"
  fi
  if [ -e "$target" ] && [ -z "$target_head" ]; then
    die "target exists but is not a registered worktree: $target"
  fi
  if [ -n "$target_head" ] && [ "$target_branch" != "$expected_branch_ref" ]; then
    if [ "$FORCE" -eq 0 ]; then
      die "$target is registered to ${target_branch:-a detached HEAD}; use --force only after reviewing it"
    fi
    assert_clean_worktree "$target"
  fi
  if [ -n "$target_head" ] && [ "$FORCE" -eq 1 ]; then
    assert_clean_worktree "$target"
  fi

  desired_ref="$(desired_ref_for "$branch")"
  if git -C "$MAIN_ROOT" show-ref --verify --quiet "$expected_branch_ref" \
      && [ "$(git -C "$MAIN_ROOT" rev-parse "$expected_branch_ref")" != "$(git -C "$MAIN_ROOT" rev-parse "$desired_ref")" ] \
      && [ "$FORCE" -eq 0 ] \
      && [ -z "$target_head" ]; then
    describe_local_divergence "$branch" "$desired_ref"
    die "refusing to move local $branch without --force and a backup ref"
  fi
done

for branch in cursor codex anthropic; do
  target="$WORKTREES_ROOT/$branch"
  expected_branch_ref="refs/heads/$branch"
  desired_ref="$(desired_ref_for "$branch")"
  target_head="$(registered_path_head "$target")"
  target_branch="$(registered_path_branch "$target")"

  if [ -n "$target_head" ] && [ "$target_branch" = "$expected_branch_ref" ] && [ "$FORCE" -eq 0 ]; then
    if [ "$(git -C "$MAIN_ROOT" rev-parse "$expected_branch_ref")" != "$(git -C "$MAIN_ROOT" rev-parse "$desired_ref")" ]; then
      describe_local_divergence "$branch" "$desired_ref"
    fi
    echo "preserved: $target ($branch)"
    continue
  fi

  if [ -n "$target_head" ]; then
    backup_commit "$branch-worktree" "$target_head"
    git -C "$MAIN_ROOT" worktree remove "$target"
  fi

  if git -C "$MAIN_ROOT" show-ref --verify --quiet "$expected_branch_ref"; then
    local_commit="$(git -C "$MAIN_ROOT" rev-parse "$expected_branch_ref")"
    desired_commit="$(git -C "$MAIN_ROOT" rev-parse "$desired_ref")"
    if [ "$local_commit" != "$desired_commit" ]; then
      backup_commit "$branch-branch" "$local_commit"
      git -C "$MAIN_ROOT" branch -f "$branch" "$desired_ref"
    fi
  else
    git -C "$MAIN_ROOT" branch "$branch" "$desired_ref"
  fi

  [ ! -e "$target" ] || die "target remained after safe worktree removal: $target"
  git -C "$MAIN_ROOT" worktree add "$target" "$branch"
  if git -C "$MAIN_ROOT" show-ref --verify --quiet "refs/remotes/origin/$branch"; then
    git -C "$target" branch --set-upstream-to="origin/$branch" "$branch"
  fi
  echo "ready: $target ($branch)"
done

# The user-owned dev branch is never reset by this script. Create it only when
# it does not yet exist, using its remote branch when available.
if ! git -C "$MAIN_ROOT" show-ref --verify --quiet refs/heads/dev; then
  if git -C "$MAIN_ROOT" show-ref --verify --quiet refs/remotes/origin/dev; then
    git -C "$MAIN_ROOT" branch --track dev origin/dev
  else
    git -C "$MAIN_ROOT" branch dev origin/main
  fi
fi

echo
git -C "$MAIN_ROOT" worktree list
echo
git -C "$MAIN_ROOT" branch -vv
