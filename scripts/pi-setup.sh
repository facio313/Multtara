#!/usr/bin/env bash
set -euo pipefail
umask 027

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
SOURCE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
# Resolved beside the installed script at runtime.
# shellcheck disable=SC1091
source "$SCRIPT_DIR/deploy-common.sh"

usage() {
  cat <<'EOF'
Usage:
  sudo ./scripts/pi-setup.sh --target /opt/pongdang \
    --deploy-user pongdang [--project-name pongdang]

Installs only deployment configuration and scripts. It never builds, pulls, or
starts an image and never generates a credential.
EOF
}

TARGET_INPUT=""
DEPLOY_USER=""
PROJECT_NAME=""

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --target)
      [[ "$#" -ge 2 ]] || pongdang_die "--target requires a value"
      TARGET_INPUT="$2"
      shift 2
      ;;
    --deploy-user)
      [[ "$#" -ge 2 ]] || pongdang_die "--deploy-user requires a value"
      DEPLOY_USER="$2"
      shift 2
      ;;
    --project-name)
      [[ "$#" -ge 2 ]] || pongdang_die "--project-name requires a value"
      PROJECT_NAME="$2"
      shift 2
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
[[ -n "$DEPLOY_USER" ]] || pongdang_die "--deploy-user is required"
[[ "$EUID" -eq 0 ]] || pongdang_die "setup must run as root"
[[ "$DEPLOY_USER" =~ ^[a-z_][a-z0-9_-]*[$]?$ ]] || pongdang_die "invalid deployment user"
getent passwd "$DEPLOY_USER" >/dev/null || pongdang_die "deployment user does not exist: $DEPLOY_USER"

pongdang_require_pi_platform
pongdang_resolve_target "$TARGET_INPUT"
[[ "$SOURCE_ROOT" != "$PONGDANG_TARGET" ]] \
  || pongdang_die "extract the release bundle outside the deployment target before setup"

if [[ -z "$PROJECT_NAME" ]]; then
  PROJECT_NAME="${PONGDANG_TARGET##*/}"
fi
[[ "$PROJECT_NAME" =~ ^pongdang(-[a-z0-9]+)*$ ]] || pongdang_die "invalid Compose project name"

for required in \
  docker-compose.yml \
  docker-compose.deploy.yml \
  .env.example \
  scripts/deploy-common.sh \
  scripts/pi-deploy.sh \
  scripts/postgres-backup.sh \
  scripts/postgres-prune-backups.sh \
  scripts/postgres-restore.sh; do
  [[ -f "$SOURCE_ROOT/$required" && ! -L "$SOURCE_ROOT/$required" ]] \
    || pongdang_die "release bundle file is missing or unsafe: $required"
done

pongdang_require_command docker
pongdang_require_command runuser
runuser -u "$DEPLOY_USER" -- docker info >/dev/null 2>&1 \
  || pongdang_die "$DEPLOY_USER cannot access Docker; configure rootless Docker or docker-group access first"
compose_version="$(runuser -u "$DEPLOY_USER" -- docker compose version --short 2>/dev/null)" \
  || pongdang_die "Docker Compose plugin is unavailable to $DEPLOY_USER"
compose_version="${compose_version#v}"
compose_major="${compose_version%%.*}"
compose_minor="${compose_version#*.}"
compose_minor="${compose_minor%%.*}"
compose_patch="${compose_version#*.*.}"
compose_patch="${compose_patch%%[-+]*}"
compose_patch="${compose_patch%%.*}"
[[ "$compose_major" =~ ^[0-9]+$ && "$compose_minor" =~ ^[0-9]+$ && "$compose_patch" =~ ^[0-9]+$ ]] \
  || pongdang_die "cannot parse Docker Compose version: $compose_version"
if (( compose_major < PONGDANG_MIN_COMPOSE_MAJOR \
    || (compose_major == PONGDANG_MIN_COMPOSE_MAJOR \
        && (compose_minor < PONGDANG_MIN_COMPOSE_MINOR \
            || (compose_minor == PONGDANG_MIN_COMPOSE_MINOR \
                && compose_patch < PONGDANG_MIN_COMPOSE_PATCH))) )); then
  pongdang_die "Docker Compose >= ${PONGDANG_MIN_COMPOSE_MAJOR}.${PONGDANG_MIN_COMPOSE_MINOR}.${PONGDANG_MIN_COMPOSE_PATCH} is required"
fi

DEPLOY_GROUP="$(id -gn "$DEPLOY_USER")"
if [[ -e "$PONGDANG_TARGET" ]]; then
  [[ -d "$PONGDANG_TARGET" && ! -L "$PONGDANG_TARGET" ]] \
    || pongdang_die "deployment target is not a regular directory"
  marker="$PONGDANG_TARGET/$PONGDANG_MARKER_NAME"
  if [[ -e "$marker" ]]; then
    pongdang_validate_existing_target "$PONGDANG_TARGET"
    [[ "$PONGDANG_DEPLOY_USER" == "$DEPLOY_USER" ]] || pongdang_die "existing deployment user mismatch"
    [[ "$PONGDANG_PROJECT_NAME" == "$PROJECT_NAME" ]] || pongdang_die "existing Compose project mismatch"
  elif [[ -n "$(find "$PONGDANG_TARGET" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
    pongdang_die "refusing a non-empty unmarked target: $PONGDANG_TARGET"
  fi
fi

install -d -m 0755 -o root -g root "$PONGDANG_TARGET" "$PONGDANG_TARGET/scripts"
install -d -m 0750 -o "$DEPLOY_USER" -g "$DEPLOY_GROUP" \
  "$PONGDANG_TARGET/state" \
  "$PONGDANG_TARGET/releases" \
  "$PONGDANG_TARGET/backups" \
  "$PONGDANG_TARGET/backups/postgres"
pongdang_validate_layout

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="$PONGDANG_TARGET/state/setup-$timestamp-$$"
[[ ! -e "$backup_dir" && ! -L "$backup_dir" ]] \
  || pongdang_die "setup backup path already exists or is unsafe: $backup_dir"
for relative in docker-compose.yml docker-compose.deploy.yml .env.example; do
  if [[ -e "$PONGDANG_TARGET/$relative" || -L "$PONGDANG_TARGET/$relative" ]]; then
    [[ -f "$PONGDANG_TARGET/$relative" && ! -L "$PONGDANG_TARGET/$relative" ]] \
      || pongdang_die "existing deployment file is unsafe: $PONGDANG_TARGET/$relative"
    install -d -m 0750 -o "$DEPLOY_USER" -g "$DEPLOY_GROUP" "$backup_dir"
    install -m 0640 -o "$DEPLOY_USER" -g "$DEPLOY_GROUP" \
      "$PONGDANG_TARGET/$relative" "$backup_dir/$relative"
  fi
done

install -m 0444 -o root -g root \
  "$SOURCE_ROOT/docker-compose.yml" \
  "$SOURCE_ROOT/docker-compose.deploy.yml" \
  "$SOURCE_ROOT/.env.example" \
  "$PONGDANG_TARGET/"
install -m 0555 -o root -g root \
  "$SOURCE_ROOT/scripts/deploy-common.sh" \
  "$SOURCE_ROOT/scripts/pi-deploy.sh" \
  "$SOURCE_ROOT/scripts/postgres-backup.sh" \
  "$SOURCE_ROOT/scripts/postgres-prune-backups.sh" \
  "$SOURCE_ROOT/scripts/postgres-restore.sh" \
  "$PONGDANG_TARGET/scripts/"

marker_tmp="$(mktemp "${TMPDIR:-/tmp}/pongdang-marker.XXXXXX")"
cleanup_marker() {
  case "$marker_tmp" in
    "${TMPDIR:-/tmp}"/pongdang-marker.*) find "$marker_tmp" -delete ;;
    *) echo "refusing unexpected marker cleanup path: $marker_tmp" >&2 ;;
  esac
}
trap cleanup_marker EXIT INT TERM
{
  printf 'FORMAT=PONGDANG_DEPLOYMENT_V1\n'
  printf 'TARGET=%s\n' "$PONGDANG_TARGET"
  printf 'DEPLOY_USER=%s\n' "$DEPLOY_USER"
  printf 'PROJECT_NAME=%s\n' "$PROJECT_NAME"
} > "$marker_tmp"
install -m 0444 -o root -g root "$marker_tmp" "$PONGDANG_TARGET/$PONGDANG_MARKER_NAME"

if [[ -e "$PONGDANG_TARGET/.env" ]]; then
  [[ -f "$PONGDANG_TARGET/.env" && ! -L "$PONGDANG_TARGET/.env" ]] \
    || pongdang_die "existing .env is not a regular file"
  echo "preserved existing secret file: $PONGDANG_TARGET/.env"
else
  install -m 0600 -o "$DEPLOY_USER" -g "$DEPLOY_GROUP" \
    "$SOURCE_ROOT/.env.example" "$PONGDANG_TARGET/.env"
  echo "placeholder environment created: $PONGDANG_TARGET/.env"
fi

echo "deployment tooling installed at $PONGDANG_TARGET"
echo "next: replace every required placeholder in $PONGDANG_TARGET/.env as $DEPLOY_USER"
