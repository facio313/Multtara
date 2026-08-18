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
  pi-deploy.sh validate-release /path/to/release.env
  pi-deploy.sh deploy --target /opt/pongdang --release-file /path/to/release.env
  pi-deploy.sh rollback --target /opt/pongdang

Deployment accepts only GHCR sha256 image digests. Effective Compose is checked
for build contexts before `pull` and `up --no-build` are allowed to run.
EOF
}

canonical_file() {
  local candidate="$1"
  local directory
  local basename
  [[ -f "$candidate" && ! -L "$candidate" ]] || pongdang_die "file is missing or unsafe: $candidate"
  directory="$(cd "$(dirname "$candidate")" && pwd -P)"
  basename="$(basename "$candidate")"
  printf '%s/%s\n' "$directory" "$basename"
}

validate_effective_config() {
  local config_file
  config_file="$(mktemp "$PONGDANG_TARGET/state/.effective-compose.XXXXXX")"
  if ! "${DEPLOY_COMPOSE[@]}" config --format json > "$config_file"; then
    find "$config_file" -delete
    pongdang_die "Docker Compose deployment configuration is invalid"
  fi
  if ! python3 - "$config_file" "$PONGDANG_BACKEND_IMAGE" "$PONGDANG_FRONTEND_IMAGE" <<'PY'
import json
import sys

path, backend_image, frontend_image = sys.argv[1:]
with open(path, encoding="utf-8") as source:
    config = json.load(source)

services = config.get("services", {})
expected_images = {
    "backend": backend_image,
    "collector": backend_image,
    "frontend": frontend_image,
}
for name, image in expected_images.items():
    service = services.get(name)
    if not service:
        raise SystemExit(f"missing deployment service: {name}")
    if service.get("build"):
        raise SystemExit(f"local build context survived deployment overlay: {name}")
    if service.get("image") != image:
        raise SystemExit(f"image mismatch for {name}")
    if service.get("pull_policy") != "always":
        raise SystemExit(f"pull_policy is not always for {name}")

ports = services["frontend"].get("ports", [])
if len(ports) != 1 or ports[0].get("host_ip") != "127.0.0.1" or int(ports[0]["target"]) != 8080:
    raise SystemExit("frontend origin must bind loopback and target unprivileged port 8080")
print("effective digest-only deployment config: PASS")
PY
  then
    find "$config_file" -delete
    pongdang_die "effective Compose violates the digest-only deployment contract"
  fi
  find "$config_file" -delete
}

select_release() {
  local release_file="$1"
  pongdang_validate_release_manifest "$release_file"
  export BACKEND_IMAGE="$PONGDANG_BACKEND_IMAGE"
  export FRONTEND_IMAGE="$PONGDANG_FRONTEND_IMAGE"
  DEPLOY_COMPOSE=(
    docker compose
    --project-name "$PONGDANG_PROJECT_NAME"
    --env-file "$PONGDANG_ENV_FILE"
    -f "$PONGDANG_TARGET/docker-compose.yml"
    -f "$PONGDANG_TARGET/docker-compose.deploy.yml"
  )
  validate_effective_config
}

store_release() {
  local source="$1"
  local destination="$PONGDANG_TARGET/releases/$PONGDANG_RELEASE_VERSION.env"
  local checksum="$destination.sha256"
  local checksum_tmp
  if [[ -e "$destination" || -L "$destination" ]]; then
    [[ -f "$destination" && ! -L "$destination" ]] || pongdang_die "stored release path is unsafe"
    cmp -s "$source" "$destination" || pongdang_die "release version already exists with different digests"
  else
    install -m 0644 "$source" "$destination"
  fi
  if [[ -e "$checksum" || -L "$checksum" ]]; then
    [[ -f "$checksum" && ! -L "$checksum" ]] || pongdang_die "stored release checksum path is unsafe"
    (
      cd "$PONGDANG_TARGET/releases"
      sha256sum -c "$PONGDANG_RELEASE_VERSION.env.sha256" >/dev/null
    ) || pongdang_die "stored release checksum is invalid"
  else
    checksum_tmp="$(mktemp "$PONGDANG_TARGET/releases/.release-checksum.XXXXXX")"
    (
      cd "$PONGDANG_TARGET/releases"
      sha256sum "$PONGDANG_RELEASE_VERSION.env" > "$checksum_tmp"
    )
    chmod 0644 "$checksum_tmp"
    mv "$checksum_tmp" "$checksum"
  fi
  PONGDANG_SELECTED_RELEASE="$destination"
}

database_is_running() {
  "${BASE_COMPOSE[@]}" ps --status running --services 2>/dev/null | grep -Fqx db
}

postgres_volume_exists() {
  local expected_volume="${PONGDANG_PROJECT_NAME}_postgres_data"
  local labelled
  if docker volume inspect "$expected_volume" >/dev/null 2>&1; then
    return 0
  fi
  labelled="$(
    docker volume ls --quiet \
      --filter "label=com.docker.compose.project=$PONGDANG_PROJECT_NAME" \
      --filter "label=com.docker.compose.volume=postgres_data" 2>/dev/null
  )" || pongdang_die "cannot inspect the PostgreSQL Docker volume"
  [[ -n "$labelled" ]]
}

backup_before_change() {
  local current="$PONGDANG_TARGET/state/current.release.env"
  if database_is_running; then
    "$PONGDANG_TARGET/scripts/postgres-backup.sh" --target "$PONGDANG_TARGET"
    return
  fi
  if [[ -e "$current" || -L "$current" ]] || postgres_volume_exists; then
    pongdang_die \
      "database is stopped but prior release state or PostgreSQL volume exists; start and verify the database so a backup can be taken before deployment"
  fi
  echo "verified first deployment: no running database, prior release state, or PostgreSQL volume"
}

activate_selected_release() {
  "${DEPLOY_COMPOSE[@]}" pull backend collector frontend
  "${DEPLOY_COMPOSE[@]}" up \
    -d \
    --no-build \
    --remove-orphans \
    --wait \
    --wait-timeout "$PONGDANG_DEPLOY_WAIT_SECONDS"
}

automatic_container_rollback() {
  local current="$PONGDANG_TARGET/state/current.release.env"
  local failed_version="$PONGDANG_RELEASE_VERSION"
  if [[ ! -f "$current" || -L "$current" ]]; then
    echo "no previous release is available for automatic container rollback" >&2
    return 1
  fi
  echo "deployment of $failed_version failed; restoring previous container images" >&2
  select_release "$current"
  "${DEPLOY_COMPOSE[@]}" pull backend collector frontend
  "${DEPLOY_COMPOSE[@]}" up \
    -d \
    --no-build \
    --remove-orphans \
    --wait \
    --wait-timeout "$PONGDANG_DEPLOY_WAIT_SECONDS"
}

finish_release_state() {
  local selected="$1"
  local current="$PONGDANG_TARGET/state/current.release.env"
  local previous="$PONGDANG_TARGET/state/previous.release.env"
  local current_next
  local previous_next=""

  if [[ -e "$current" || -L "$current" ]]; then
    [[ -f "$current" && ! -L "$current" ]] || pongdang_die "current release state is unsafe"
  fi
  if [[ -e "$previous" || -L "$previous" ]]; then
    [[ -f "$previous" && ! -L "$previous" ]] || pongdang_die "previous release state is unsafe"
  fi

  current_next="$(mktemp "$PONGDANG_TARGET/state/.current.release.XXXXXX")"
  install -m 0644 "$selected" "$current_next"
  if [[ -f "$current" ]] && ! cmp -s "$current" "$selected"; then
    previous_next="$(mktemp "$PONGDANG_TARGET/state/.previous.release.XXXXXX")"
    install -m 0644 "$current" "$previous_next"
  fi

  # Publish current first so a crash never claims the old image is active after
  # the new containers passed readiness. The prior release is staged before
  # either state file changes and is published immediately afterwards.
  mv "$current_next" "$current"
  if [[ -n "$previous_next" ]]; then
    mv "$previous_next" "$previous"
  fi
}

ACTION="${1:-}"
case "$ACTION" in
  validate-release)
    [[ "$#" -eq 2 ]] || { usage >&2; exit 2; }
    pongdang_require_command sha256sum
    RELEASE_FILE="$(canonical_file "$2")"
    pongdang_validate_release_manifest "$RELEASE_FILE"
    pongdang_verify_release_checksum "$RELEASE_FILE"
    echo "release manifest validation: PASS ($PONGDANG_RELEASE_VERSION)"
    exit 0
    ;;
  deploy|rollback) shift ;;
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
RELEASE_INPUT=""
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --target)
      [[ "$#" -ge 2 ]] || pongdang_die "--target requires a value"
      TARGET_INPUT="$2"
      shift 2
      ;;
    --release-file)
      [[ "$#" -ge 2 ]] || pongdang_die "--release-file requires a value"
      RELEASE_INPUT="$2"
      shift 2
      ;;
    *)
      usage >&2
      pongdang_die "unknown argument: $1"
      ;;
  esac
done

[[ -n "$TARGET_INPUT" ]] || pongdang_die "--target is required"
if [[ "$ACTION" == "deploy" ]]; then
  [[ -n "$RELEASE_INPUT" ]] || pongdang_die "deploy requires --release-file"
else
  [[ -z "$RELEASE_INPUT" ]] || pongdang_die "rollback does not accept --release-file"
fi

pongdang_validate_existing_target "$TARGET_INPUT"
pongdang_require_deploy_user
pongdang_require_pi_platform
pongdang_require_command python3
pongdang_require_command sha256sum
pongdang_require_compose
pongdang_validate_secret_env
pongdang_acquire_lock deploy

for required in docker-compose.yml docker-compose.deploy.yml; do
  [[ -f "$PONGDANG_TARGET/$required" && ! -L "$PONGDANG_TARGET/$required" ]] \
    || pongdang_die "deployment configuration is missing or unsafe: $required"
done

PONGDANG_DEPLOY_WAIT_SECONDS="$(pongdang_optional_env_value "$PONGDANG_ENV_FILE" DEPLOY_WAIT_SECONDS)" \
  || pongdang_die "DEPLOY_WAIT_SECONDS may appear at most once"
if [[ -z "$PONGDANG_DEPLOY_WAIT_SECONDS" ]]; then
  PONGDANG_DEPLOY_WAIT_SECONDS=180
fi
[[ "$PONGDANG_DEPLOY_WAIT_SECONDS" =~ ^[0-9]+$ ]] \
  || pongdang_die "DEPLOY_WAIT_SECONDS must be numeric"
(( PONGDANG_DEPLOY_WAIT_SECONDS >= 30 && PONGDANG_DEPLOY_WAIT_SECONDS <= 600 )) \
  || pongdang_die "DEPLOY_WAIT_SECONDS must be between 30 and 600"

BASE_COMPOSE=(
  docker compose
  --project-name "$PONGDANG_PROJECT_NAME"
  --env-file "$PONGDANG_ENV_FILE"
  -f "$PONGDANG_TARGET/docker-compose.yml"
)

if [[ "$ACTION" == "deploy" ]]; then
  RELEASE_FILE="$(canonical_file "$RELEASE_INPUT")"
  pongdang_verify_release_checksum "$RELEASE_FILE"
  select_release "$RELEASE_FILE"
  store_release "$RELEASE_FILE"
  backup_before_change
  if ! activate_selected_release; then
    automatic_container_rollback || true
    pongdang_die "deployment failed; database was not automatically restored"
  fi
  finish_release_state "$PONGDANG_SELECTED_RELEASE"
  echo "deployed $PONGDANG_RELEASE_VERSION at $PONGDANG_RELEASE_COMMIT"
  exit 0
fi

CURRENT_RELEASE="$PONGDANG_TARGET/state/current.release.env"
PREVIOUS_RELEASE="$PONGDANG_TARGET/state/previous.release.env"
[[ -f "$CURRENT_RELEASE" && ! -L "$CURRENT_RELEASE" ]] || pongdang_die "current release state is missing"
[[ -f "$PREVIOUS_RELEASE" && ! -L "$PREVIOUS_RELEASE" ]] || pongdang_die "previous release state is missing"
backup_before_change
select_release "$PREVIOUS_RELEASE"
if ! activate_selected_release; then
  pongdang_die "rollback images failed; current release state was preserved"
fi
finish_release_state "$PREVIOUS_RELEASE"
echo "rolled back to $PONGDANG_RELEASE_VERSION at $PONGDANG_RELEASE_COMMIT"
