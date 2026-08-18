#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
SUBJECT="$REPO_ROOT/scripts/setup-worktrees.sh"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/pongdang-worktree-test.XXXXXX")"

cleanup() {
  case "$TMP_ROOT" in
    "${TMPDIR:-/tmp}"/pongdang-worktree-test.*) find "$TMP_ROOT" -depth -delete ;;
    *) echo "refusing unexpected cleanup path: $TMP_ROOT" >&2 ;;
  esac
}
trap cleanup EXIT INT TERM

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

REMOTE="$TMP_ROOT/remote.git"
SEED="$TMP_ROOT/seed"
MAIN="$TMP_ROOT/main"
LOG="$TMP_ROOT/setup.log"

git init --bare --quiet "$REMOTE"
git init --quiet -b main "$SEED"
git -C "$SEED" config user.name "Ops Test"
git -C "$SEED" config user.email "ops-test@example.invalid"
printf '%s\n' "test repository" > "$SEED/README.md"
printf '%s\n' ".env" > "$SEED/.gitignore"
git -C "$SEED" add README.md .gitignore
git -C "$SEED" commit --quiet -m "initial"
for branch in cursor codex anthropic dev; do
  git -C "$SEED" branch "$branch"
done
git -C "$SEED" remote add origin "$REMOTE"
git -C "$SEED" push --quiet --all origin
git --git-dir="$REMOTE" symbolic-ref HEAD refs/heads/main

git clone --quiet --branch main "$REMOTE" "$MAIN"
mkdir -p "$MAIN/scripts"
cp "$SUBJECT" "$MAIN/scripts/setup-worktrees.sh"

(cd "$MAIN" && bash scripts/setup-worktrees.sh >"$LOG" 2>&1) \
  || { sed -n '1,240p' "$LOG" >&2; fail "initial setup failed"; }

for branch in cursor codex anthropic; do
  [ -d "$MAIN/worktrees/$branch" ] || fail "missing $branch worktree"
  [ "$(git -C "$MAIN/worktrees/$branch" branch --show-current)" = "$branch" ] \
    || fail "$branch worktree uses the wrong branch"
done

# An idempotent default run must not rebuild existing valid worktrees.
before="$(git -C "$MAIN/worktrees/cursor" rev-parse HEAD)"
(cd "$MAIN" && bash scripts/setup-worktrees.sh >"$LOG" 2>&1) \
  || { sed -n '1,240p' "$LOG" >&2; fail "idempotent setup failed"; }
[ "$(git -C "$MAIN/worktrees/cursor" rev-parse HEAD)" = "$before" ] \
  || fail "default setup moved an existing worktree"

# Even explicit force must refuse uncommitted and untracked content before any
# worktree is changed.
printf '%s\n' "keep me" > "$MAIN/worktrees/codex/untracked.txt"
if (cd "$MAIN" && bash scripts/setup-worktrees.sh --force >"$LOG" 2>&1); then
  fail "--force accepted a dirty worktree"
fi
[ -f "$MAIN/worktrees/codex/untracked.txt" ] || fail "dirty file was removed"
find "$MAIN/worktrees/codex/untracked.txt" -delete

# Ignored files may contain credentials and are not recoverable from a commit
# backup, so force must preserve and reject them as well.
printf '%s\n' "LOCAL_SECRET=test-only" > "$MAIN/worktrees/codex/.env"
if (cd "$MAIN" && bash scripts/setup-worktrees.sh --force >"$LOG" 2>&1); then
  fail "--force accepted an ignored file"
fi
[ -f "$MAIN/worktrees/codex/.env" ] || fail "ignored file was removed"
find "$MAIN/worktrees/codex/.env" -delete

# A committed, unpushed local change is preserved by the default path. Forced
# replacement is allowed only after a named backup ref retains the old commit.
git -C "$MAIN/worktrees/codex" config user.name "Ops Test"
git -C "$MAIN/worktrees/codex" config user.email "ops-test@example.invalid"
printf '%s\n' "local commit" > "$MAIN/worktrees/codex/local.txt"
git -C "$MAIN/worktrees/codex" add local.txt
git -C "$MAIN/worktrees/codex" commit --quiet -m "local work"
local_commit="$(git -C "$MAIN/worktrees/codex" rev-parse HEAD)"

(cd "$MAIN" && bash scripts/setup-worktrees.sh >"$LOG" 2>&1) \
  || { sed -n '1,240p' "$LOG" >&2; fail "default preservation run failed"; }
[ "$(git -C "$MAIN/worktrees/codex" rev-parse HEAD)" = "$local_commit" ] \
  || fail "default setup discarded an unpushed commit"

(cd "$MAIN" && bash scripts/setup-worktrees.sh --force >"$LOG" 2>&1) \
  || { sed -n '1,240p' "$LOG" >&2; fail "safe forced rebuild failed"; }
[ "$(git -C "$MAIN/worktrees/codex" rev-parse HEAD)" = "$(git -C "$MAIN" rev-parse origin/codex)" ] \
  || fail "forced rebuild did not restore origin/codex"
git -C "$MAIN" for-each-ref --format='%(objectname)' refs/backup/setup-worktrees \
  | grep -Fqx "$local_commit" \
  || fail "the unpushed commit is not reachable from a backup ref"

# A copy invoked from an agent worktree must refuse to target its own parent.
mkdir -p "$MAIN/worktrees/codex/scripts"
cp "$SUBJECT" "$MAIN/worktrees/codex/scripts/setup-worktrees.sh"
if (cd "$MAIN/worktrees/codex" && bash scripts/setup-worktrees.sh >"$LOG" 2>&1); then
  fail "agent-worktree invocation was not rejected"
fi
grep -Fq "run this command from the primary repository" "$LOG" \
  || fail "agent-worktree rejection did not explain the safe entry point"

echo "setup-worktrees safety integration: PASS"
