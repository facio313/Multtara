#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
# Never expose password-bearing environment assignments when a caller supplied
# bash -x. Explicit diagnostics below contain no credentials.
set +x

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
# Resolved beside this script both in a release bundle and after pi-setup.
# shellcheck disable=SC1091
source "$SCRIPT_DIR/deploy-common.sh"

BUNDLE_NAME="pre-cksdb-rollback"
BUNDLE_FORMAT="PONGDANG_PRE_CKSDB_ROLLBACK_V1"
BUNDLE_MANIFEST="SHA256SUMS"
BUNDLE_MANIFEST_CHECKSUM="SHA256SUMS.sha256"
ACTIVE_FORMAT="PONGDANG_PRE_CKSDB_ROLLBACK_ACTIVE_V1"
DATA_CONFIRMATION="NO_CKSDB_WRITES_SINCE_CUTOVER"
CUTOVER_CONFIRMATION="CUTOVER:multtara:pg15-to-cksdb"
LEGACY_PG_MAJOR=15
LEGACY_DB_NAME="pongdang"
LEGACY_DB_ROLE="pongdang"
LEGACY_DB_SERVICE="db"
LEGACY_VOLUME_KEY="postgres_data"
LEGACY_FORENSIC_SCRIPTS=(
  deploy-common.sh
  pi-deploy.sh
  postgres-backup.sh
  postgres-prune-backups.sh
  postgres-restore.sh
)

usage() {
  cat <<'EOF'
Usage:
  db-migration-rollback.sh stage --target /opt/pongdang-multtara
  db-migration-rollback.sh verify --target /opt/pongdang-multtara
  db-migration-rollback.sh cutover --target /opt/pongdang-multtara \
    --confirm CUTOVER:multtara:pg15-to-cksdb
  db-migration-rollback.sh restore --target /opt/pongdang-multtara \
    --confirm RESTORE:pre-cksdb-standalone:<project-name>:postgres_data \
    --confirm-data-state NO_CKSDB_WRITES_SINCE_CUTOVER

`stage` must run while the original PostgreSQL 15 `db` service is healthy and
before pi-setup replaces the deployment files. It creates exactly one protected
state/pre-cksdb-rollback bundle and never overwrites it.

`verify` is read-only. It verifies the fixed bundle path, complete manifest and
manifest sidecar, metadata, retained volume identity, release, environment, and
legacy Compose contract without taking a lock or changing containers.

`cutover` stops the bundled PG15 backend and collector, creates the final
source dump, restores it through the pinned cksDB tool, compares deterministic
schema/constraint/index/sequence and exact table-row-count fingerprints, and
only then finalizes cksDB and atomically publishes the fixed cutover marker.
Any failure leaves application writers stopped and publishes no marker.

`restore` is an emergency topology rollback. It is safe only when an operator
can prove that cksDB has accepted no application writes since cutover. The
command first stops all Multtara writers, makes and verifies a current cksDB
backup, and then starts the bundled digest-pinned topology on the retained PG15
volume. A PostgreSQL 16 dump is deliberately never restored into PostgreSQL 15.

If cksDB may have accepted even one write, do not use this command. Keep cksDB
active, roll back only application images, or restore the verified backup into a
fresh PostgreSQL 16 standalone instance under a separately reviewed procedure.
EOF
}

require_plain_file() {
  local file="$1"
  local description="$2"
  local mode

  [[ -f "$file" && ! -L "$file" ]] \
    || pongdang_die "$description is missing or unsafe: $file"
  mode="$(stat -c '%a' "$file")"
  (( (8#$mode & 022) == 0 )) \
    || pongdang_die "$description must not be group/world writable: $file"
}

require_owned_mode() {
  local path="$1"
  local expected_mode="$2"
  local description="$3"
  local mode
  local owner

  [[ ! -L "$path" ]] || pongdang_die "$description must not be a symlink: $path"
  mode="$(stat -c '%a' "$path")"
  owner="$(stat -c '%u' "$path")"
  [[ "$mode" == "$expected_mode" ]] \
    || pongdang_die "$description must have mode 0$expected_mode, found 0$mode"
  [[ "$owner" == "$(id -u)" ]] \
    || pongdang_die "$description must be owned by the deployment user"
}

validate_legacy_env() {
  local file="$1"

  [[ -f "$file" && ! -L "$file" ]] \
    || pongdang_die "legacy secret environment is missing or unsafe"
  require_owned_mode "$file" 600 "legacy secret environment"
  pongdang_require_command python3
  python3 - "$file" <<'PY' \
    || pongdang_die "legacy environment does not describe the isolated pongdang PostgreSQL 15 topology"
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlsplit

path = Path(sys.argv[1])
try:
    content = path.read_text(encoding="utf-8")
except UnicodeError:
    raise SystemExit(1) from None

if "\r" in content or any(
    unicodedata.category(character) == "Cc" and character not in "\t\n"
    for character in content
):
    raise SystemExit(1)

values: dict[str, str] = {}
for line in content.splitlines():
    if not line or line.lstrip().startswith("#"):
        continue
    if "=" not in line:
        raise SystemExit(1)
    key, value = line.split("=", 1)
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key) or key in values:
        raise SystemExit(1)
    values[key] = value

required = ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "DATABASE_URL")
if any(key not in values for key in required):
    raise SystemExit(1)
if values["POSTGRES_DB"] != "pongdang" or values["POSTGRES_USER"] != "pongdang":
    raise SystemExit(1)
password = values["POSTGRES_PASSWORD"]
if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", password):
    raise SystemExit(1)

try:
    parsed = urlsplit(values["DATABASE_URL"])
    port = parsed.port
except ValueError:
    raise SystemExit(1) from None
if (
    parsed.scheme != "postgresql"
    or parsed.hostname != "db"
    or port != 5432
    or parsed.path != "/pongdang"
    or parsed.query
    or parsed.fragment
    or parsed.username is None
    or parsed.password is None
):
    raise SystemExit(1)
userinfo = parsed.netloc.rsplit("@", 1)[0]
if ":" not in userinfo:
    raise SystemExit(1)
encoded_user, encoded_password = userinfo.split(":", 1)
component = re.compile(r"^(?:[A-Za-z0-9._~-]|%[0-9A-Fa-f]{2})+$")
if not component.fullmatch(encoded_user) or not component.fullmatch(encoded_password):
    raise SystemExit(1)
if unquote(encoded_user) != "pongdang" or unquote(encoded_password) != password:
    raise SystemExit(1)
PY
}

load_release() {
  local file="$1"

  pongdang_validate_release_manifest "$file"
  LEGACY_RELEASE_VERSION="$PONGDANG_RELEASE_VERSION"
  LEGACY_RELEASE_COMMIT="$PONGDANG_RELEASE_COMMIT"
  LEGACY_BACKEND_IMAGE="$PONGDANG_BACKEND_IMAGE"
  LEGACY_FRONTEND_IMAGE="$PONGDANG_FRONTEND_IMAGE"
}

legacy_compose_command() {
  local env_file="$1"
  local compose_file="$2"
  local overlay_file="$3"

  LEGACY_COMPOSE=(
    docker compose
    --project-name "$PONGDANG_PROJECT_NAME"
    --env-file "$env_file"
    -f "$compose_file"
    -f "$overlay_file"
  )
}

validate_legacy_compose() {
  local env_file="$1"
  local compose_file="$2"
  local overlay_file="$3"

  require_plain_file "$compose_file" "legacy base Compose file"
  require_plain_file "$overlay_file" "legacy deployment Compose file"
  legacy_compose_command "$env_file" "$compose_file" "$overlay_file"
  if ! BACKEND_IMAGE="$LEGACY_BACKEND_IMAGE" \
      FRONTEND_IMAGE="$LEGACY_FRONTEND_IMAGE" \
      "${LEGACY_COMPOSE[@]}" config --format json \
      | python3 /dev/fd/3 "$PONGDANG_PROJECT_NAME" \
      "$LEGACY_BACKEND_IMAGE" "$LEGACY_FRONTEND_IMAGE" 3<<'PY'
import json
import sys
from urllib.parse import urlsplit

project, backend_image, frontend_image = sys.argv[1:]
config = json.load(sys.stdin)

services = config.get("services", {})
if set(services) != {"db", "backend", "collector", "frontend"}:
    raise SystemExit("legacy service set changed")

db = services["db"]
if db.get("image") != "postgres:15-alpine":
    raise SystemExit("legacy database image is not PostgreSQL 15 Alpine")
environment = db.get("environment", {})
if environment.get("POSTGRES_DB") != "pongdang" or environment.get("POSTGRES_USER") != "pongdang":
    raise SystemExit("legacy database/role changed")
mounts = db.get("volumes", [])
valid_sources = {"postgres_data", f"{project}_postgres_data"}
if not any(
    mount.get("type") == "volume"
    and mount.get("source") in valid_sources
    and mount.get("target") == "/var/lib/postgresql/data"
    for mount in mounts
):
    raise SystemExit("legacy PostgreSQL volume contract changed")
volumes = config.get("volumes", {})
volume = volumes.get("postgres_data")
if not isinstance(volume, dict) or volume.get("external") is True:
    raise SystemExit("legacy PostgreSQL volume must be project-owned")
if volume.get("name") not in (None, f"{project}_postgres_data"):
    raise SystemExit("legacy PostgreSQL volume name changed")

expected_images = {
    "backend": backend_image,
    "collector": backend_image,
    "frontend": frontend_image,
}
for name, expected_image in expected_images.items():
    service = services[name]
    if service.get("build") or service.get("image") != expected_image:
        raise SystemExit(f"legacy release image mismatch for {name}")
    if service.get("pull_policy") != "always":
        raise SystemExit(f"legacy release is not digest-pull-only for {name}")
for name in ("backend", "collector"):
    url = services[name].get("environment", {}).get("DATABASE_URL", "")
    if urlsplit(url).hostname != "db":
        raise SystemExit(f"legacy {name} does not target the private db service")
dependency = services["backend"].get("depends_on", {}).get("db", {})
if dependency.get("condition") != "service_healthy":
    raise SystemExit("legacy backend does not wait for database readiness")
for network in config.get("networks", {}).values():
    if network.get("external") is True or network.get("name") == "cksDB-multtara":
        raise SystemExit("legacy topology unexpectedly reaches cksDB")
PY
  then
    pongdang_die "legacy Compose violates the retained PostgreSQL 15 contract"
  fi
}

inspect_legacy_volume() {
  local volume_name="${PONGDANG_PROJECT_NAME}_${LEGACY_VOLUME_KEY}"
  local details
  local driver
  local project_label
  local volume_label
  local created_at

  details="$(docker volume inspect \
    --format '{{.Driver}}|{{index .Labels "com.docker.compose.project"}}|{{index .Labels "com.docker.compose.volume"}}|{{.CreatedAt}}' \
    "$volume_name" 2>/dev/null)" \
    || pongdang_die "retained legacy Docker volume is missing: $volume_name"
  [[ "$details" != *$'\n'* ]] || pongdang_die "legacy volume inspection returned multiple records"
  IFS='|' read -r driver project_label volume_label created_at <<< "$details"
  [[ "$driver" == "local" ]] || pongdang_die "legacy PostgreSQL volume must use the local driver"
  [[ "$project_label" == "$PONGDANG_PROJECT_NAME" ]] \
    || pongdang_die "legacy PostgreSQL volume Compose project label mismatch"
  [[ "$volume_label" == "$LEGACY_VOLUME_KEY" ]] \
    || pongdang_die "legacy PostgreSQL volume logical label mismatch"
  [[ -n "$created_at" && "$created_at" != *$'\n'* && "$created_at" != *'|'* ]] \
    || pongdang_die "legacy PostgreSQL volume creation identity is unavailable"
  LEGACY_VOLUME_NAME="$volume_name"
  LEGACY_VOLUME_CREATED_AT="$created_at"
}

require_running_legacy_db() {
  local running
  local version

  running="$(BACKEND_IMAGE="$LEGACY_BACKEND_IMAGE" \
    FRONTEND_IMAGE="$LEGACY_FRONTEND_IMAGE" \
    "${LEGACY_COMPOSE[@]}" ps --status running --services)" \
    || pongdang_die "legacy Compose service state is unavailable"
  grep -Fqx "$LEGACY_DB_SERVICE" <<< "$running" \
    || pongdang_die "legacy PostgreSQL db service is not running"
  version="$(BACKEND_IMAGE="$LEGACY_BACKEND_IMAGE" \
    FRONTEND_IMAGE="$LEGACY_FRONTEND_IMAGE" \
    "${LEGACY_COMPOSE[@]}" exec -T "$LEGACY_DB_SERVICE" postgres --version)" \
    || pongdang_die "legacy PostgreSQL server version cannot be inspected"
  [[ "$version" =~ PostgreSQL\)[[:space:]]+${LEGACY_PG_MAJOR}([.]|$) ]] \
    || pongdang_die "running legacy database is not PostgreSQL $LEGACY_PG_MAJOR"
}

write_bundle_metadata() {
  local destination="$1"

  {
    printf 'FORMAT=%s\n' "$BUNDLE_FORMAT"
    printf 'TARGET=%s\n' "$PONGDANG_TARGET"
    printf 'DEPLOY_USER=%s\n' "$PONGDANG_DEPLOY_USER"
    printf 'PROJECT_NAME=%s\n' "$PONGDANG_PROJECT_NAME"
    printf 'DATABASE=%s\n' "$LEGACY_DB_NAME"
    printf 'ROLE=%s\n' "$LEGACY_DB_ROLE"
    printf 'POSTGRES_MAJOR=%s\n' "$LEGACY_PG_MAJOR"
    printf 'VOLUME_NAME=%s\n' "$LEGACY_VOLUME_NAME"
    printf 'VOLUME_CREATED_AT=%s\n' "$LEGACY_VOLUME_CREATED_AT"
    printf 'RELEASE_VERSION=%s\n' "$LEGACY_RELEASE_VERSION"
    printf 'RELEASE_COMMIT=%s\n' "$LEGACY_RELEASE_COMMIT"
    printf 'DATA_CONTRACT=%s\n' "$DATA_CONFIRMATION"
  } > "$destination"
  chmod 0400 "$destination"
}

validate_bundle_metadata() {
  local file="$1"

  python3 - "$file" <<'PY' \
    || pongdang_die "rollback bundle metadata has unknown, missing, duplicate, or unsafe fields"
import re
import sys
from pathlib import Path

expected = {
    "FORMAT", "TARGET", "DEPLOY_USER", "PROJECT_NAME", "DATABASE", "ROLE",
    "POSTGRES_MAJOR", "VOLUME_NAME", "VOLUME_CREATED_AT", "RELEASE_VERSION",
    "RELEASE_COMMIT", "DATA_CONTRACT",
}
values: dict[str, str] = {}
try:
    lines = Path(sys.argv[1]).read_text(encoding="ascii").splitlines()
except UnicodeError:
    raise SystemExit(1) from None
for line in lines:
    if "=" not in line:
        raise SystemExit(1)
    key, value = line.split("=", 1)
    if key not in expected or key in values or not value or any(ord(c) < 32 or ord(c) > 126 for c in value):
        raise SystemExit(1)
    values[key] = value
if set(values) != expected:
    raise SystemExit(1)
if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+(?:[.-][0-9A-Za-z.-]+)?", values["RELEASE_VERSION"]):
    raise SystemExit(1)
if not re.fullmatch(r"[0-9a-f]{40}", values["RELEASE_COMMIT"]):
    raise SystemExit(1)
PY

  [[ "$(pongdang_marker_value "$file" FORMAT)" == "$BUNDLE_FORMAT" ]] \
    || pongdang_die "unsupported rollback bundle format"
  [[ "$(pongdang_marker_value "$file" TARGET)" == "$PONGDANG_TARGET" ]] \
    || pongdang_die "rollback bundle target mismatch"
  [[ "$(pongdang_marker_value "$file" DEPLOY_USER)" == "$PONGDANG_DEPLOY_USER" ]] \
    || pongdang_die "rollback bundle deployment user mismatch"
  [[ "$(pongdang_marker_value "$file" PROJECT_NAME)" == "$PONGDANG_PROJECT_NAME" ]] \
    || pongdang_die "rollback bundle Compose project mismatch"
  [[ "$(pongdang_marker_value "$file" DATABASE)" == "$LEGACY_DB_NAME" ]] \
    || pongdang_die "rollback bundle database mismatch"
  [[ "$(pongdang_marker_value "$file" ROLE)" == "$LEGACY_DB_ROLE" ]] \
    || pongdang_die "rollback bundle role mismatch"
  [[ "$(pongdang_marker_value "$file" POSTGRES_MAJOR)" == "$LEGACY_PG_MAJOR" ]] \
    || pongdang_die "rollback bundle PostgreSQL major mismatch"
  [[ "$(pongdang_marker_value "$file" DATA_CONTRACT)" == "$DATA_CONFIRMATION" ]] \
    || pongdang_die "rollback bundle data contract mismatch"
  LEGACY_VOLUME_NAME="$(pongdang_marker_value "$file" VOLUME_NAME)"
  LEGACY_VOLUME_CREATED_AT="$(pongdang_marker_value "$file" VOLUME_CREATED_AT)"
  LEGACY_RELEASE_VERSION="$(pongdang_marker_value "$file" RELEASE_VERSION)"
  LEGACY_RELEASE_COMMIT="$(pongdang_marker_value "$file" RELEASE_COMMIT)"
  [[ "$LEGACY_VOLUME_NAME" == "${PONGDANG_PROJECT_NAME}_${LEGACY_VOLUME_KEY}" ]] \
    || pongdang_die "rollback bundle volume name mismatch"
}

validate_bundle() {
  local bundle="$1"
  local canonical
  local actual_names
  local expected_names
  local file
  local script
  local metadata_release_version
  local metadata_release_commit

  [[ -d "$bundle" && ! -L "$bundle" ]] || pongdang_die "rollback bundle is missing or unsafe"
  canonical="$(cd "$bundle" && pwd -P)"
  [[ "$canonical" == "$PONGDANG_TARGET/state/$BUNDLE_NAME" ]] \
    || pongdang_die "rollback bundle escaped its fixed state path"
  require_owned_mode "$bundle" 700 "rollback bundle directory"

  expected_names=$'.env\nSHA256SUMS\nSHA256SUMS.sha256\nbundle.env\ncurrent.release.env\ncurrent.release.env.sha256\ndocker-compose.deploy.yml\ndocker-compose.yml\nscripts'
  actual_names="$(find "$bundle" -mindepth 1 -maxdepth 1 -printf '%f\n' | LC_ALL=C sort)"
  [[ "$actual_names" == "$expected_names" ]] \
    || pongdang_die "rollback bundle contains missing or unexpected files"

  for file in .env SHA256SUMS SHA256SUMS.sha256 bundle.env current.release.env \
    current.release.env.sha256 docker-compose.deploy.yml docker-compose.yml; do
    [[ -f "$bundle/$file" && ! -L "$bundle/$file" ]] \
      || pongdang_die "rollback bundle file is missing or unsafe: $file"
    if [[ "$file" == ".env" ]]; then
      require_owned_mode "$bundle/$file" 600 "rollback bundle secret environment"
    else
      require_owned_mode "$bundle/$file" 400 "rollback bundle file $file"
    fi
  done
  [[ -d "$bundle/scripts" && ! -L "$bundle/scripts" ]] \
    || pongdang_die "rollback bundle forensic scripts directory is missing or unsafe"
  require_owned_mode "$bundle/scripts" 700 "rollback bundle forensic scripts directory"
  expected_names="$(printf '%s\n' "${LEGACY_FORENSIC_SCRIPTS[@]}" | LC_ALL=C sort)"
  actual_names="$(find "$bundle/scripts" -mindepth 1 -maxdepth 1 -printf '%f\n' | LC_ALL=C sort)"
  [[ "$actual_names" == "$expected_names" ]] \
    || pongdang_die "rollback bundle forensic scripts are missing or unexpected"
  for script in "${LEGACY_FORENSIC_SCRIPTS[@]}"; do
    [[ -f "$bundle/scripts/$script" && ! -L "$bundle/scripts/$script" ]] \
      || pongdang_die "rollback bundle forensic script is missing or unsafe: $script"
    require_owned_mode "$bundle/scripts/$script" 400 "rollback bundle forensic script $script"
  done

  python3 - "$bundle/$BUNDLE_MANIFEST_CHECKSUM" <<'PY' \
    || pongdang_die "rollback bundle manifest checksum sidecar is malformed"
import re
import sys
from pathlib import Path

lines = Path(sys.argv[1]).read_text(encoding="ascii").splitlines()
if len(lines) != 1 or not re.fullmatch(r"[0-9a-f]{64}  SHA256SUMS", lines[0]):
    raise SystemExit(1)
PY
  (cd "$bundle" && sha256sum --check --strict "$BUNDLE_MANIFEST_CHECKSUM" >/dev/null) \
    || pongdang_die "rollback bundle manifest checksum verification failed"

  python3 - "$bundle/$BUNDLE_MANIFEST" <<'PY' \
    || pongdang_die "rollback bundle checksum manifest is malformed"
import re
import sys
from pathlib import Path

expected = {
    ".env", "bundle.env", "current.release.env", "current.release.env.sha256",
    "docker-compose.deploy.yml", "docker-compose.yml",
    "scripts/deploy-common.sh", "scripts/pi-deploy.sh",
    "scripts/postgres-backup.sh", "scripts/postgres-prune-backups.sh",
    "scripts/postgres-restore.sh",
}
seen: set[str] = set()
for line in Path(sys.argv[1]).read_text(encoding="ascii").splitlines():
    match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9._/-]+)", line)
    if not match or match.group(2) not in expected or match.group(2) in seen:
        raise SystemExit(1)
    seen.add(match.group(2))
if seen != expected:
    raise SystemExit(1)
PY
  (cd "$bundle" && sha256sum --check --strict "$BUNDLE_MANIFEST" >/dev/null) \
    || pongdang_die "rollback bundle checksum verification failed"
  ROLLBACK_BUNDLE_MANIFEST_SHA256="$(sha256sum "$bundle/$BUNDLE_MANIFEST" | awk '{print $1}')"

  validate_bundle_metadata "$bundle/bundle.env"
  metadata_release_version="$LEGACY_RELEASE_VERSION"
  metadata_release_commit="$LEGACY_RELEASE_COMMIT"
  load_release "$bundle/current.release.env"
  pongdang_verify_release_checksum "$bundle/current.release.env"
  [[ "$PONGDANG_RELEASE_VERSION" == "$metadata_release_version" \
      && "$PONGDANG_RELEASE_COMMIT" == "$metadata_release_commit" ]] \
    || pongdang_die "rollback release and bundle metadata disagree"
  validate_legacy_env "$bundle/.env"
  validate_legacy_compose \
    "$bundle/.env" \
    "$bundle/docker-compose.yml" \
    "$bundle/docker-compose.deploy.yml"
}

stage_bundle() {
  local bundle="$PONGDANG_TARGET/state/$BUNDLE_NAME"
  local active="$PONGDANG_TARGET/state/$BUNDLE_NAME.active"
  local staging
  local current="$PONGDANG_TARGET/state/current.release.env"
  local stored_release
  local script

  [[ ! -e "$bundle" && ! -L "$bundle" ]] \
    || pongdang_die "rollback bundle already exists and will never be overwritten: $bundle"
  [[ ! -e "$active" && ! -L "$active" ]] \
    || pongdang_die "pre-cksDB standalone rollback is already active"
  for file in "$PONGDANG_TARGET/docker-compose.yml" \
    "$PONGDANG_TARGET/docker-compose.deploy.yml"; do
    require_plain_file "$file" "legacy deployment configuration"
  done
  for script in "${LEGACY_FORENSIC_SCRIPTS[@]}"; do
    require_plain_file "$PONGDANG_TARGET/scripts/$script" "installed legacy operation script"
  done
  validate_legacy_env "$PONGDANG_TARGET/.env"
  load_release "$current"
  stored_release="$PONGDANG_TARGET/releases/$LEGACY_RELEASE_VERSION.env"
  require_plain_file "$stored_release" "stored legacy release manifest"
  pongdang_verify_release_checksum "$stored_release"
  cmp -s "$current" "$stored_release" \
    || pongdang_die "current release state does not match its immutable stored manifest"
  load_release "$current"
  validate_legacy_compose \
    "$PONGDANG_TARGET/.env" \
    "$PONGDANG_TARGET/docker-compose.yml" \
    "$PONGDANG_TARGET/docker-compose.deploy.yml"
  inspect_legacy_volume
  require_running_legacy_db

  staging="$(mktemp -d "$PONGDANG_TARGET/state/.$BUNDLE_NAME.XXXXXX")"
  chmod 0700 "$staging"
  cleanup_stage() {
    if [[ -n "${staging:-}" && -d "$staging" && ! -L "$staging" ]]; then
      case "$staging" in
        "$PONGDANG_TARGET/state/.$BUNDLE_NAME."*) find "$staging" -depth -delete ;;
        *) echo "refusing unexpected rollback staging cleanup: $staging" >&2 ;;
      esac
    fi
  }
  trap cleanup_stage EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM

  install -m 0400 "$PONGDANG_TARGET/docker-compose.yml" "$staging/docker-compose.yml"
  install -m 0400 "$PONGDANG_TARGET/docker-compose.deploy.yml" "$staging/docker-compose.deploy.yml"
  install -m 0600 "$PONGDANG_TARGET/.env" "$staging/.env"
  install -m 0400 "$current" "$staging/current.release.env"
  install -d -m 0700 "$staging/scripts"
  for script in "${LEGACY_FORENSIC_SCRIPTS[@]}"; do
    install -m 0400 "$PONGDANG_TARGET/scripts/$script" "$staging/scripts/$script"
  done
  (
    cd "$staging"
    sha256sum current.release.env > current.release.env.sha256
  )
  chmod 0400 "$staging/current.release.env.sha256"
  write_bundle_metadata "$staging/bundle.env"
  (
    cd "$staging"
    sha256sum \
      .env \
      bundle.env \
      current.release.env \
      current.release.env.sha256 \
      docker-compose.deploy.yml \
      docker-compose.yml \
      scripts/deploy-common.sh \
      scripts/pi-deploy.sh \
      scripts/postgres-backup.sh \
      scripts/postgres-prune-backups.sh \
      scripts/postgres-restore.sh > "$BUNDLE_MANIFEST"
    sha256sum "$BUNDLE_MANIFEST" > "$BUNDLE_MANIFEST_CHECKSUM"
  )
  chmod 0400 "$staging/$BUNDLE_MANIFEST" "$staging/$BUNDLE_MANIFEST_CHECKSUM"

  [[ ! -e "$bundle" && ! -L "$bundle" ]] \
    || pongdang_die "rollback bundle appeared while staging; refusing overwrite"
  mv -T "$staging" "$bundle"
  staging=""
  trap - EXIT INT TERM
  validate_bundle "$bundle"
  echo "staged immutable pre-cksDB rollback bundle: $bundle"
  echo "data boundary: restore is forbidden after any cksDB write"
}

verify_bundle() {
  local bundle="$PONGDANG_TARGET/state/$BUNDLE_NAME"
  local expected_volume_created_at

  validate_bundle "$bundle"
  expected_volume_created_at="$LEGACY_VOLUME_CREATED_AT"
  inspect_legacy_volume
  [[ "$LEGACY_VOLUME_CREATED_AT" == "$expected_volume_created_at" ]] \
    || pongdang_die "retained PostgreSQL volume was replaced after the bundle was staged"
  printf 'verified immutable pre-cksDB rollback bundle: %s\n' "$bundle"
}

write_fingerprint_sql() {
  cat <<'SQL'
\set ON_ERROR_STOP on
\pset tuples_only on
\pset format unaligned
SET client_encoding = 'UTF8';
SET search_path = pg_catalog;
SET extra_float_digits = 3;
SELECT (count(*) = 0)::text AS isolated
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid()
\gset
\if :isolated
\else
\echo 'another database session is active; fingerprint refused'
\quit 3
\endif
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
COPY (
  SELECT
    'schema',
    namespace.nspname,
    CASE pg_get_userbyid(namespace.nspowner)
      WHEN 'pg_database_owner' THEN pg_get_userbyid(database_record.datdba)
      ELSE pg_get_userbyid(namespace.nspowner)
    END
  FROM pg_namespace AS namespace
  CROSS JOIN pg_database AS database_record
  WHERE namespace.nspname <> 'information_schema'
    AND namespace.nspname !~ '^pg_'
    AND database_record.datname = current_database()
  ORDER BY namespace.nspname
) TO STDOUT WITH (FORMAT csv, FORCE_QUOTE *);
COPY (
  SELECT
    'relation', namespace.nspname, relation.relname, relation.relkind,
    relation.relpersistence, pg_get_userbyid(relation.relowner)
  FROM pg_class AS relation
  JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
  WHERE namespace.nspname <> 'information_schema'
    AND namespace.nspname !~ '^pg_'
    AND relation.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')
  ORDER BY namespace.nspname, relation.relname
) TO STDOUT WITH (FORMAT csv, FORCE_QUOTE *);
COPY (
  SELECT
    'column', namespace.nspname, relation.relname,
    row_number() OVER (
      PARTITION BY attribute.attrelid
      ORDER BY attribute.attnum
    ),
    attribute.attname, format_type(attribute.atttypid, attribute.atttypmod),
    attribute.attnotnull, attribute.attidentity, attribute.attgenerated,
    COALESCE(pg_get_expr(default_value.adbin, default_value.adrelid, true), ''),
    CASE
      WHEN attribute.attcollation = 0 THEN ''
      ELSE quote_ident(collation_namespace.nspname) || '.' || quote_ident(collation_record.collname)
    END
  FROM pg_attribute AS attribute
  JOIN pg_class AS relation ON relation.oid = attribute.attrelid
  JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
  LEFT JOIN pg_attrdef AS default_value
    ON default_value.adrelid = attribute.attrelid
   AND default_value.adnum = attribute.attnum
  LEFT JOIN pg_collation AS collation_record
    ON collation_record.oid = attribute.attcollation
  LEFT JOIN pg_namespace AS collation_namespace
    ON collation_namespace.oid = collation_record.collnamespace
  WHERE namespace.nspname <> 'information_schema'
    AND namespace.nspname !~ '^pg_'
    AND relation.relkind IN ('r', 'p', 'v', 'm', 'f')
    AND attribute.attnum > 0
    AND NOT attribute.attisdropped
  ORDER BY namespace.nspname, relation.relname, attribute.attnum
) TO STDOUT WITH (FORMAT csv, FORCE_QUOTE *);
COPY (
  SELECT
    'constraint', namespace.nspname, relation.relname, constraint_record.conname,
    constraint_record.contype, constraint_record.condeferrable,
    constraint_record.condeferred, constraint_record.convalidated,
    replace(
      replace(
        pg_get_constraintdef(constraint_record.oid, true),
        '::character varying::text',
        '::character varying'
      ),
      ']::text[]',
      ']'
    )
  FROM pg_constraint AS constraint_record
  JOIN pg_class AS relation ON relation.oid = constraint_record.conrelid
  JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
  WHERE namespace.nspname <> 'information_schema'
    AND namespace.nspname !~ '^pg_'
  ORDER BY namespace.nspname, relation.relname, constraint_record.conname
) TO STDOUT WITH (FORMAT csv, FORCE_QUOTE *);
COPY (
  SELECT
    'index', namespace.nspname, table_record.relname, index_record.relname,
    index_metadata.indisunique, index_metadata.indisprimary,
    index_metadata.indisvalid, index_metadata.indisready,
    pg_get_indexdef(index_metadata.indexrelid, 0, true)
  FROM pg_index AS index_metadata
  JOIN pg_class AS table_record ON table_record.oid = index_metadata.indrelid
  JOIN pg_class AS index_record ON index_record.oid = index_metadata.indexrelid
  JOIN pg_namespace AS namespace ON namespace.oid = table_record.relnamespace
  WHERE namespace.nspname <> 'information_schema'
    AND namespace.nspname !~ '^pg_'
  ORDER BY namespace.nspname, table_record.relname, index_record.relname
) TO STDOUT WITH (FORMAT csv, FORCE_QUOTE *);
COPY (
  SELECT
    'sequence', schemaname, sequencename, sequenceowner, data_type,
    start_value, min_value, max_value, increment_by, cycle, cache_size,
    COALESCE(last_value::text, '')
  FROM pg_sequences
  WHERE schemaname <> 'information_schema'
    AND schemaname !~ '^pg_'
  ORDER BY schemaname, sequencename
) TO STDOUT WITH (FORMAT csv, FORCE_QUOTE *);
COPY (
  SELECT
    'view', namespace.nspname, relation.relname,
    pg_get_viewdef(relation.oid, true)
  FROM pg_class AS relation
  JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
  WHERE namespace.nspname <> 'information_schema'
    AND namespace.nspname !~ '^pg_'
    AND relation.relkind IN ('v', 'm')
  ORDER BY namespace.nspname, relation.relname
) TO STDOUT WITH (FORMAT csv, FORCE_QUOTE *);
COPY (
  SELECT
    'trigger', namespace.nspname, relation.relname, trigger_record.tgname,
    pg_get_triggerdef(trigger_record.oid, true)
  FROM pg_trigger AS trigger_record
  JOIN pg_class AS relation ON relation.oid = trigger_record.tgrelid
  JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
  WHERE namespace.nspname <> 'information_schema'
    AND namespace.nspname !~ '^pg_'
    AND NOT trigger_record.tgisinternal
  ORDER BY namespace.nspname, relation.relname, trigger_record.tgname
) TO STDOUT WITH (FORMAT csv, FORCE_QUOTE *);
COPY (
  SELECT
    'enum', namespace.nspname, type_record.typname,
    enum_record.enumsortorder, enum_record.enumlabel
  FROM pg_enum AS enum_record
  JOIN pg_type AS type_record ON type_record.oid = enum_record.enumtypid
  JOIN pg_namespace AS namespace ON namespace.oid = type_record.typnamespace
  WHERE namespace.nspname <> 'information_schema'
    AND namespace.nspname !~ '^pg_'
  ORDER BY namespace.nspname, type_record.typname, enum_record.enumsortorder
) TO STDOUT WITH (FORMAT csv, FORCE_QUOTE *);
SELECT format(
  'COPY (SELECT %L, %L, %L, count(*)::text FROM %I.%I) TO STDOUT WITH (FORMAT csv, FORCE_QUOTE *);',
  'row-count', namespace.nspname, relation.relname,
  namespace.nspname, relation.relname
)
FROM pg_class AS relation
JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
WHERE namespace.nspname <> 'information_schema'
  AND namespace.nspname !~ '^pg_'
  AND relation.relkind IN ('r', 'p')
ORDER BY namespace.nspname, relation.relname
\gexec
COMMIT;
SELECT (count(*) = 0)::text AS isolated
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid()
\gset
\if :isolated
\else
\echo 'another database session appeared during fingerprint; fingerprint refused'
\quit 3
\endif
SQL
}

fingerprint_source_database() {
  local sql_file="$1"
  local output_file="$2"

  LC_ALL=C "${LEGACY_COMPOSE[@]}" exec -T "$LEGACY_DB_SERVICE" \
    psql \
      --no-psqlrc \
      --no-password \
      --quiet \
      --username "$LEGACY_DB_ROLE" \
      --dbname "$LEGACY_DB_NAME" < "$sql_file" > "$output_file" \
    || pongdang_die "source PostgreSQL fingerprint failed"
  [[ -s "$output_file" ]] || pongdang_die "source PostgreSQL fingerprint is empty"
}

cksdb_runtime_image() {
  local details
  details="$(docker inspect --format '{{.Image}}|{{.State.Status}}' cksDB 2>/dev/null)" \
    || pongdang_die "cksDB container cannot be inspected"
  [[ "$details" != *$'\n'* ]] || pongdang_die "cksDB inspection returned multiple records"
  IFS='|' read -r CKSDB_RUNTIME_IMAGE cksdb_status <<< "$details"
  [[ "$CKSDB_RUNTIME_IMAGE" =~ ^sha256:[0-9a-f]{64}$ ]] \
    || pongdang_die "cksDB runtime image is not content-addressed"
  [[ "$cksdb_status" == "running" ]] || pongdang_die "cksDB container is not running"
}

target_psql() {
  PGPASSWORD="$PONGDANG_POSTGRES_PASSWORD" docker run \
    --rm \
    --pull never \
    --network cksDB-multtara \
    --read-only \
    --cap-drop ALL \
    --security-opt no-new-privileges \
    --pids-limit 64 \
    --memory 256m \
    --tmpfs /tmp:rw,noexec,nosuid,nodev,size=16m \
    --env PGPASSWORD \
    "$CKSDB_RUNTIME_IMAGE" \
    psql \
      --no-psqlrc \
      --no-password \
      --host cksDB \
      --port 5432 \
      --username "$PONGDANG_POSTGRES_USER" \
      --dbname "$PONGDANG_POSTGRES_DB" \
      "$@"
}

fingerprint_target_database() {
  local sql_file="$1"
  local output_file="$2"
  local server_version

  server_version="$(target_psql --quiet --tuples-only --no-align \
    --command 'SHOW server_version_num')" \
    || pongdang_die "target PostgreSQL version cannot be inspected"
  [[ "$server_version" =~ ^16[0-9]{4}$ ]] \
    || pongdang_die "target cksDB database is not PostgreSQL 16"
  LC_ALL=C target_psql --quiet < "$sql_file" > "$output_file" \
    || pongdang_die "target cksDB PostgreSQL fingerprint failed"
  [[ -s "$output_file" ]] || pongdang_die "target cksDB PostgreSQL fingerprint is empty"
}

create_final_source_dump() {
  local backup_dir="$PONGDANG_TARGET/backups/postgres"
  local timestamp

  [[ -d "$backup_dir" && ! -L "$backup_dir" ]] \
    || pongdang_die "backup directory is missing or unsafe"
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)-$$"
  CUTOVER_FINAL_DUMP="$backup_dir/pongdang-$timestamp.dump"
  CUTOVER_FINAL_DUMP_PARTIAL="$backup_dir/.pongdang-$timestamp.$$.partial"
  CUTOVER_FINAL_DUMP_CHECKSUM="$CUTOVER_FINAL_DUMP.sha256"
  [[ ! -e "$CUTOVER_FINAL_DUMP_PARTIAL" && ! -L "$CUTOVER_FINAL_DUMP_PARTIAL" \
      && ! -e "$CUTOVER_FINAL_DUMP" && ! -L "$CUTOVER_FINAL_DUMP" \
      && ! -e "$CUTOVER_FINAL_DUMP_CHECKSUM" && ! -L "$CUTOVER_FINAL_DUMP_CHECKSUM" ]] \
    || pongdang_die "cutover final dump path collision"
  LC_ALL=C "${LEGACY_COMPOSE[@]}" exec -T "$LEGACY_DB_SERVICE" \
    pg_dump \
      --username "$LEGACY_DB_ROLE" \
      --dbname "$LEGACY_DB_NAME" \
      --format=custom \
      --compress=6 \
      --no-owner \
      --no-privileges > "$CUTOVER_FINAL_DUMP_PARTIAL" \
    || pongdang_die "final PostgreSQL 15 source dump failed"
  [[ -s "$CUTOVER_FINAL_DUMP_PARTIAL" ]] || pongdang_die "final PostgreSQL 15 source dump is empty"
  LC_ALL=C "${LEGACY_COMPOSE[@]}" exec -T "$LEGACY_DB_SERVICE" \
    pg_restore --list < "$CUTOVER_FINAL_DUMP_PARTIAL" >/dev/null \
    || pongdang_die "source PostgreSQL 15 pg_restore rejected the final dump"
  chmod 0600 "$CUTOVER_FINAL_DUMP_PARTIAL"
  mv "$CUTOVER_FINAL_DUMP_PARTIAL" "$CUTOVER_FINAL_DUMP"
  CUTOVER_FINAL_DUMP_PARTIAL=""
  (
    cd "$backup_dir"
    sha256sum "${CUTOVER_FINAL_DUMP##*/}" > "${CUTOVER_FINAL_DUMP_CHECKSUM##*/}"
  )
  chmod 0600 "$CUTOVER_FINAL_DUMP_CHECKSUM"
  CUTOVER_FINAL_DUMP_SHA256="$(sha256sum "$CUTOVER_FINAL_DUMP" | awk '{print $1}')"
}

publish_cutover_marker() {
  local marker="$PONGDANG_TARGET/state/$PONGDANG_CUTOVER_MARKER_NAME"
  local temporary
  local created_at

  [[ ! -e "$marker" && ! -L "$marker" ]] \
    || pongdang_die "cksDB cutover-ready marker already exists"
  created_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  temporary="$(mktemp "$PONGDANG_TARGET/state/.$PONGDANG_CUTOVER_MARKER_NAME.XXXXXX")"
  {
    printf 'FORMAT=%s\n' "$PONGDANG_CUTOVER_MARKER_FORMAT"
    printf 'TARGET=%s\n' "$PONGDANG_TARGET"
    printf 'DEPLOY_USER=%s\n' "$PONGDANG_DEPLOY_USER"
    printf 'PROJECT_NAME=%s\n' "$PONGDANG_PROJECT_NAME"
    printf 'DATABASE=pongdang\n'
    printf 'SOURCE_POSTGRES_MAJOR=15\n'
    printf 'TARGET_POSTGRES_MAJOR=16\n'
    printf 'FINGERPRINT_FORMAT=%s\n' "$PONGDANG_DB_FINGERPRINT_FORMAT"
    printf 'FINAL_DUMP=%s\n' "${CUTOVER_FINAL_DUMP##*/}"
    printf 'FINAL_DUMP_SHA256=%s\n' "$CUTOVER_FINAL_DUMP_SHA256"
    printf 'SOURCE_FINGERPRINT_SHA256=%s\n' "$CUTOVER_SOURCE_FINGERPRINT_SHA256"
    printf 'TARGET_FINGERPRINT_SHA256=%s\n' "$CUTOVER_TARGET_FINGERPRINT_SHA256"
    printf 'CKSDB_REVISION=%s\n' "$PONGDANG_CKSDB_REVISION"
    printf 'SHARED_DB_TOOL_SHA256=%s\n' "$PONGDANG_SHARED_DB_TOOL_SHA256"
    printf 'ROLLBACK_BUNDLE_MANIFEST_SHA256=%s\n' "$ROLLBACK_BUNDLE_MANIFEST_SHA256"
    printf 'CREATED_AT=%s\n' "$created_at"
  } > "$temporary"
  chmod 0400 "$temporary"
  if ! ln "$temporary" "$marker"; then
    find "$temporary" -delete
    pongdang_die "cannot publish cksDB cutover-ready marker without overwrite"
  fi
  find "$temporary" -delete
}

cutover_to_cksdb() {
  local bundle="$PONGDANG_TARGET/state/$BUNDLE_NAME"
  local marker="$PONGDANG_TARGET/state/$PONGDANG_CUTOVER_MARKER_NAME"
  local expected_volume_created_at
  local running_services
  local work_dir
  local fingerprint_sql
  local source_fingerprint
  local target_fingerprint
  local finalize_output
  local expected_finalize_output
  local cutover_succeeded=0

  [[ "$CONFIRMATION" == "$CUTOVER_CONFIRMATION" ]] \
    || pongdang_die "cutover requires --confirm $CUTOVER_CONFIRMATION"
  if [[ -e "$marker" || -L "$marker" ]]; then
    pongdang_validate_cutover_ready
    echo "cksDB cutover-ready marker is already valid: $marker"
    return 0
  fi
  validate_bundle "$bundle"
  expected_volume_created_at="$LEGACY_VOLUME_CREATED_AT"
  inspect_legacy_volume
  [[ "$LEGACY_VOLUME_CREATED_AT" == "$expected_volume_created_at" ]] \
    || pongdang_die "retained PostgreSQL volume was replaced after the bundle was staged"
  require_running_legacy_db
  pongdang_validate_secret_env
  "$PONGDANG_SHARED_DB_TOOL" ready \
    || pongdang_die "target cksDB database is not credential-ready"
  cksdb_runtime_image

  work_dir="$(mktemp -d "$PONGDANG_TARGET/state/.cksdb-cutover.XXXXXX")"
  chmod 0700 "$work_dir"
  fingerprint_sql="$work_dir/fingerprint.sql"
  source_fingerprint="$work_dir/source.fingerprint"
  target_fingerprint="$work_dir/target.fingerprint"
  write_fingerprint_sql > "$fingerprint_sql"
  chmod 0600 "$fingerprint_sql"
  cleanup_cutover() {
    if [[ -n "${CUTOVER_FINAL_DUMP_PARTIAL:-}" \
        && -e "$CUTOVER_FINAL_DUMP_PARTIAL" ]]; then
      case "$CUTOVER_FINAL_DUMP_PARTIAL" in
        "$PONGDANG_TARGET/backups/postgres/".pongdang-*.partial)
          find "$CUTOVER_FINAL_DUMP_PARTIAL" -delete
          ;;
        *) echo "refusing unexpected cutover partial cleanup: $CUTOVER_FINAL_DUMP_PARTIAL" >&2 ;;
      esac
    fi
    if [[ -d "$work_dir" && ! -L "$work_dir" ]]; then
      case "$work_dir" in
        "$PONGDANG_TARGET/state/.cksdb-cutover."*) find "$work_dir" -depth -delete ;;
        *) echo "refusing unexpected cutover work cleanup: $work_dir" >&2 ;;
      esac
    fi
    if [[ "$cutover_succeeded" -ne 1 ]]; then
      BACKEND_IMAGE="$LEGACY_BACKEND_IMAGE" \
        FRONTEND_IMAGE="$LEGACY_FRONTEND_IMAGE" \
        "${LEGACY_COMPOSE[@]}" stop collector backend >/dev/null 2>&1 || true
      echo "cutover did not complete; Multtara backend and collector remain stopped" >&2
    fi
  }
  trap cleanup_cutover EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM

  BACKEND_IMAGE="$LEGACY_BACKEND_IMAGE" \
    FRONTEND_IMAGE="$LEGACY_FRONTEND_IMAGE" \
    "${LEGACY_COMPOSE[@]}" stop collector backend
  running_services="$(BACKEND_IMAGE="$LEGACY_BACKEND_IMAGE" \
    FRONTEND_IMAGE="$LEGACY_FRONTEND_IMAGE" \
    "${LEGACY_COMPOSE[@]}" ps --status running --services)" \
    || pongdang_die "legacy service state cannot be verified after writer stop"
  if grep -Eq '^(backend|collector)$' <<< "$running_services"; then
    pongdang_die "legacy application writers are still running"
  fi

  create_final_source_dump
  "$PONGDANG_SHARED_DB_TOOL" verify --backup "$CUTOVER_FINAL_DUMP" \
    || pongdang_die "target PostgreSQL 16 rejected the final source archive"
  "$PONGDANG_SHARED_DB_TOOL" restore \
    --backup "$CUTOVER_FINAL_DUMP" \
    --confirm RESTORE:multtara:pongdang \
    || pongdang_die "final source archive restore into cksDB failed"

  fingerprint_source_database "$fingerprint_sql" "$source_fingerprint"
  fingerprint_target_database "$fingerprint_sql" "$target_fingerprint"
  CUTOVER_SOURCE_FINGERPRINT_SHA256="$(sha256sum "$source_fingerprint" | awk '{print $1}')"
  CUTOVER_TARGET_FINGERPRINT_SHA256="$(sha256sum "$target_fingerprint" | awk '{print $1}')"
  [[ "$CUTOVER_SOURCE_FINGERPRINT_SHA256" == "$CUTOVER_TARGET_FINGERPRINT_SHA256" ]] \
    || pongdang_die "source and target database fingerprints differ; cksDB was not finalized"
  cmp -s "$source_fingerprint" "$target_fingerprint" \
    || pongdang_die "source and target database evidence differs despite its digest"

  expected_finalize_output='{"protocol":"cksdb.multtara-db","version":1,"action":"finalize","database":"pongdang","removed":"pongdang_previous","ready":true}'
  finalize_output="$("$PONGDANG_SHARED_DB_TOOL" finalize \
    --confirm FINALIZE:multtara:pongdang_previous)" \
    || pongdang_die "cksDB finalize failed; pongdang_previous must be reviewed"
  [[ "$finalize_output" == "$expected_finalize_output" ]] \
    || pongdang_die "cksDB finalize returned an incompatible result"
  publish_cutover_marker
  pongdang_validate_cutover_ready
  cutover_succeeded=1
  trap - EXIT INT TERM
  find "$work_dir" -depth -delete
  echo "cksDB cutover evidence verified and marker published: $marker"
  echo "Multtara backend and collector remain stopped; run the gated digest deployment next"
}

validate_current_shared_compose() {
  local current_release="$PONGDANG_TARGET/state/current.release.env"

  require_plain_file "$PONGDANG_TARGET/docker-compose.yml" "current base Compose file"
  require_plain_file "$PONGDANG_TARGET/docker-compose.deploy.yml" "current deployment Compose file"
  pongdang_validate_release_manifest "$current_release"
  export BACKEND_IMAGE="$PONGDANG_BACKEND_IMAGE"
  export FRONTEND_IMAGE="$PONGDANG_FRONTEND_IMAGE"
  CURRENT_COMPOSE=(
    docker compose
    --project-name "$PONGDANG_PROJECT_NAME"
    --env-file "$PONGDANG_ENV_FILE"
    -f "$PONGDANG_TARGET/docker-compose.yml"
    -f "$PONGDANG_TARGET/docker-compose.deploy.yml"
  )
  if ! "${CURRENT_COMPOSE[@]}" config --format json \
      | python3 /dev/fd/3 "$PONGDANG_BACKEND_IMAGE" "$PONGDANG_FRONTEND_IMAGE" 3<<'PY'
import json
import sys

config = json.load(sys.stdin)
backend_image, frontend_image = sys.argv[1:]
services = config.get("services", {})
if set(services) != {"backend", "collector", "frontend"} or "db" in services:
    raise SystemExit(1)
expected_images = {
    "backend": backend_image,
    "collector": backend_image,
    "frontend": frontend_image,
}
for name, image in expected_images.items():
    if services[name].get("image") != image or services[name].get("pull_policy") != "always":
        raise SystemExit(1)
for name in ("backend", "collector"):
    if set(services[name].get("networks", {})) != {"default", "multtara-db"}:
        raise SystemExit(1)
if set(services["frontend"].get("networks", {})) != {"default"}:
    raise SystemExit(1)
network = config.get("networks", {}).get("multtara-db", {})
if network.get("name") != "cksDB-multtara" or network.get("external") is not True:
    raise SystemExit(1)
PY
  then
    pongdang_die "current deployment is not the expected isolated cksDB topology"
  fi
}

publish_active_marker() {
  local backup_basename="$1"
  local active="$PONGDANG_TARGET/state/$BUNDLE_NAME.active"
  local temporary

  [[ ! -e "$active" && ! -L "$active" ]] \
    || pongdang_die "pre-cksDB standalone rollback active marker already exists"
  temporary="$(mktemp "$PONGDANG_TARGET/state/.$BUNDLE_NAME.active.XXXXXX")"
  {
    printf 'FORMAT=%s\n' "$ACTIVE_FORMAT"
    printf 'TARGET=%s\n' "$PONGDANG_TARGET"
    printf 'PROJECT_NAME=%s\n' "$PONGDANG_PROJECT_NAME"
    printf 'LEGACY_RELEASE_VERSION=%s\n' "$LEGACY_RELEASE_VERSION"
    printf 'LEGACY_RELEASE_COMMIT=%s\n' "$LEGACY_RELEASE_COMMIT"
    printf 'SHARED_BACKUP=%s\n' "$backup_basename"
    printf 'DATA_WARNING=SHARED_DB_BACKUP_NOT_APPLIED_TO_PG15\n'
  } > "$temporary"
  chmod 0400 "$temporary"
  mv "$temporary" "$active"
}

restore_bundle() {
  local bundle="$PONGDANG_TARGET/state/$BUNDLE_NAME"
  local active="$PONGDANG_TARGET/state/$BUNDLE_NAME.active"
  local expected_confirmation
  local shared_backup
  local shared_backup_basename
  local expected_volume_created_at
  local restore_succeeded=0

  [[ ! -e "$active" && ! -L "$active" ]] \
    || pongdang_die "pre-cksDB standalone rollback is already active; reconcile it manually"
  validate_bundle "$bundle"
  expected_confirmation="RESTORE:pre-cksdb-standalone:${PONGDANG_PROJECT_NAME}:${LEGACY_VOLUME_KEY}"
  [[ "$CONFIRMATION" == "$expected_confirmation" ]] \
    || pongdang_die "restore requires --confirm $expected_confirmation"
  [[ "$DATA_STATE_CONFIRMATION" == "$DATA_CONFIRMATION" ]] \
    || pongdang_die "restore requires --confirm-data-state $DATA_CONFIRMATION"

  # Inspect the exact retained volume identity again immediately before the
  # irreversible writer stop. A recreated volume must never be mistaken for it.
  expected_volume_created_at="$LEGACY_VOLUME_CREATED_AT"
  inspect_legacy_volume
  [[ "$LEGACY_VOLUME_CREATED_AT" == "$expected_volume_created_at" ]] \
    || pongdang_die "retained PostgreSQL volume was replaced after the bundle was staged"

  pongdang_validate_secret_env
  validate_current_shared_compose
  cleanup_failed_restore() {
    if [[ "$restore_succeeded" -ne 1 ]]; then
      "${CURRENT_COMPOSE[@]}" stop collector backend >/dev/null 2>&1 || true
      BACKEND_IMAGE="$LEGACY_BACKEND_IMAGE" \
        FRONTEND_IMAGE="$LEGACY_FRONTEND_IMAGE" \
        "${LEGACY_COMPOSE[@]}" stop collector backend db >/dev/null 2>&1 || true
      echo "restore did not complete; all Multtara writers remain stopped" >&2
    fi
  }
  trap cleanup_failed_restore EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM

  # Quiesce both application writers before the safety dump so there is no
  # backup-to-stop gap in which cksDB can advance beyond the retained PG15 data.
  "${CURRENT_COMPOSE[@]}" stop collector backend
  shared_backup="$("$PONGDANG_TARGET/scripts/postgres-backup.sh" \
    --target "$PONGDANG_TARGET" --skip-retention)" \
    || pongdang_die "current cksDB backup failed; all Multtara writers remain stopped"
  [[ "$shared_backup" == "$PONGDANG_TARGET/backups/postgres/"* \
      && -f "$shared_backup" && ! -L "$shared_backup" \
      && -f "$shared_backup.sha256" && ! -L "$shared_backup.sha256" ]] \
    || pongdang_die "current cksDB backup did not return a verified in-target archive"
  (cd "${shared_backup%/*}" && sha256sum -c "${shared_backup##*/}.sha256" >/dev/null) \
    || pongdang_die "current cksDB backup checksum failed after writer shutdown"
  shared_backup_basename="${shared_backup##*/}"

  pongdang_acquire_lock database 8
  if ! BACKEND_IMAGE="$LEGACY_BACKEND_IMAGE" \
      FRONTEND_IMAGE="$LEGACY_FRONTEND_IMAGE" \
      "${LEGACY_COMPOSE[@]}" up \
        -d \
        --no-build \
        --remove-orphans \
        --wait \
        --wait-timeout 180; then
    pongdang_die "legacy standalone topology failed readiness; all writers remain stopped"
  fi
  publish_active_marker "$shared_backup_basename"
  restore_succeeded=1
  trap - EXIT INT TERM
  echo "pre-cksDB PostgreSQL 15 standalone topology is active"
  echo "verified cksDB safety backup retained: $shared_backup"
  echo "normal deploy/backup/restore commands are now blocked until the topology is reconciled"
}

ACTION="${1:-}"
case "$ACTION" in
  stage|verify|cutover|restore) shift ;;
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
CONFIRMATION=""
DATA_STATE_CONFIRMATION=""
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --target)
      [[ "$#" -ge 2 ]] || pongdang_die "--target requires a value"
      TARGET_INPUT="$2"
      shift 2
      ;;
    --confirm)
      [[ "$#" -ge 2 ]] || pongdang_die "--confirm requires a value"
      CONFIRMATION="$2"
      shift 2
      ;;
    --confirm-data-state)
      [[ "$#" -ge 2 ]] || pongdang_die "--confirm-data-state requires a value"
      DATA_STATE_CONFIRMATION="$2"
      shift 2
      ;;
    *)
      usage >&2
      pongdang_die "unknown argument: $1"
      ;;
  esac
done

[[ -n "$TARGET_INPUT" ]] || pongdang_die "--target is required"
if [[ "$ACTION" == "stage" || "$ACTION" == "verify" ]]; then
  [[ -z "$CONFIRMATION" && -z "$DATA_STATE_CONFIRMATION" ]] \
    || pongdang_die "$ACTION does not accept restore confirmations"
elif [[ "$ACTION" == "cutover" ]]; then
  [[ -z "$DATA_STATE_CONFIRMATION" ]] \
    || pongdang_die "cutover does not accept a rollback data-state confirmation"
fi

pongdang_validate_existing_target "$TARGET_INPUT"
pongdang_require_deploy_user
pongdang_require_pi_platform
pongdang_require_command cmp
pongdang_require_command find
pongdang_require_command sha256sum
pongdang_require_compose

case "$ACTION" in
  stage)
    pongdang_acquire_lock deploy
    stage_bundle
    ;;
  verify)
    verify_bundle
    ;;
  cutover)
    pongdang_acquire_lock deploy
    pongdang_acquire_lock database 8
    cutover_to_cksdb
    ;;
  restore)
    pongdang_acquire_lock deploy
    restore_bundle
    ;;
esac
