#!/usr/bin/env bash
# Shared fail-closed validation for PongDang Raspberry Pi operations.
# shellcheck shell=bash

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  echo "deploy-common.sh must be sourced by a deployment command" >&2
  exit 2
fi

PONGDANG_MARKER_NAME=".pongdang-deployment"
PONGDANG_MIN_COMPOSE_MAJOR=2
PONGDANG_MIN_COMPOSE_MINOR=24
PONGDANG_MIN_COMPOSE_PATCH=4

pongdang_die() {
  echo "error: $*" >&2
  exit 1
}

pongdang_require_command() {
  command -v "$1" >/dev/null 2>&1 || pongdang_die "required command is missing: $1"
}

pongdang_resolve_target() {
  local candidate="${1%/}"
  local parent
  local resolved_parent
  local basename

  [[ "$candidate" == /* ]] || pongdang_die "deployment target must be absolute"
  [[ "$candidate" != "/" ]] || pongdang_die "filesystem root is not a deployment target"
  [[ ! -L "$candidate" ]] || pongdang_die "deployment target must not be a symlink: $candidate"
  basename="${candidate##*/}"
  [[ "$basename" =~ ^pongdang(-[a-z0-9]+)*$ ]] \
    || pongdang_die "deployment directory name must be pongdang or pongdang-<name>"
  parent="${candidate%/*}"
  [[ -d "$parent" ]] || pongdang_die "deployment parent does not exist: $parent"
  resolved_parent="$(cd "$parent" && pwd -P)"
  PONGDANG_TARGET="$resolved_parent/$basename"
  [[ "$candidate" == "$PONGDANG_TARGET" ]] \
    || pongdang_die "deployment target is not canonical: $candidate -> $PONGDANG_TARGET"
}

pongdang_marker_value() {
  local marker="$1"
  local key="$2"
  awk -F= -v key="$key" '
    $1 == key {
      count += 1
      value = substr($0, index($0, "=") + 1)
    }
    END {
      if (count != 1) exit 1
      print value
    }
  ' "$marker"
}

pongdang_validate_layout() {
  local relative
  local path
  local resolved

  for relative in state releases backups backups/postgres scripts; do
    path="$PONGDANG_TARGET/$relative"
    [[ -d "$path" && ! -L "$path" ]] \
      || pongdang_die "deployment directory is missing or unsafe: $path"
    resolved="$(cd "$path" && pwd -P)"
    [[ "$resolved" == "$path" ]] \
      || pongdang_die "deployment directory escaped its approved path: $path -> $resolved"
  done
}

pongdang_validate_existing_target() {
  local requested="$1"
  local marker
  local format
  local marked_target

  pongdang_resolve_target "$requested"
  [[ -d "$PONGDANG_TARGET" ]] || pongdang_die "deployment target does not exist: $PONGDANG_TARGET"
  marker="$PONGDANG_TARGET/$PONGDANG_MARKER_NAME"
  [[ -f "$marker" && ! -L "$marker" ]] || pongdang_die "deployment marker is missing or unsafe: $marker"
  format="$(pongdang_marker_value "$marker" FORMAT)" \
    || pongdang_die "deployment marker FORMAT is invalid"
  marked_target="$(pongdang_marker_value "$marker" TARGET)" \
    || pongdang_die "deployment marker TARGET is invalid"
  PONGDANG_DEPLOY_USER="$(pongdang_marker_value "$marker" DEPLOY_USER)" \
    || pongdang_die "deployment marker DEPLOY_USER is invalid"
  PONGDANG_PROJECT_NAME="$(pongdang_marker_value "$marker" PROJECT_NAME)" \
    || pongdang_die "deployment marker PROJECT_NAME is invalid"
  [[ "$format" == "PONGDANG_DEPLOYMENT_V1" ]] || pongdang_die "unsupported deployment marker format"
  [[ "$marked_target" == "$PONGDANG_TARGET" ]] || pongdang_die "deployment marker target mismatch"
  [[ "$PONGDANG_DEPLOY_USER" =~ ^[a-z_][a-z0-9_-]*[$]?$ ]] || pongdang_die "invalid deployment user in marker"
  [[ "$PONGDANG_PROJECT_NAME" =~ ^pongdang(-[a-z0-9]+)*$ ]] || pongdang_die "invalid Compose project in marker"
  pongdang_validate_layout
}

pongdang_require_deploy_user() {
  local actual_user
  actual_user="$(id -un)"
  [[ "$actual_user" == "$PONGDANG_DEPLOY_USER" ]] \
    || pongdang_die "run as deployment user $PONGDANG_DEPLOY_USER, not $actual_user"
}

pongdang_require_pi_platform() {
  local kernel
  local machine
  kernel="$(uname -s)"
  machine="$(uname -m)"
  [[ "$kernel" == "Linux" ]] || pongdang_die "deployment requires Linux, found $kernel"
  [[ "$machine" == "aarch64" || "$machine" == "arm64" ]] \
    || pongdang_die "deployment requires ARM64, found $machine"
}

pongdang_require_compose() {
  local version
  local major
  local minor
  local patch
  pongdang_require_command docker
  docker info >/dev/null 2>&1 || pongdang_die "Docker Engine is unavailable to the deployment user"
  version="$(docker compose version --short 2>/dev/null)" \
    || pongdang_die "Docker Compose plugin is unavailable"
  version="${version#v}"
  major="${version%%.*}"
  minor="${version#*.}"
  minor="${minor%%.*}"
  patch="${version#*.*.}"
  patch="${patch%%[-+]*}"
  patch="${patch%%.*}"
  [[ "$major" =~ ^[0-9]+$ && "$minor" =~ ^[0-9]+$ && "$patch" =~ ^[0-9]+$ ]] \
    || pongdang_die "cannot parse Docker Compose version: $version"
  if (( major < PONGDANG_MIN_COMPOSE_MAJOR \
      || (major == PONGDANG_MIN_COMPOSE_MAJOR \
          && (minor < PONGDANG_MIN_COMPOSE_MINOR \
              || (minor == PONGDANG_MIN_COMPOSE_MINOR \
                  && patch < PONGDANG_MIN_COMPOSE_PATCH))) )); then
    pongdang_die "Docker Compose >= ${PONGDANG_MIN_COMPOSE_MAJOR}.${PONGDANG_MIN_COMPOSE_MINOR}.${PONGDANG_MIN_COMPOSE_PATCH} is required"
  fi
}

pongdang_env_value() {
  local file="$1"
  local key="$2"
  awk -F= -v key="$key" '
    $1 == key {
      count += 1
      value = substr($0, index($0, "=") + 1)
    }
    END {
      if (count != 1) exit 1
      print value
    }
  ' "$file"
}

pongdang_optional_env_value() {
  local file="$1"
  local key="$2"
  awk -F= -v key="$key" '
    $1 == key {
      count += 1
      value = substr($0, index($0, "=") + 1)
    }
    END {
      if (count > 1) exit 1
      if (count == 1) print value
    }
  ' "$file"
}

pongdang_validate_secret_env() {
  local file="$PONGDANG_TARGET/.env"
  local mode
  local owner
  local secret_lower

  [[ -f "$file" && ! -L "$file" ]] || pongdang_die "secret environment file is missing or unsafe: $file"
  [[ -z "$(LC_ALL=C tr -d '\11\12\15\40-\176' < "$file")" ]] \
    || pongdang_die "secret environment file contains control characters"
  ! LC_ALL=C grep -q $'\r' "$file" || pongdang_die "secret environment file uses CRLF; use Unix line endings"
  mode="$(stat -c '%a' "$file")"
  owner="$(stat -c '%u' "$file")"
  (( (8#$mode & 077) == 0 )) || pongdang_die "secret environment file must not be group/world accessible (mode $mode)"
  [[ "$owner" == "$(id -u)" ]] || pongdang_die "secret environment file must be owned by the deployment user"

  PONGDANG_POSTGRES_DB="$(pongdang_env_value "$file" POSTGRES_DB)" \
    || pongdang_die "POSTGRES_DB must appear exactly once"
  PONGDANG_POSTGRES_USER="$(pongdang_env_value "$file" POSTGRES_USER)" \
    || pongdang_die "POSTGRES_USER must appear exactly once"
  PONGDANG_POSTGRES_PASSWORD="$(pongdang_env_value "$file" POSTGRES_PASSWORD)" \
    || pongdang_die "POSTGRES_PASSWORD must appear exactly once"
  PONGDANG_DATABASE_URL="$(pongdang_env_value "$file" DATABASE_URL)" \
    || pongdang_die "DATABASE_URL must appear exactly once"
  PONGDANG_SECRET_KEY="$(pongdang_env_value "$file" SECRET_KEY)" \
    || pongdang_die "SECRET_KEY must appear exactly once"
  PONGDANG_ALLOWED_HOSTS="$(pongdang_env_value "$file" ALLOWED_HOSTS)" \
    || pongdang_die "ALLOWED_HOSTS must appear exactly once"
  PONGDANG_SSL_REDIRECT="$(pongdang_env_value "$file" SECURE_SSL_REDIRECT)" \
    || pongdang_die "SECURE_SSL_REDIRECT must appear exactly once"
  PONGDANG_FRONTEND_BIND="$(pongdang_env_value "$file" FRONTEND_BIND_ADDRESS)" \
    || pongdang_die "FRONTEND_BIND_ADDRESS must appear exactly once"
  PONGDANG_ROUTING_MATRIX_URL="$(pongdang_optional_env_value "$file" ROUTING_MATRIX_URL)" \
    || pongdang_die "ROUTING_MATRIX_URL may appear at most once"

  [[ "$PONGDANG_POSTGRES_DB" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] \
    || pongdang_die "POSTGRES_DB is not a safe PostgreSQL identifier"
  [[ "$PONGDANG_POSTGRES_DB" != "postgres" && "$PONGDANG_POSTGRES_DB" != template* ]] \
    || pongdang_die "POSTGRES_DB must be a dedicated application database"
  [[ "$PONGDANG_POSTGRES_USER" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] \
    || pongdang_die "POSTGRES_USER is not a safe PostgreSQL identifier"
  (( ${#PONGDANG_POSTGRES_PASSWORD} >= 16 )) \
    || pongdang_die "POSTGRES_PASSWORD must contain at least 16 characters"
  [[ "$PONGDANG_POSTGRES_PASSWORD" != *YOUR_PASSWORD* ]] \
    || pongdang_die "POSTGRES_PASSWORD still contains a placeholder"
  [[ "$PONGDANG_DATABASE_URL" != *YOUR_PASSWORD* && "$PONGDANG_DATABASE_URL" != *REPLACE_* ]] \
    || pongdang_die "DATABASE_URL still contains a placeholder"
  pongdang_require_command python3
  if ! PONGDANG_CHECK_DATABASE_URL="$PONGDANG_DATABASE_URL" \
      PONGDANG_CHECK_POSTGRES_DB="$PONGDANG_POSTGRES_DB" \
      PONGDANG_CHECK_POSTGRES_USER="$PONGDANG_POSTGRES_USER" \
      PONGDANG_CHECK_POSTGRES_PASSWORD="$PONGDANG_POSTGRES_PASSWORD" \
      python3 - <<'PY'
import os
import re
from urllib.parse import unquote, urlsplit

url = os.environ["PONGDANG_CHECK_DATABASE_URL"]
database = os.environ["PONGDANG_CHECK_POSTGRES_DB"]
expected_user = os.environ["PONGDANG_CHECK_POSTGRES_USER"]
expected_password = os.environ["PONGDANG_CHECK_POSTGRES_PASSWORD"]

try:
    parsed = urlsplit(url)
    port = parsed.port
except ValueError:
    raise SystemExit(1) from None

if parsed.scheme != "postgresql" or parsed.hostname != "db" or port != 5432:
    raise SystemExit(1)
if parsed.path != f"/{database}" or parsed.query or parsed.fragment:
    raise SystemExit(1)
if parsed.username is None or parsed.password is None:
    raise SystemExit(1)

# The URL is configuration, not a shell template. Require each userinfo
# component to be RFC 3986 unreserved bytes or explicit percent escapes so raw
# '@', '/', ':', and '%' cannot make Docker and Django interpret it differently.
userinfo = parsed.netloc.rsplit("@", 1)[0]
if ":" not in userinfo:
    raise SystemExit(1)
encoded_user, encoded_password = userinfo.split(":", 1)
encoded_component = re.compile(r"^(?:[A-Za-z0-9._~-]|%[0-9A-Fa-f]{2})+$")
if not encoded_component.fullmatch(encoded_user):
    raise SystemExit(1)
if not encoded_component.fullmatch(encoded_password):
    raise SystemExit(1)
if unquote(encoded_user) != expected_user or unquote(encoded_password) != expected_password:
    raise SystemExit(1)
PY
  then
    pongdang_die "DATABASE_URL must contain the percent-encoded PostgreSQL credentials and target db:5432/POSTGRES_DB exactly"
  fi
  (( ${#PONGDANG_SECRET_KEY} >= 50 )) || pongdang_die "SECRET_KEY must contain at least 50 characters"
  secret_lower="$(printf '%s' "$PONGDANG_SECRET_KEY" | tr '[:upper:]' '[:lower:]')"
  [[ "$secret_lower" != django-insecure-* && "$secret_lower" != *change* ]] \
    || pongdang_die "SECRET_KEY is not production-safe"
  [[ -n "$PONGDANG_ALLOWED_HOSTS" && "$PONGDANG_ALLOWED_HOSTS" != *"*"* ]] \
    || pongdang_die "ALLOWED_HOSTS must be explicit and cannot contain '*'"
  [[ "$PONGDANG_ALLOWED_HOSTS" != *"://"* && "$PONGDANG_ALLOWED_HOSTS" != *"/"* ]] \
    || pongdang_die "ALLOWED_HOSTS accepts host names, not URLs"
  [[ "$PONGDANG_SSL_REDIRECT" == "True" ]] || pongdang_die "SECURE_SSL_REDIRECT must be True on the Pi"
  [[ "$PONGDANG_FRONTEND_BIND" == "127.0.0.1" ]] \
    || pongdang_die "FRONTEND_BIND_ADDRESS must remain 127.0.0.1 behind the trusted HTTPS edge"
  if [[ -n "$PONGDANG_ROUTING_MATRIX_URL" ]]; then
    [[ "$PONGDANG_ROUTING_MATRIX_URL" =~ ^https://[A-Za-z0-9.-]+(:[0-9]+)?(/[A-Za-z0-9._~:/%-]*)?/?$ ]] \
      || pongdang_die "ROUTING_MATRIX_URL must be a credential-free HTTPS base URL"
  fi
  # This library publishes the validated path to each caller.
  # shellcheck disable=SC2034
  PONGDANG_ENV_FILE="$file"
}

pongdang_validate_release_manifest() {
  local file="$1"
  local invalid

  [[ -f "$file" && ! -L "$file" ]] || pongdang_die "release manifest is missing or unsafe: $file"
  ! LC_ALL=C grep -q $'\r' "$file" || pongdang_die "release manifest uses CRLF; use Unix line endings"
  invalid="$(awk -F= '
    BEGIN {
      allowed["RELEASE_VERSION"] = 1
      allowed["RELEASE_COMMIT"] = 1
      allowed["BACKEND_IMAGE"] = 1
      allowed["FRONTEND_IMAGE"] = 1
    }
    /^[[:space:]]*$/ { next }
    {
      key = $1
      if (!(key in allowed) || seen[key]++) invalid = 1
    }
    END {
      for (key in allowed) if (seen[key] != 1) invalid = 1
      print invalid + 0
    }
  ' "$file")"
  [[ "$invalid" == "0" ]] || pongdang_die "release manifest has unknown, missing, or duplicate keys"

  PONGDANG_RELEASE_VERSION="$(pongdang_env_value "$file" RELEASE_VERSION)"
  PONGDANG_RELEASE_COMMIT="$(pongdang_env_value "$file" RELEASE_COMMIT)"
  PONGDANG_BACKEND_IMAGE="$(pongdang_env_value "$file" BACKEND_IMAGE)"
  PONGDANG_FRONTEND_IMAGE="$(pongdang_env_value "$file" FRONTEND_IMAGE)"
  [[ "$PONGDANG_RELEASE_VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$ ]] \
    || pongdang_die "release version must match vMAJOR.MINOR.PATCH"
  [[ "$PONGDANG_RELEASE_COMMIT" =~ ^[0-9a-f]{40}$ ]] \
    || pongdang_die "release commit must be a full lowercase Git SHA"
  [[ "$PONGDANG_BACKEND_IMAGE" =~ ^ghcr\.io/[a-z0-9][a-z0-9._/-]*/backend@sha256:[0-9a-f]{64}$ ]] \
    || pongdang_die "backend image must be a lowercase GHCR backend digest"
  [[ "$PONGDANG_FRONTEND_IMAGE" =~ ^ghcr\.io/[a-z0-9][a-z0-9._/-]*/frontend@sha256:[0-9a-f]{64}$ ]] \
    || pongdang_die "frontend image must be a lowercase GHCR frontend digest"
  [[ "$PONGDANG_BACKEND_IMAGE" != "$PONGDANG_FRONTEND_IMAGE" ]] \
    || pongdang_die "backend and frontend images must differ"
}

pongdang_verify_release_checksum() {
  local file="$1"
  local checksum="$file.sha256"
  local basename
  local expected_line
  local actual_line

  [[ -f "$checksum" && ! -L "$checksum" ]] || pongdang_die "release manifest checksum is missing: $checksum"
  basename="${file##*/}"
  expected_line="$(awk 'NR == 1 { print $1 "  " $2 } END { if (NR != 1) exit 1 }' "$checksum")" \
    || pongdang_die "release checksum file must contain exactly one record"
  actual_line="$(cd "${file%/*}" && sha256sum "$basename")"
  [[ "$expected_line" == "$actual_line" ]] || pongdang_die "release manifest checksum mismatch"
}

pongdang_acquire_lock() {
  local name="$1"
  local descriptor="${2:-9}"
  local lock_path="$PONGDANG_TARGET/state/$name.lock"
  pongdang_require_command flock
  if [[ -e "$lock_path" || -L "$lock_path" ]]; then
    [[ -f "$lock_path" && ! -L "$lock_path" ]] \
      || pongdang_die "operation lock path is unsafe: $lock_path"
  fi
  case "$descriptor" in
    7)
      exec 7>"$lock_path"
      flock -n 7 || pongdang_die "another $name operation is already running"
      ;;
    8)
      exec 8>"$lock_path"
      flock -n 8 || pongdang_die "another $name operation is already running"
      ;;
    9)
      exec 9>"$lock_path"
      flock -n 9 || pongdang_die "another $name operation is already running"
      ;;
    *) pongdang_die "unsupported lock descriptor: $descriptor" ;;
  esac
}
