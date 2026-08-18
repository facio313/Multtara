#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
# Resolved beside the installed script at runtime.
# shellcheck disable=SC1091
source "$SCRIPT_DIR/deploy-common.sh"

usage() {
  cat <<'EOF'
Usage:
  postgres-prune-backups.sh --target /opt/pongdang [--days 14] [--apply]

The default is a dry run. --apply removes only validated pongdang-*.dump files
older than the retention window and always preserves the newest archive.
EOF
}

TARGET_INPUT=""
RETENTION_DAYS=""
APPLY=0
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --target)
      [[ "$#" -ge 2 ]] || pongdang_die "--target requires a value"
      TARGET_INPUT="$2"
      shift 2
      ;;
    --days)
      [[ "$#" -ge 2 ]] || pongdang_die "--days requires a value"
      RETENTION_DAYS="$2"
      shift 2
      ;;
    --apply)
      APPLY=1
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
pongdang_require_command sha256sum
pongdang_validate_secret_env
pongdang_acquire_lock backup-prune

if [[ -z "$RETENTION_DAYS" ]]; then
  RETENTION_DAYS="$(pongdang_optional_env_value "$PONGDANG_ENV_FILE" BACKUP_RETENTION_DAYS)" \
    || pongdang_die "BACKUP_RETENTION_DAYS may appear at most once"
  RETENTION_DAYS="${RETENTION_DAYS:-14}"
fi
[[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]] || pongdang_die "retention days must be numeric"
(( RETENTION_DAYS >= 7 && RETENTION_DAYS <= 365 )) \
  || pongdang_die "retention days must be between 7 and 365"

BACKUP_DIR="$PONGDANG_TARGET/backups/postgres"
[[ -d "$BACKUP_DIR" && ! -L "$BACKUP_DIR" ]] || pongdang_die "backup directory is missing or unsafe"

archives=()
while IFS= read -r archive; do
  archives[${#archives[@]}]="$archive"
done < <(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'pongdang-*.dump' -print | LC_ALL=C sort)
if [[ "${#archives[@]}" -eq 0 ]]; then
  echo "no PostgreSQL backups to prune"
  exit 0
fi
newest="${archives[${#archives[@]} - 1]}"
removed=0
eligible=0

for archive in "${archives[@]}"; do
  [[ "$archive" != "$newest" ]] || continue
  if [[ -z "$(find "$archive" -maxdepth 0 -mtime "+$RETENTION_DAYS" -print)" ]]; then
    continue
  fi
  eligible=$((eligible + 1))
  checksum="$archive.sha256"
  if [[ ! -f "$checksum" || -L "$checksum" ]] \
      || ! (cd "$BACKUP_DIR" && sha256sum -c "${checksum##*/}" >/dev/null 2>&1); then
    echo "preserved old archive with missing/invalid checksum: $archive" >&2
    continue
  fi
  if [[ "$APPLY" -eq 1 ]]; then
    find "$archive" -delete
    find "$checksum" -delete
    removed=$((removed + 1))
    echo "removed expired backup: $archive"
  else
    echo "would remove expired backup: $archive"
  fi
done

echo "retention complete: eligible=$eligible removed=$removed newest_preserved=$newest"
