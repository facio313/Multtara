#!/usr/bin/env bash
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
# Resolved beside the installed script at runtime.
# shellcheck disable=SC1091
source "$SCRIPT_DIR/deploy-common.sh"

usage() {
  cat <<'EOF'
Usage:
  postgres-backup.sh --target /opt/pongdang-multtara [--retention-days 14] [--skip-retention]

Creates a PostgreSQL custom-format archive, validates it through pg_restore,
writes a sha256 checksum, and then enforces retention.

--skip-retention is reserved for the restore workflow so the requested source
archive cannot be pruned between verification and use.
EOF
}

TARGET_INPUT=""
RETENTION_DAYS=""
SKIP_RETENTION=0
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --target)
      [[ "$#" -ge 2 ]] || pongdang_die "--target requires a value"
      TARGET_INPUT="$2"
      shift 2
      ;;
    --retention-days)
      [[ "$#" -ge 2 ]] || pongdang_die "--retention-days requires a value"
      RETENTION_DAYS="$2"
      shift 2
      ;;
    --skip-retention)
      SKIP_RETENTION=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      pongdang_die "unknown argument: $1"
      ;;
  esac
done

[[ -n "$TARGET_INPUT" ]] || pongdang_die "--target is required"
pongdang_validate_existing_target "$TARGET_INPUT"
pongdang_require_deploy_user
pongdang_require_pi_platform
pongdang_require_command sha256sum
pongdang_require_compose
pongdang_validate_secret_env
pongdang_acquire_lock database

if [[ -z "$RETENTION_DAYS" ]]; then
  RETENTION_DAYS="$(pongdang_optional_env_value "$PONGDANG_ENV_FILE" BACKUP_RETENTION_DAYS)" \
    || pongdang_die "BACKUP_RETENTION_DAYS may appear at most once"
  RETENTION_DAYS="${RETENTION_DAYS:-14}"
fi
[[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]] || pongdang_die "retention days must be numeric"
(( RETENTION_DAYS >= 7 && RETENTION_DAYS <= 365 )) \
  || pongdang_die "retention days must be between 7 and 365"

"$PONGDANG_SHARED_DB_TOOL" ready \
  || pongdang_die "shared PostgreSQL database is not ready"

BACKUP_DIR="$PONGDANG_TARGET/backups/postgres"
[[ -d "$BACKUP_DIR" && ! -L "$BACKUP_DIR" ]] || pongdang_die "backup directory is missing or unsafe"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)-$$"
final="$BACKUP_DIR/pongdang-$timestamp.dump"
partial="$BACKUP_DIR/.pongdang-$timestamp.$$.partial"
checksum="$final.sha256"
complete=0
dumped=""
[[ ! -e "$final" && ! -L "$final" \
    && ! -e "$partial" && ! -L "$partial" \
    && ! -e "$checksum" && ! -L "$checksum" ]] \
  || pongdang_die "backup timestamp collision or unsafe output path: $timestamp"

cleanup_incomplete() {
  if [[ "$complete" -ne 1 ]]; then
    for candidate in "$partial" "$final" "$checksum"; do
      case "$candidate" in
        "$BACKUP_DIR"/*) [[ ! -e "$candidate" ]] || find "$candidate" -delete ;;
        *) echo "refusing unexpected backup cleanup path: $candidate" >&2 ;;
      esac
    done
  fi
}
trap cleanup_incomplete EXIT INT TERM

dumped="$("$PONGDANG_SHARED_DB_TOOL" dump --output "$partial")" \
  || pongdang_die "shared PostgreSQL dump failed"
[[ "$dumped" == "$partial" ]] \
  || pongdang_die "shared PostgreSQL dump returned an unexpected output path"
[[ -s "$partial" ]] || pongdang_die "pg_dump produced an empty archive"
"$PONGDANG_SHARED_DB_TOOL" verify --backup "$partial" \
  || pongdang_die "pg_restore rejected the new archive"
chmod 0600 "$partial"
mv "$partial" "$final"
(
  cd "$BACKUP_DIR"
  sha256sum "${final##*/}" > "${checksum##*/}"
)
chmod 0600 "$checksum"
complete=1

if [[ "$SKIP_RETENTION" -eq 0 ]]; then
  "$PONGDANG_TARGET/scripts/postgres-prune-backups.sh" \
    --target "$PONGDANG_TARGET" \
    --days "$RETENTION_DAYS" \
    --apply
fi
echo "$final"
