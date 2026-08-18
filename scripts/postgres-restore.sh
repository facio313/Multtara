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
  postgres-restore.sh verify --target /opt/pongdang --backup /path/to/pongdang-*.dump
  postgres-restore.sh restore --target /opt/pongdang --backup /path/to/pongdang-*.dump \
    --confirm RESTORE:<project-name>:<database-name>

`restore` stops backend and collector, takes a fresh pre-restore backup, replaces
the application database, and starts the current digest-pinned release only
after pg_restore succeeds. A failed restore remains offline for investigation.
EOF
}

ACTION="${1:-}"
case "$ACTION" in
  verify|restore) shift ;;
  -h|--help|"")
    usage
    exit 0
    ;;
  *)
    usage >&2
    pongdang_die "unknown action: $ACTION"
    ;;
esac

TARGET_INPUT=""
BACKUP_INPUT=""
CONFIRMATION=""
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --target)
      [[ "$#" -ge 2 ]] || pongdang_die "--target requires a value"
      TARGET_INPUT="$2"
      shift 2
      ;;
    --backup)
      [[ "$#" -ge 2 ]] || pongdang_die "--backup requires a value"
      BACKUP_INPUT="$2"
      shift 2
      ;;
    --confirm)
      [[ "$#" -ge 2 ]] || pongdang_die "--confirm requires a value"
      CONFIRMATION="$2"
      shift 2
      ;;
    *)
      usage >&2
      pongdang_die "unknown argument: $1"
      ;;
  esac
done

[[ -n "$TARGET_INPUT" ]] || pongdang_die "--target is required"
[[ -n "$BACKUP_INPUT" ]] || pongdang_die "--backup is required"
pongdang_validate_existing_target "$TARGET_INPUT"
pongdang_require_deploy_user
pongdang_require_pi_platform
pongdang_require_command sha256sum
pongdang_require_compose
pongdang_validate_secret_env
pongdang_acquire_lock deploy 8
pongdang_acquire_lock backup-prune 7

BACKUP_DIR="$PONGDANG_TARGET/backups/postgres"
[[ -d "$BACKUP_DIR" && ! -L "$BACKUP_DIR" ]] || pongdang_die "backup directory is missing or unsafe"
[[ -f "$BACKUP_INPUT" && ! -L "$BACKUP_INPUT" ]] || pongdang_die "backup archive is missing or unsafe"
backup_parent="$(cd "$(dirname "$BACKUP_INPUT")" && pwd -P)"
backup_name="$(basename "$BACKUP_INPUT")"
BACKUP_FILE="$backup_parent/$backup_name"
[[ "$backup_parent" == "$BACKUP_DIR" ]] || pongdang_die "backup must be inside $BACKUP_DIR"
[[ "$backup_name" =~ ^pongdang-[0-9]{8}T[0-9]{6}Z-[0-9]+\.dump$ ]] || pongdang_die "backup filename is invalid"
CHECKSUM_FILE="$BACKUP_FILE.sha256"
[[ -f "$CHECKSUM_FILE" && ! -L "$CHECKSUM_FILE" ]] || pongdang_die "backup checksum is missing"
(cd "$BACKUP_DIR" && sha256sum -c "${CHECKSUM_FILE##*/}")

COMPOSE=(
  docker compose
  --project-name "$PONGDANG_PROJECT_NAME"
  --env-file "$PONGDANG_ENV_FILE"
  -f "$PONGDANG_TARGET/docker-compose.yml"
)
"${COMPOSE[@]}" ps --status running --services | grep -Fqx db \
  || pongdang_die "PostgreSQL service is not running"
"${COMPOSE[@]}" exec -T db pg_restore --list < "$BACKUP_FILE" >/dev/null \
  || pongdang_die "pg_restore rejected the archive"

if [[ "$ACTION" == "verify" ]]; then
  echo "backup verification: PASS ($BACKUP_FILE)"
  exit 0
fi

expected_confirmation="RESTORE:$PONGDANG_PROJECT_NAME:$PONGDANG_POSTGRES_DB"
[[ "$CONFIRMATION" == "$expected_confirmation" ]] \
  || pongdang_die "restore requires --confirm $expected_confirmation"

CURRENT_RELEASE="$PONGDANG_TARGET/state/current.release.env"
[[ -f "$CURRENT_RELEASE" && ! -L "$CURRENT_RELEASE" ]] \
  || pongdang_die "current release state is missing; refusing to replace the database"
pongdang_validate_release_manifest "$CURRENT_RELEASE"
export BACKEND_IMAGE="$PONGDANG_BACKEND_IMAGE"
export FRONTEND_IMAGE="$PONGDANG_FRONTEND_IMAGE"
DEPLOY_COMPOSE=(
  docker compose
  --project-name "$PONGDANG_PROJECT_NAME"
  --env-file "$PONGDANG_ENV_FILE"
  -f "$PONGDANG_TARGET/docker-compose.yml"
  -f "$PONGDANG_TARGET/docker-compose.deploy.yml"
)

echo "creating mandatory pre-restore backup"
"$PONGDANG_TARGET/scripts/postgres-backup.sh" \
  --target "$PONGDANG_TARGET" \
  --skip-retention
pongdang_acquire_lock database

# Revalidate immediately before the destructive step. The backup-prune lock
# prevents the requested source from being removed by the supported retention
# command while the restore is in progress.
(cd "$BACKUP_DIR" && sha256sum -c "${CHECKSUM_FILE##*/}")
"${COMPOSE[@]}" exec -T db pg_restore --list < "$BACKUP_FILE" >/dev/null \
  || pongdang_die "pg_restore rejected the archive after the pre-restore backup"

"${COMPOSE[@]}" stop collector backend
restore_succeeded=0
cleanup_restore() {
  if [[ "$restore_succeeded" -ne 1 ]]; then
    "${COMPOSE[@]}" stop collector backend >/dev/null 2>&1 || true
    echo "restore did not complete; backend and collector remain stopped" >&2
  fi
}
trap cleanup_restore EXIT INT TERM

"${COMPOSE[@]}" exec -T db psql \
  --username "$PONGDANG_POSTGRES_USER" \
  --dbname postgres \
  --set ON_ERROR_STOP=1 <<SQL
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = '$PONGDANG_POSTGRES_DB'
  AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS "$PONGDANG_POSTGRES_DB";
CREATE DATABASE "$PONGDANG_POSTGRES_DB" OWNER "$PONGDANG_POSTGRES_USER";
SQL

"${COMPOSE[@]}" exec -T db pg_restore \
  --username "$PONGDANG_POSTGRES_USER" \
  --dbname "$PONGDANG_POSTGRES_DB" \
  --exit-on-error \
  --no-owner \
  --no-privileges < "$BACKUP_FILE"

"${DEPLOY_COMPOSE[@]}" up \
  -d \
  --no-build \
  --wait \
  --wait-timeout 180 \
  backend collector frontend
restore_succeeded=1
echo "database restore complete: $BACKUP_FILE"
