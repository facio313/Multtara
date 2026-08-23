#!/usr/bin/env bash
set -euo pipefail
umask 0022

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$REPO_ROOT"

bash -n \
  scripts/db-migration-rollback.sh \
  scripts/deploy-common.sh \
  scripts/pi-setup.sh \
  scripts/pi-deploy.sh \
  scripts/postgres-backup.sh \
  scripts/postgres-prune-backups.sh \
  scripts/postgres-restore.sh

TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/pongdang-deploy-test.XXXXXX")"
TMP_ROOT="$(cd "$TMP_ROOT" && pwd -P)"
cleanup() {
  case "$TMP_ROOT" in
    */pongdang-deploy-test.*) find "$TMP_ROOT" -depth -delete ;;
    *) echo "refusing unexpected cleanup path: $TMP_ROOT" >&2 ;;
  esac
}
trap cleanup EXIT INT TERM

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

RELEASE_DIR="$TMP_ROOT/release"
mkdir -p "$RELEASE_DIR"
{
  printf 'RELEASE_VERSION=v1.2.3\n'
  printf 'RELEASE_COMMIT=1234567890abcdef1234567890abcdef12345678\n'
  printf 'BACKEND_IMAGE=ghcr.io/example/pongdang/backend@sha256:%064d\n' 1
  printf 'FRONTEND_IMAGE=ghcr.io/example/pongdang/frontend@sha256:%064d\n' 2
} > "$RELEASE_DIR/release.env"
(
  cd "$RELEASE_DIR"
  sha256sum release.env > release.env.sha256
)
scripts/pi-deploy.sh validate-release "$RELEASE_DIR/release.env" >/dev/null

cp "$RELEASE_DIR/release.env" "$RELEASE_DIR/mutable.env"
sed 's#backend@sha256:[0-9]*#backend:v1.2.3#' \
  "$RELEASE_DIR/mutable.env" > "$RELEASE_DIR/mutable.env.tmp"
mv "$RELEASE_DIR/mutable.env.tmp" "$RELEASE_DIR/mutable.env"
(
  cd "$RELEASE_DIR"
  sha256sum mutable.env > mutable.env.sha256
)
if scripts/pi-deploy.sh validate-release "$RELEASE_DIR/mutable.env" >/dev/null 2>&1; then
  fail "mutable image tag was accepted"
fi

cp "$RELEASE_DIR/release.env" "$RELEASE_DIR/unknown.env"
printf 'UNEXPECTED=value\n' >> "$RELEASE_DIR/unknown.env"
(
  cd "$RELEASE_DIR"
  sha256sum unknown.env > unknown.env.sha256
)
if scripts/pi-deploy.sh validate-release "$RELEASE_DIR/unknown.env" >/dev/null 2>&1; then
  fail "unknown release key was accepted"
fi

printf '\nMUTATED\n' >> "$RELEASE_DIR/release.env"
if scripts/pi-deploy.sh validate-release "$RELEASE_DIR/release.env" >/dev/null 2>&1; then
  fail "release checksum mismatch was accepted"
fi

TARGET="$TMP_ROOT/pongdang-test"
mkdir -p "$TARGET/state" "$TARGET/releases" "$TARGET/backups/postgres" "$TARGET/scripts"
{
  printf 'FORMAT=PONGDANG_DEPLOYMENT_V1\n'
  printf 'TARGET=%s\n' "$TARGET"
  printf 'DEPLOY_USER=pongdangtest\n'
  printf 'PROJECT_NAME=pongdang-test\n'
} > "$TARGET/.pongdang-deployment"
TARGET="$TARGET" SCRIPT_DIR="$REPO_ROOT/scripts" bash -c '
  set -euo pipefail
  # shellcheck source=deploy-common.sh
  source "$SCRIPT_DIR/deploy-common.sh"
  pongdang_validate_existing_target "$TARGET"
'

UNSAFE_TARGET="$TMP_ROOT/pongdang-unsafe"
mkdir -p \
  "$UNSAFE_TARGET/releases" \
  "$UNSAFE_TARGET/backups/postgres" \
  "$UNSAFE_TARGET/scripts"
ln -s "$TARGET/state" "$UNSAFE_TARGET/state"
{
  printf 'FORMAT=PONGDANG_DEPLOYMENT_V1\n'
  printf 'TARGET=%s\n' "$UNSAFE_TARGET"
  printf 'DEPLOY_USER=pongdangtest\n'
  printf 'PROJECT_NAME=pongdang-unsafe\n'
} > "$UNSAFE_TARGET/.pongdang-deployment"
if TARGET="$UNSAFE_TARGET" SCRIPT_DIR="$REPO_ROOT/scripts" bash -c '
    set -euo pipefail
    # shellcheck source=deploy-common.sh
    source "$SCRIPT_DIR/deploy-common.sh"
    pongdang_validate_existing_target "$TARGET"
  ' >/dev/null 2>&1; then
  fail "symlinked deployment state directory was accepted"
fi

# Exercise the backup and restore control flow across deterministic Docker and
# shared-DB operator boundaries. The fakes preserve command/stream behavior but
# do not claim a real PostgreSQL recovery; that remains an ARM64 drill obligation.
cp \
  scripts/db-migration-rollback.sh \
  scripts/deploy-common.sh \
  scripts/pi-deploy.sh \
  scripts/postgres-backup.sh \
  scripts/postgres-prune-backups.sh \
  scripts/postgres-restore.sh \
  "$TARGET/scripts/"
chmod +x "$TARGET/scripts/"*.sh
cp docker-compose.yml docker-compose.deploy.yml "$TARGET/"
export PONGDANG_FAKE_SHARED_DB_LOG="$TMP_ROOT/fake-shared-db.log"
: > "$PONGDANG_FAKE_SHARED_DB_LOG"
CKSDB_REVISION=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
SHARED_DB_TOOL="$TARGET/releases/$CKSDB_REVISION/scripts/multtara-db.sh"
mkdir -p "${SHARED_DB_TOOL%/*}"
cat > "$SHARED_DB_TOOL" <<'SH'
#!/usr/bin/env bash
set -euo pipefail

printf '%s\n' "$*" >> "$PONGDANG_FAKE_SHARED_DB_LOG"
case "${1:-}" in
  contract)
    [[ "$#" -eq 1 ]]
    printf '{"protocol":"cksdb.multtara-db","version":1,"database":"pongdang","role":"pongdang"}\n'
    ;;
  ready)
    [[ "$#" -eq 1 && "${PONGDANG_FAKE_SHARED_DB_READY:-1}" == "1" ]]
    ;;
  dump)
    [[ "$#" -eq 3 && "$2" == "--output" && "$3" == /* && ! -e "$3" ]]
    printf 'FAKE_CUSTOM_ARCHIVE\n' > "$3"
    chmod 0600 "$3"
    printf 'dump\n' >> "$PONGDANG_FAKE_SHARED_DB_LOG"
    printf '%s/%s\n' "$(cd "${3%/*}" && pwd -P)" "${3##*/}"
    ;;
  verify)
    [[ "$#" -eq 3 && "$2" == "--backup" && -s "$3" ]]
    ;;
  restore)
    [[ "$#" -eq 5 \
      && "$2" == "--backup" \
      && -s "$3" \
      && "$4" == "--confirm" \
      && "$5" == "RESTORE:multtara:pongdang" ]]
    ;;
  finalize)
    [[ "$#" -eq 3 \
      && "$2" == "--confirm" \
      && "$3" == "FINALIZE:multtara:pongdang_previous" ]]
    printf '{"protocol":"cksdb.multtara-db","version":1,"action":"finalize","database":"pongdang","removed":"pongdang_previous","ready":true}\n'
    ;;
  *)
    exit 2
    ;;
esac
SH
chmod 0755 "$SHARED_DB_TOOL"
SHARED_DB_TOOL_SHA256="$(sha256sum "$SHARED_DB_TOOL" | awk '{print $1}')"
SSO_SECRET_FILE="$TARGET/state/pongdang-sso-edge-secret"
printf 'test-only-private-edge-secret-value-2026\n' > "$SSO_SECRET_FILE"
chmod 0640 "$SSO_SECRET_FILE"
{
  printf 'POSTGRES_DB=pongdang\n'
  printf 'POSTGRES_USER=pongdang\n'
  printf 'POSTGRES_PASSWORD=0123456789abcdef\n'
  printf 'DATABASE_URL=postgresql://pongdang:0123456789abcdef@cksDB:5432/pongdang\n'
  printf 'SHARED_DB_TOOL=%s\n' "$SHARED_DB_TOOL"
  printf 'SHARED_DB_TOOL_SHA256=%s\n' "$SHARED_DB_TOOL_SHA256"
  printf 'CKSDB_REVISION=%s\n' "$CKSDB_REVISION"
  printf 'SECRET_KEY=0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMN\n'
  printf 'ALLOWED_HOSTS=localhost\n'
  printf 'SECURE_SSL_REDIRECT=True\n'
  printf 'FRONTEND_BIND_ADDRESS=127.0.0.1\n'
  printf 'PORTFOLIO_BRANCH=main\n'
  printf 'PORTFOLIO_AUTH_MODE=sso\n'
  printf 'VITE_SSO_ENABLED=true\n'
  printf 'ROUTING_MATRIX_URL=\n'
  printf 'PONGDANG_SSO_ENABLED=True\n'
  printf 'PONGDANG_SSO_EDGE_SECRET=\n'
  printf 'PONGDANG_SSO_EDGE_SECRET_MOUNT=%s\n' "$SSO_SECRET_FILE"
  printf 'PONGDANG_SSO_EDGE_SECRET_FILE=/run/secrets/pongdang_sso_edge_secret\n'
  printf 'PONGDANG_BACKEND_RUNTIME_USER=pongdang:root\n'
  printf 'BACKUP_RETENTION_DAYS=14\n'
  printf '# 운영 UTF-8 주석은 허용한다.\n'
} > "$TARGET/.env"
chmod 0600 "$TARGET/.env"

FAKE_BIN="$TMP_ROOT/fake-bin"
mkdir -p "$FAKE_BIN"
cat > "$FAKE_BIN/id" <<'SH'
#!/bin/sh
case "${1:-}" in
  -un) echo pongdangtest ;;
  -u) echo 1000 ;;
  -gn) echo pongdangtest ;;
  *) echo 1000 ;;
esac
SH
cat > "$FAKE_BIN/stat" <<'SH'
#!/bin/sh
case "${2:-}" in
  %a)
    case "${3##*/}" in
      .env) echo 600 ;;
      pongdang-sso-edge-secret) echo 640 ;;
      *) /usr/bin/stat "$@" ;;
    esac
    ;;
  %u) echo 1000 ;;
  %g) echo 1000 ;;
  *) exit 1 ;;
esac
SH
cat > "$FAKE_BIN/uname" <<'SH'
#!/bin/sh
case "${1:-}" in
  -s) echo Linux ;;
  -m) echo aarch64 ;;
  *) echo Linux ;;
esac
SH
cat > "$FAKE_BIN/flock" <<'SH'
#!/bin/sh
exit 0
SH
cat > "$FAKE_BIN/docker" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "info" ]]; then
  exit 0
fi
if [[ "${1:-}" == "volume" && "${2:-}" == "inspect" ]]; then
  [[ "${@: -1}" == "${PONGDANG_FAKE_VOLUME_PROJECT:-pongdang-test}_postgres_data" ]]
  printf 'local|%s|postgres_data|%s\n' \
    "${PONGDANG_FAKE_VOLUME_PROJECT:-pongdang-test}" \
    "${PONGDANG_FAKE_VOLUME_CREATED_AT:-2026-08-01T00:00:00Z}"
  exit 0
fi
if [[ "${1:-}" == "inspect" && "${@: -1}" == "cksDB" ]]; then
  printf 'sha256:%064d|running\n' 9
  exit 0
fi
if [[ "${1:-}" == "run" ]]; then
  if [[ " $* " == *" SHOW server_version_num "* ]]; then
    printf '160000\n'
  else
    cat >/dev/null
    printf '"schema","public","pongdang"\n"row-count","public","probe","1"\n'
  fi
  exit 0
fi
if [[ " $* " == *" compose version --short "* ]]; then
  echo "${PONGDANG_FAKE_COMPOSE_VERSION:-v2.24.4}"
  exit 0
fi
if [[ " $* " == *" ps --status running --services "* ]]; then
  if [[ "${PONGDANG_FAKE_CUTOVER:-0}" == "1" ]]; then
    printf 'db\nfrontend\n'
  else
    printf 'db\nbackend\ncollector\nfrontend\n'
  fi
  exit 0
fi
if [[ " $* " == *" exec -T db postgres --version "* ]]; then
  printf 'postgres (PostgreSQL) %s.13\n' "${PONGDANG_FAKE_PG_MAJOR:-15}"
  exit 0
fi
if [[ " $* " == *" exec -T db pg_dump "* ]]; then
  printf 'FAKE_PG15_CUSTOM_ARCHIVE\n'
  exit 0
fi
if [[ " $* " == *" exec -T db pg_restore --list "* ]]; then
  cat >/dev/null
  exit 0
fi
if [[ " $* " == *" exec -T db psql "* ]]; then
  cat >/dev/null
  printf '"schema","public","pongdang"\n"row-count","public","probe","1"\n'
  exit 0
fi
for token in "$@"; do
  case "$token" in
    config)
      echo config >> "$PONGDANG_FAKE_DOCKER_LOG"
      if [[ " $* " == *"/pre-cksdb-rollback/"* \
          || "${PONGDANG_FAKE_LEGACY_TARGET_CONFIG:-0}" == "1" ]]; then
        printf '{"services":{"db":{"image":"postgres:15-alpine","environment":{"POSTGRES_DB":"pongdang","POSTGRES_USER":"pongdang"},"volumes":[{"type":"volume","source":"%s_postgres_data","target":"/var/lib/postgresql/data"}]},"backend":{"image":"%s","pull_policy":"always","environment":{"DATABASE_URL":"postgresql://pongdang:0123456789abcdef@db:5432/pongdang"},"depends_on":{"db":{"condition":"service_healthy"}},"networks":{"default":null}},"collector":{"image":"%s","pull_policy":"always","environment":{"DATABASE_URL":"postgresql://pongdang:0123456789abcdef@db:5432/pongdang"},"networks":{"default":null}},"frontend":{"image":"%s","pull_policy":"always","networks":{"default":null}}},"volumes":{"postgres_data":{"name":"%s_postgres_data"}},"networks":{"default":{"name":"%s_default"}}}\n' \
          "${PONGDANG_FAKE_VOLUME_PROJECT:-pongdang-legacy}" \
          "$BACKEND_IMAGE" "$BACKEND_IMAGE" "$FRONTEND_IMAGE" \
          "${PONGDANG_FAKE_VOLUME_PROJECT:-pongdang-legacy}" \
          "${PONGDANG_FAKE_VOLUME_PROJECT:-pongdang-legacy}"
      elif [[ "${PONGDANG_FAKE_EXTRA_SERVICE:-0}" == "1" ]]; then
        printf '{"services":{"backend":{"image":"%s","pull_policy":"always","networks":{"default":null,"multtara-db":null}},"collector":{"image":"%s","pull_policy":"always","networks":{"default":null,"multtara-db":null}},"frontend":{"image":"%s","pull_policy":"always","networks":{"default":null},"ports":[{"host_ip":"127.0.0.1","published":"8080","target":8080}]},"unexpected":{"image":"busybox"}},"networks":{"default":{"name":"pongdang-test_default"},"multtara-db":{"name":"cksDB-multtara","external":true}}}\n' \
          "$BACKEND_IMAGE" "$BACKEND_IMAGE" "$FRONTEND_IMAGE"
      elif [[ "${PONGDANG_FAKE_FRONTEND_EXTRA_NETWORK:-0}" == "1" ]]; then
        printf '{"services":{"backend":{"image":"%s","pull_policy":"always","networks":{"default":null,"multtara-db":null}},"collector":{"image":"%s","pull_policy":"always","networks":{"default":null,"multtara-db":null}},"frontend":{"image":"%s","pull_policy":"always","networks":{"default":null,"monitor":null},"ports":[{"host_ip":"127.0.0.1","published":"8080","target":8080}]}},"networks":{"default":{"name":"pongdang-test_default"},"monitor":{"name":"monitor"},"multtara-db":{"name":"cksDB-multtara","external":true}}}\n' \
          "$BACKEND_IMAGE" "$BACKEND_IMAGE" "$FRONTEND_IMAGE"
      elif [[ "${PONGDANG_FAKE_BAD_NETWORK:-0}" == "1" ]]; then
        printf '{"services":{"backend":{"image":"%s","pull_policy":"always","networks":{"default":null}},"collector":{"image":"%s","pull_policy":"always","networks":{"default":null}},"frontend":{"image":"%s","pull_policy":"always","networks":{"default":null},"ports":[{"host_ip":"127.0.0.1","published":"8080","target":8080}]}},"networks":{"default":{"name":"pongdang-test_default"}}}\n' \
          "$BACKEND_IMAGE" "$BACKEND_IMAGE" "$FRONTEND_IMAGE"
      else
        printf '{"services":{"backend":{"image":"%s","pull_policy":"always","networks":{"default":null,"multtara-db":null}},"collector":{"image":"%s","pull_policy":"always","networks":{"default":null,"multtara-db":null}},"frontend":{"image":"%s","pull_policy":"always","networks":{"default":null},"ports":[{"host_ip":"127.0.0.1","published":"8080","target":8080}]}},"networks":{"default":{"name":"pongdang-test_default"},"multtara-db":{"name":"cksDB-multtara","external":true}}}\n' \
          "$BACKEND_IMAGE" "$BACKEND_IMAGE" "$FRONTEND_IMAGE"
      fi
      exit 0
      ;;
    pull)
      echo pull >> "$PONGDANG_FAKE_DOCKER_LOG"
      exit 0
      ;;
    stop)
      echo stop >> "$PONGDANG_FAKE_DOCKER_LOG"
      exit 0
      ;;
    up)
      echo up >> "$PONGDANG_FAKE_DOCKER_LOG"
      [[ "${PONGDANG_FAKE_UP_FAIL:-0}" != "1" ]]
      exit 0
      ;;
  esac
done
exit 0
SH
chmod +x "$FAKE_BIN/"*
export PONGDANG_FAKE_DOCKER_LOG="$TMP_ROOT/fake-docker.log"
: > "$PONGDANG_FAKE_DOCKER_LOG"

cp "$TARGET/.env" "$TARGET/.env.valid-shared-tool"
sed 's#^SHARED_DB_TOOL=.*#SHARED_DB_TOOL=relative/shared-db-tool#' \
  "$TARGET/.env.valid-shared-tool" > "$TARGET/.env"
chmod 0600 "$TARGET/.env"
if PATH="$FAKE_BIN:$PATH" bash -c '
    set -euo pipefail
    PONGDANG_TARGET="$1"
    source "$2/deploy-common.sh"
    pongdang_validate_secret_env
  ' _ "$TARGET" "$TARGET/scripts" >/dev/null 2>&1; then
  fail "relative shared DB tool was accepted"
fi
mv "$TARGET/.env.valid-shared-tool" "$TARGET/.env"

SHARED_DB_TOOL_LINK="$TARGET/scripts/shared-db-tool-link"
ln -s "$SHARED_DB_TOOL" "$SHARED_DB_TOOL_LINK"
cp "$TARGET/.env" "$TARGET/.env.valid-shared-tool-link"
sed "s#^SHARED_DB_TOOL=.*#SHARED_DB_TOOL=$SHARED_DB_TOOL_LINK#" \
  "$TARGET/.env.valid-shared-tool-link" > "$TARGET/.env"
chmod 0600 "$TARGET/.env"
if PATH="$FAKE_BIN:$PATH" bash -c '
    set -euo pipefail
    PONGDANG_TARGET="$1"
    source "$2/deploy-common.sh"
    pongdang_validate_secret_env
  ' _ "$TARGET" "$TARGET/scripts" >/dev/null 2>&1; then
  fail "symlinked shared DB tool was accepted"
fi
mv "$TARGET/.env.valid-shared-tool-link" "$TARGET/.env"

NONEXEC_SHARED_DB_TOOL="$TARGET/scripts/shared-db-tool-nonexec"
cp "$SHARED_DB_TOOL" "$NONEXEC_SHARED_DB_TOOL"
chmod 0644 "$NONEXEC_SHARED_DB_TOOL"
cp "$TARGET/.env" "$TARGET/.env.valid-shared-tool-executable"
sed "s#^SHARED_DB_TOOL=.*#SHARED_DB_TOOL=$NONEXEC_SHARED_DB_TOOL#" \
  "$TARGET/.env.valid-shared-tool-executable" > "$TARGET/.env"
chmod 0600 "$TARGET/.env"
if PATH="$FAKE_BIN:$PATH" bash -c '
    set -euo pipefail
    PONGDANG_TARGET="$1"
    source "$2/deploy-common.sh"
    pongdang_validate_secret_env
  ' _ "$TARGET" "$TARGET/scripts" >/dev/null 2>&1; then
  fail "non-executable shared DB tool was accepted"
fi
mv "$TARGET/.env.valid-shared-tool-executable" "$TARGET/.env"

cp "$TARGET/.env" "$TARGET/.env.valid-shared-tool-digest"
sed 's#^SHARED_DB_TOOL_SHA256=.*#SHARED_DB_TOOL_SHA256=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa#' \
  "$TARGET/.env.valid-shared-tool-digest" > "$TARGET/.env"
chmod 0600 "$TARGET/.env"
if PATH="$FAKE_BIN:$PATH" bash -c '
    set -euo pipefail
    PONGDANG_TARGET="$1"
    source "$2/deploy-common.sh"
    pongdang_validate_secret_env
  ' _ "$TARGET" "$TARGET/scripts" >/dev/null 2>&1; then
  fail "mismatched shared DB tool digest was accepted"
fi
mv "$TARGET/.env.valid-shared-tool-digest" "$TARGET/.env"

chmod 0775 "$SHARED_DB_TOOL"
if PATH="$FAKE_BIN:$PATH" bash -c '
    set -euo pipefail
    PONGDANG_TARGET="$1"
    source "$2/deploy-common.sh"
    pongdang_validate_secret_env
  ' _ "$TARGET" "$TARGET/scripts" >/dev/null 2>&1; then
  fail "group-writable shared DB tool was accepted"
fi
chmod 0755 "$SHARED_DB_TOOL"

cp "$SSO_SECRET_FILE" "$SSO_SECRET_FILE.valid"
printf 'short\n' > "$SSO_SECRET_FILE"
chmod 0640 "$SSO_SECRET_FILE"
if PATH="$FAKE_BIN:$PATH" bash -c '
    set -euo pipefail
    PONGDANG_TARGET="$1"
    source "$2/deploy-common.sh"
    pongdang_validate_secret_env
  ' _ "$TARGET" "$TARGET/scripts" >/dev/null 2>&1; then
  fail "short SSO edge secret was accepted"
fi
mv "$SSO_SECRET_FILE.valid" "$SSO_SECRET_FILE"

cp "$TARGET/.env" "$TARGET/.env.valid-runtime-user"
sed 's/^PONGDANG_BACKEND_RUNTIME_USER=.*/PONGDANG_BACKEND_RUNTIME_USER=1000:1000/' \
  "$TARGET/.env.valid-runtime-user" > "$TARGET/.env"
chmod 0600 "$TARGET/.env"
if PATH="$FAKE_BIN:$PATH" bash -c '
    set -euo pipefail
    PONGDANG_TARGET="$1"
    source "$2/deploy-common.sh"
    pongdang_validate_secret_env
  ' _ "$TARGET" "$TARGET/scripts" >/dev/null 2>&1; then
  fail "host UID:GID backend runtime override was accepted"
fi
mv "$TARGET/.env.valid-runtime-user" "$TARGET/.env"

cp "$TARGET/.env" "$TARGET/.env.valid-file-precedence"
sed 's/^PONGDANG_SSO_EDGE_SECRET=.*/PONGDANG_SSO_EDGE_SECRET=duplicate-private-edge-secret-value-2026/' \
  "$TARGET/.env.valid-file-precedence" > "$TARGET/.env"
chmod 0600 "$TARGET/.env"
if PATH="$FAKE_BIN:$PATH" bash -c '
    set -euo pipefail
    PONGDANG_TARGET="$1"
    source "$2/deploy-common.sh"
    pongdang_validate_secret_env
  ' _ "$TARGET" "$TARGET/scripts" >/dev/null 2>&1; then
  fail "file-backed SSO deployment retained a duplicate environment secret"
fi
mv "$TARGET/.env.valid-file-precedence" "$TARGET/.env"

if PONGDANG_FAKE_COMPOSE_VERSION=v2.24.3 PATH="$FAKE_BIN:$PATH" \
    "$TARGET/scripts/postgres-backup.sh" --target "$TARGET" >/dev/null 2>&1; then
  fail "Docker Compose 2.24.3 was accepted despite the !override contract"
fi

cp "$TARGET/.env" "$TARGET/.env.valid"
sed 's#^DATABASE_URL=.*#DATABASE_URL=postgresql://pongdang:different-password@cksDB:5432/pongdang#' \
  "$TARGET/.env.valid" > "$TARGET/.env"
chmod 0600 "$TARGET/.env"
if PATH="$FAKE_BIN:$PATH" "$TARGET/scripts/postgres-backup.sh" \
    --target "$TARGET" >/dev/null 2>&1; then
  fail "mismatched DATABASE_URL credentials were accepted"
fi
mv "$TARGET/.env.valid" "$TARGET/.env"

cp "$TARGET/.env" "$TARGET/.env.valid-host"
sed 's#^DATABASE_URL=.*#DATABASE_URL=postgresql://pongdang:0123456789abcdef@db:5432/pongdang#' \
  "$TARGET/.env.valid-host" > "$TARGET/.env"
chmod 0600 "$TARGET/.env"
if PATH="$FAKE_BIN:$PATH" "$TARGET/scripts/postgres-backup.sh" \
    --target "$TARGET" >/dev/null 2>&1; then
  fail "private Compose database host was accepted in production"
fi
mv "$TARGET/.env.valid-host" "$TARGET/.env"

PATH="$FAKE_BIN:$PATH" "$TARGET/scripts/postgres-backup.sh" \
  --target "$TARGET" >/dev/null
BACKUP_FILE="$(find "$TARGET/backups/postgres" -maxdepth 1 -type f -name 'pongdang-*.dump' -print -quit)"
[[ -n "$BACKUP_FILE" && -f "$BACKUP_FILE.sha256" ]] || fail "backup archive/checksum was not finalized"
PATH="$FAKE_BIN:$PATH" "$TARGET/scripts/postgres-restore.sh" verify \
  --target "$TARGET" \
  --backup "$BACKUP_FILE" >/dev/null

{
  printf 'RELEASE_VERSION=v1.2.3\n'
  printf 'RELEASE_COMMIT=1234567890abcdef1234567890abcdef12345678\n'
  printf 'BACKEND_IMAGE=ghcr.io/example/pongdang/backend@sha256:%064d\n' 1
  printf 'FRONTEND_IMAGE=ghcr.io/example/pongdang/frontend@sha256:%064d\n' 2
} > "$TARGET/state/current.release.env"
PATH="$FAKE_BIN:$PATH" "$TARGET/scripts/postgres-restore.sh" restore \
  --target "$TARGET" \
  --backup "$BACKUP_FILE" \
  --confirm RESTORE:pongdang-test:pongdang >/dev/null
grep -Fqx "restore --backup $BACKUP_FILE --confirm RESTORE:multtara:pongdang" \
  "$PONGDANG_FAKE_SHARED_DB_LOG" \
  || fail "restore bypassed the shared database operator boundary"
grep -Fqx 'finalize --confirm FINALIZE:multtara:pongdang_previous' \
  "$PONGDANG_FAKE_SHARED_DB_LOG" \
  || fail "restore did not finalize the retained previous database after readiness"
grep -Fqx up "$PONGDANG_FAKE_DOCKER_LOG" || fail "restore never restarted digest-pinned services"

# Build the immutable legacy bundle and cutover marker required by every
# shared-DB deploy. This target uses synthetic evidence; the dedicated cutover
# test below exercises automatic marker creation and fingerprint comparison.
cp "$TARGET/docker-compose.yml" "$TMP_ROOT/shared-docker-compose.yml"
cp "$TARGET/docker-compose.deploy.yml" "$TMP_ROOT/shared-docker-compose.deploy.yml"
cp "$TARGET/.env" "$TMP_ROOT/shared.env"
cat > "$TARGET/docker-compose.yml" <<'YAML'
services:
  db:
    image: postgres:15-alpine
    volumes:
      - postgres_data:/var/lib/postgresql/data
  backend: {}
  collector: {}
  frontend: {}
volumes:
  postgres_data:
    driver: local
YAML
cat > "$TARGET/docker-compose.deploy.yml" <<'YAML'
services:
  backend:
    image: ${BACKEND_IMAGE}
  collector:
    image: ${BACKEND_IMAGE}
  frontend:
    image: ${FRONTEND_IMAGE}
YAML
sed 's#@cksDB:5432/#@db:5432/#' "$TMP_ROOT/shared.env" > "$TARGET/.env"
chmod 0600 "$TARGET/.env"
cp "$TARGET/state/current.release.env" "$TARGET/releases/v1.2.3.env"
(
  cd "$TARGET/releases"
  sha256sum v1.2.3.env > v1.2.3.env.sha256
)
PONGDANG_FAKE_VOLUME_PROJECT=pongdang-test \
PONGDANG_FAKE_LEGACY_TARGET_CONFIG=1 \
PATH="$FAKE_BIN:$PATH" \
  "$TARGET/scripts/db-migration-rollback.sh" stage --target "$TARGET" >/dev/null
mv "$TMP_ROOT/shared-docker-compose.yml" "$TARGET/docker-compose.yml"
mv "$TMP_ROOT/shared-docker-compose.deploy.yml" "$TARGET/docker-compose.deploy.yml"
mv "$TMP_ROOT/shared.env" "$TARGET/.env"
chmod 0600 "$TARGET/.env"

TARGET_BUNDLE="$TARGET/state/pre-cksdb-rollback"
(
  cd "$TARGET_BUNDLE"
  sha256sum --check --strict SHA256SUMS.sha256 >/dev/null
  sha256sum --check --strict SHA256SUMS >/dev/null
) || fail "primary target rollback bundle integrity did not verify"
TARGET_DUMP_SHA256="$(sha256sum "$BACKUP_FILE" | awk '{print $1}')"
TARGET_BUNDLE_MANIFEST_SHA256="$(sha256sum "$TARGET_BUNDLE/SHA256SUMS" | awk '{print $1}')"
TARGET_FINGERPRINT_SHA256="$(printf 'synthetic-equal-fingerprint\n' | sha256sum | awk '{print $1}')"
{
  printf 'FORMAT=PONGDANG_CKSDB_CUTOVER_READY_V1\n'
  printf 'TARGET=%s\n' "$TARGET"
  printf 'DEPLOY_USER=pongdangtest\n'
  printf 'PROJECT_NAME=pongdang-test\n'
  printf 'DATABASE=pongdang\n'
  printf 'SOURCE_POSTGRES_MAJOR=15\n'
  printf 'TARGET_POSTGRES_MAJOR=16\n'
  printf 'FINGERPRINT_FORMAT=PONGDANG_DB_FINGERPRINT_V1\n'
  printf 'FINAL_DUMP=%s\n' "${BACKUP_FILE##*/}"
  printf 'FINAL_DUMP_SHA256=%s\n' "$TARGET_DUMP_SHA256"
  printf 'SOURCE_FINGERPRINT_SHA256=%s\n' "$TARGET_FINGERPRINT_SHA256"
  printf 'TARGET_FINGERPRINT_SHA256=%s\n' "$TARGET_FINGERPRINT_SHA256"
  printf 'CKSDB_REVISION=%s\n' "$CKSDB_REVISION"
  printf 'SHARED_DB_TOOL_SHA256=%s\n' "$SHARED_DB_TOOL_SHA256"
  printf 'ROLLBACK_BUNDLE_MANIFEST_SHA256=%s\n' "$TARGET_BUNDLE_MANIFEST_SHA256"
  printf 'CREATED_AT=2026-08-24T00:00:00Z\n'
} > "$TARGET/state/cksdb-cutover-ready.env"
chmod 0400 "$TARGET/state/cksdb-cutover-ready.env"
export PONGDANG_FAKE_VOLUME_PROJECT=pongdang-test
PATH="$FAKE_BIN:$PATH" "$TARGET/scripts/db-migration-rollback.sh" verify \
  --target "$TARGET" >/dev/null

DEPLOY_RELEASE="$RELEASE_DIR/v2.0.0.env"
{
  printf 'RELEASE_VERSION=v2.0.0\n'
  printf 'RELEASE_COMMIT=abcdef1234567890abcdef1234567890abcdef12\n'
  printf 'BACKEND_IMAGE=ghcr.io/example/pongdang/backend@sha256:%064d\n' 3
  printf 'FRONTEND_IMAGE=ghcr.io/example/pongdang/frontend@sha256:%064d\n' 4
} > "$DEPLOY_RELEASE"
(
  cd "$RELEASE_DIR"
  sha256sum "${DEPLOY_RELEASE##*/}" > "${DEPLOY_RELEASE##*/}.sha256"
)

cp "$TARGET/state/cksdb-cutover-ready.env" "$TMP_ROOT/valid-cutover-marker.env"
chmod 0600 "$TARGET/state/cksdb-cutover-ready.env"
sed 's/^TARGET_FINGERPRINT_SHA256=.*/TARGET_FINGERPRINT_SHA256=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb/' \
  "$TMP_ROOT/valid-cutover-marker.env" > "$TARGET/state/cksdb-cutover-ready.env"
chmod 0400 "$TARGET/state/cksdb-cutover-ready.env"
BACKUPS_BEFORE_BAD_MARKER="$(grep -Fxc dump "$PONGDANG_FAKE_SHARED_DB_LOG" || true)"
if PATH="$FAKE_BIN:$PATH" "$TARGET/scripts/pi-deploy.sh" deploy \
    --target "$TARGET" --release-file "$DEPLOY_RELEASE" >/dev/null 2>&1; then
  fail "deploy accepted mismatched source/target fingerprint evidence"
fi
[[ "$(grep -Fxc dump "$PONGDANG_FAKE_SHARED_DB_LOG" || true)" == "$BACKUPS_BEFORE_BAD_MARKER" ]] \
  || fail "invalid cutover marker reached the pre-change backup boundary"
mv "$TMP_ROOT/valid-cutover-marker.env" "$TARGET/state/cksdb-cutover-ready.env"
chmod 0400 "$TARGET/state/cksdb-cutover-ready.env"

cp "$TARGET_BUNDLE/scripts/deploy-common.sh" "$TMP_ROOT/valid-bundled-deploy-common.sh"
chmod 0600 "$TARGET_BUNDLE/scripts/deploy-common.sh"
printf '# tampered\n' >> "$TARGET_BUNDLE/scripts/deploy-common.sh"
BACKUPS_BEFORE_BAD_BUNDLE="$(grep -Fxc dump "$PONGDANG_FAKE_SHARED_DB_LOG" || true)"
if PATH="$FAKE_BIN:$PATH" "$TARGET/scripts/pi-deploy.sh" deploy \
    --target "$TARGET" --release-file "$DEPLOY_RELEASE" >/dev/null 2>&1; then
  fail "deploy accepted a rollback bundle whose contents changed"
fi
[[ "$(grep -Fxc dump "$PONGDANG_FAKE_SHARED_DB_LOG" || true)" == "$BACKUPS_BEFORE_BAD_BUNDLE" ]] \
  || fail "tampered rollback bundle reached the pre-change backup boundary"
mv "$TMP_ROOT/valid-bundled-deploy-common.sh" "$TARGET_BUNDLE/scripts/deploy-common.sh"
chmod 0400 "$TARGET_BUNDLE/scripts/deploy-common.sh"

BACKUPS_BEFORE_DEPLOY="$(grep -Fxc dump "$PONGDANG_FAKE_SHARED_DB_LOG" || true)"
PATH="$FAKE_BIN:$PATH" "$TARGET/scripts/pi-deploy.sh" deploy \
  --target "$TARGET" \
  --release-file "$DEPLOY_RELEASE" >/dev/null
BACKUPS_AFTER_DEPLOY="$(grep -Fxc dump "$PONGDANG_FAKE_SHARED_DB_LOG" || true)"
(( BACKUPS_AFTER_DEPLOY == BACKUPS_BEFORE_DEPLOY + 1 )) \
  || fail "deploy did not take exactly one pre-change shared database backup"
grep -Fqx 'RELEASE_VERSION=v2.0.0' "$TARGET/state/current.release.env" \
  || fail "successful deploy did not publish the selected release"
grep -Fqx 'RELEASE_VERSION=v1.2.3' "$TARGET/state/previous.release.env" \
  || fail "successful deploy did not preserve the prior release"

BACKUPS_BEFORE_ROLLBACK="$(grep -Fxc dump "$PONGDANG_FAKE_SHARED_DB_LOG" || true)"
PATH="$FAKE_BIN:$PATH" "$TARGET/scripts/pi-deploy.sh" rollback \
  --target "$TARGET" >/dev/null
BACKUPS_AFTER_ROLLBACK="$(grep -Fxc dump "$PONGDANG_FAKE_SHARED_DB_LOG" || true)"
(( BACKUPS_AFTER_ROLLBACK == BACKUPS_BEFORE_ROLLBACK + 1 )) \
  || fail "rollback did not take exactly one pre-change shared database backup"
grep -Fqx 'RELEASE_VERSION=v1.2.3' "$TARGET/state/current.release.env" \
  || fail "rollback did not atomically select the prior release"
grep -Fqx 'RELEASE_VERSION=v2.0.0' "$TARGET/state/previous.release.env" \
  || fail "rollback did not retain the release it replaced"
grep -Fqx config "$PONGDANG_FAKE_DOCKER_LOG" || fail "deploy never inspected effective Compose"
grep -Fqx pull "$PONGDANG_FAKE_DOCKER_LOG" || fail "deploy never pulled digest-pinned images"

GUARDED_RELEASE="$RELEASE_DIR/v3.0.0.env"
{
  printf 'RELEASE_VERSION=v3.0.0\n'
  printf 'RELEASE_COMMIT=abcdefabcdefabcdefabcdefabcdefabcdefabcd\n'
  printf 'BACKEND_IMAGE=ghcr.io/example/pongdang/backend@sha256:%064d\n' 5
  printf 'FRONTEND_IMAGE=ghcr.io/example/pongdang/frontend@sha256:%064d\n' 6
} > "$GUARDED_RELEASE"
(
  cd "$RELEASE_DIR"
  sha256sum "${GUARDED_RELEASE##*/}" > "${GUARDED_RELEASE##*/}.sha256"
)
BACKUPS_BEFORE_INVALID_NETWORK="$(grep -Fxc dump "$PONGDANG_FAKE_SHARED_DB_LOG" || true)"
if PONGDANG_FAKE_BAD_NETWORK=1 PATH="$FAKE_BIN:$PATH" \
    "$TARGET/scripts/pi-deploy.sh" deploy \
      --target "$TARGET" \
      --release-file "$GUARDED_RELEASE" >/dev/null 2>&1; then
  fail "deployment accepted an effective Compose without the private cksDB-multtara network"
fi
BACKUPS_AFTER_INVALID_NETWORK="$(grep -Fxc dump "$PONGDANG_FAKE_SHARED_DB_LOG" || true)"
(( BACKUPS_AFTER_INVALID_NETWORK == BACKUPS_BEFORE_INVALID_NETWORK )) \
  || fail "invalid effective Compose reached the pre-change backup boundary"

if PONGDANG_FAKE_EXTRA_SERVICE=1 PATH="$FAKE_BIN:$PATH" \
    "$TARGET/scripts/pi-deploy.sh" deploy \
      --target "$TARGET" --release-file "$GUARDED_RELEASE" >/dev/null 2>&1; then
  fail "deployment accepted an unexpected fourth service"
fi
if PONGDANG_FAKE_FRONTEND_EXTRA_NETWORK=1 PATH="$FAKE_BIN:$PATH" \
    "$TARGET/scripts/pi-deploy.sh" deploy \
      --target "$TARGET" --release-file "$GUARDED_RELEASE" >/dev/null 2>&1; then
  fail "deployment accepted a frontend network beyond default"
fi
[[ "$(grep -Fxc dump "$PONGDANG_FAKE_SHARED_DB_LOG" || true)" == "$BACKUPS_BEFORE_INVALID_NETWORK" ]] \
  || fail "invalid service/network topology reached the backup boundary"

BACKUPS_BEFORE_UNREADY_DB="$(grep -Fxc dump "$PONGDANG_FAKE_SHARED_DB_LOG" || true)"
if PONGDANG_FAKE_SHARED_DB_READY=0 PATH="$FAKE_BIN:$PATH" \
    "$TARGET/scripts/pi-deploy.sh" deploy \
      --target "$TARGET" \
      --release-file "$GUARDED_RELEASE" >/dev/null 2>&1; then
  fail "deployment continued while the shared PostgreSQL database was unavailable"
fi
BACKUPS_AFTER_UNREADY_DB="$(grep -Fxc dump "$PONGDANG_FAKE_SHARED_DB_LOG" || true)"
(( BACKUPS_AFTER_UNREADY_DB == BACKUPS_BEFORE_UNREADY_DB )) \
  || fail "unready shared database produced a backup archive"
grep -Fqx 'RELEASE_VERSION=v1.2.3' "$TARGET/state/current.release.env" \
  || fail "failed guarded deployment changed the current release"

# Exercise the one-time PG15 topology rollback boundary without touching a real
# Docker volume or database. Stage runs against the legacy shape; restore runs
# only after the target has been switched to the current shared-DB shape.
LEGACY_TARGET="$TMP_ROOT/pongdang-legacy"
mkdir -p \
  "$LEGACY_TARGET/state" \
  "$LEGACY_TARGET/releases" \
  "$LEGACY_TARGET/backups/postgres" \
  "$LEGACY_TARGET/scripts"
{
  printf 'FORMAT=PONGDANG_DEPLOYMENT_V1\n'
  printf 'TARGET=%s\n' "$LEGACY_TARGET"
  printf 'DEPLOY_USER=pongdangtest\n'
  printf 'PROJECT_NAME=pongdang-legacy\n'
} > "$LEGACY_TARGET/.pongdang-deployment"
cp \
  scripts/db-migration-rollback.sh \
  scripts/deploy-common.sh \
  scripts/pi-deploy.sh \
  scripts/postgres-backup.sh \
  scripts/postgres-prune-backups.sh \
  scripts/postgres-restore.sh \
  "$LEGACY_TARGET/scripts/"
chmod 0755 "$LEGACY_TARGET/scripts/"*.sh
cat > "$LEGACY_TARGET/docker-compose.yml" <<'YAML'
services:
  db:
    image: postgres:15-alpine
    volumes:
      - postgres_data:/var/lib/postgresql/data
  backend: {}
  collector: {}
  frontend: {}
volumes:
  postgres_data:
    driver: local
YAML
cat > "$LEGACY_TARGET/docker-compose.deploy.yml" <<'YAML'
services:
  backend:
    image: ${BACKEND_IMAGE}
  collector:
    image: ${BACKEND_IMAGE}
  frontend:
    image: ${FRONTEND_IMAGE}
YAML
{
  printf 'POSTGRES_DB=pongdang\n'
  printf 'POSTGRES_USER=pongdang\n'
  printf 'POSTGRES_PASSWORD=0123456789abcdef\n'
  printf 'DATABASE_URL=postgresql://pongdang:0123456789abcdef@db:5432/pongdang\n'
  printf 'SECRET_KEY=0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMN\n'
  printf 'ALLOWED_HOSTS=localhost\n'
  printf 'SECURE_SSL_REDIRECT=True\n'
  printf 'FRONTEND_BIND_ADDRESS=127.0.0.1\n'
  printf 'PORTFOLIO_BRANCH=main\n'
  printf 'PORTFOLIO_AUTH_MODE=sso\n'
  printf 'VITE_SSO_ENABLED=true\n'
  printf 'PONGDANG_SSO_ENABLED=True\n'
} > "$LEGACY_TARGET/.env"
chmod 0600 "$LEGACY_TARGET/.env"
LEGACY_RELEASE="$LEGACY_TARGET/releases/v4.5.6.env"
{
  printf 'RELEASE_VERSION=v4.5.6\n'
  printf 'RELEASE_COMMIT=4567890abcdef1234567890abcdef1234567890a\n'
  printf 'BACKEND_IMAGE=ghcr.io/example/pongdang/backend@sha256:%064d\n' 7
  printf 'FRONTEND_IMAGE=ghcr.io/example/pongdang/frontend@sha256:%064d\n' 8
} > "$LEGACY_RELEASE"
(
  cd "$LEGACY_TARGET/releases"
  sha256sum "${LEGACY_RELEASE##*/}" > "${LEGACY_RELEASE##*/}.sha256"
)
cp "$LEGACY_RELEASE" "$LEGACY_TARGET/state/current.release.env"

export PONGDANG_FAKE_VOLUME_PROJECT=pongdang-legacy
PONGDANG_FAKE_LEGACY_TARGET_CONFIG=1 PATH="$FAKE_BIN:$PATH" \
  scripts/db-migration-rollback.sh stage \
  --target "$LEGACY_TARGET" >/dev/null
ROLLBACK_BUNDLE="$LEGACY_TARGET/state/pre-cksdb-rollback"
[[ -d "$ROLLBACK_BUNDLE" && ! -L "$ROLLBACK_BUNDLE" ]] \
  || fail "pre-cksDB rollback bundle was not staged at the fixed path"
[[ "$(/usr/bin/stat -c '%a' "$ROLLBACK_BUNDLE")" == "700" ]] \
  || fail "rollback bundle directory is not owner-only"
[[ "$(/usr/bin/stat -c '%a' "$ROLLBACK_BUNDLE/.env")" == "600" ]] \
  || fail "rollback bundle secret is not mode 0600"
cmp -s "$LEGACY_TARGET/docker-compose.yml" "$ROLLBACK_BUNDLE/docker-compose.yml" \
  || fail "rollback bundle did not preserve the exact legacy base Compose file"
cmp -s "$LEGACY_TARGET/.env" "$ROLLBACK_BUNDLE/.env" \
  || fail "rollback bundle did not preserve the exact legacy environment"
cmp -s "$LEGACY_TARGET/scripts/deploy-common.sh" "$ROLLBACK_BUNDLE/scripts/deploy-common.sh" \
  || fail "rollback bundle did not preserve exact legacy operation scripts"
[[ "$(/usr/bin/stat -c '%a' "$ROLLBACK_BUNDLE/scripts/deploy-common.sh")" == "400" ]] \
  || fail "rollback bundle forensic script is not read-only"
(
  cd "$ROLLBACK_BUNDLE"
  sha256sum -c SHA256SUMS >/dev/null
) || fail "staged rollback bundle checksum does not verify"
if PONGDANG_FAKE_LEGACY_TARGET_CONFIG=1 PATH="$FAKE_BIN:$PATH" \
    scripts/db-migration-rollback.sh stage \
    --target "$LEGACY_TARGET" >/dev/null 2>&1; then
  fail "rollback stage overwrote an existing fixed bundle"
fi
printf 'unexpected\n' > "$ROLLBACK_BUNDLE/unexpected"
if PATH="$FAKE_BIN:$PATH" scripts/db-migration-rollback.sh restore \
    --target "$LEGACY_TARGET" \
    --confirm RESTORE:pre-cksdb-standalone:pongdang-legacy:postgres_data \
    --confirm-data-state NO_CKSDB_WRITES_SINCE_CUTOVER >/dev/null 2>&1; then
  fail "rollback restore accepted an unexpected bundle file"
fi
find "$ROLLBACK_BUNDLE/unexpected" -delete

# Simulate the completed cksDB cutover while preserving the old project volume.
cp docker-compose.yml docker-compose.deploy.yml "$LEGACY_TARGET/"
cp "$TARGET/.env" "$LEGACY_TARGET/.env"
chmod 0600 "$LEGACY_TARGET/.env"
cp \
  scripts/db-migration-rollback.sh \
  scripts/deploy-common.sh \
  scripts/postgres-backup.sh \
  scripts/postgres-prune-backups.sh \
  "$LEGACY_TARGET/scripts/"
chmod 0755 "$LEGACY_TARGET/scripts/"*.sh

PONGDANG_FAKE_CUTOVER=1 PATH="$FAKE_BIN:$PATH" \
  "$LEGACY_TARGET/scripts/db-migration-rollback.sh" cutover \
    --target "$LEGACY_TARGET" \
    --confirm CUTOVER:multtara:pg15-to-cksdb >/dev/null
CUTOVER_MARKER="$LEGACY_TARGET/state/cksdb-cutover-ready.env"
[[ -f "$CUTOVER_MARKER" && ! -L "$CUTOVER_MARKER" ]] \
  || fail "successful PG15-to-cksDB cutover did not publish its fixed marker"
[[ "$(/usr/bin/stat -c '%a' "$CUTOVER_MARKER")" == "400" ]] \
  || fail "cutover-ready marker is not mode 0400"
CUTOVER_SOURCE_FINGERPRINT="$(awk -F= '$1 == "SOURCE_FINGERPRINT_SHA256" {print $2}' "$CUTOVER_MARKER")"
CUTOVER_TARGET_FINGERPRINT="$(awk -F= '$1 == "TARGET_FINGERPRINT_SHA256" {print $2}' "$CUTOVER_MARKER")"
[[ "$CUTOVER_SOURCE_FINGERPRINT" =~ ^[0-9a-f]{64}$ \
    && "$CUTOVER_SOURCE_FINGERPRINT" == "$CUTOVER_TARGET_FINGERPRINT" ]] \
  || fail "cutover marker does not prove equal source/target fingerprints"
CUTOVER_DUMP_NAME="$(awk -F= '$1 == "FINAL_DUMP" {print $2}' "$CUTOVER_MARKER")"
(
  cd "$LEGACY_TARGET/backups/postgres"
  sha256sum --check --strict "$CUTOVER_DUMP_NAME.sha256" >/dev/null
) || fail "cutover marker final dump checksum is invalid"
grep -Fqx 'finalize --confirm FINALIZE:multtara:pongdang_previous' \
  "$PONGDANG_FAKE_SHARED_DB_LOG" \
  || fail "cutover did not finalize the isolated previous cksDB database"

ROLLBACK_CONFIRMATION='RESTORE:pre-cksdb-standalone:pongdang-legacy:postgres_data'
BACKUPS_BEFORE_TOPOLOGY_ROLLBACK="$(grep -Fxc dump "$PONGDANG_FAKE_SHARED_DB_LOG" || true)"
if PATH="$FAKE_BIN:$PATH" "$LEGACY_TARGET/scripts/db-migration-rollback.sh" restore \
    --target "$LEGACY_TARGET" \
    --confirm "$ROLLBACK_CONFIRMATION" >/dev/null 2>&1; then
  fail "topology rollback accepted a missing data-state confirmation"
fi
BACKUPS_AFTER_MISSING_CONFIRMATION="$(grep -Fxc dump "$PONGDANG_FAKE_SHARED_DB_LOG" || true)"
(( BACKUPS_AFTER_MISSING_CONFIRMATION == BACKUPS_BEFORE_TOPOLOGY_ROLLBACK )) \
  || fail "invalid topology rollback reached the shared backup boundary"

if PONGDANG_FAKE_VOLUME_CREATED_AT=2026-08-02T00:00:00Z \
    PATH="$FAKE_BIN:$PATH" "$LEGACY_TARGET/scripts/db-migration-rollback.sh" restore \
      --target "$LEGACY_TARGET" \
      --confirm "$ROLLBACK_CONFIRMATION" \
      --confirm-data-state NO_CKSDB_WRITES_SINCE_CUTOVER >/dev/null 2>&1; then
  fail "topology rollback accepted a replaced legacy volume"
fi
BACKUPS_AFTER_REPLACED_VOLUME="$(grep -Fxc dump "$PONGDANG_FAKE_SHARED_DB_LOG" || true)"
(( BACKUPS_AFTER_REPLACED_VOLUME == BACKUPS_BEFORE_TOPOLOGY_ROLLBACK )) \
  || fail "replaced legacy volume reached the shared backup boundary"

if PONGDANG_FAKE_UP_FAIL=1 PATH="$FAKE_BIN:$PATH" \
    "$LEGACY_TARGET/scripts/db-migration-rollback.sh" restore \
      --target "$LEGACY_TARGET" \
      --confirm "$ROLLBACK_CONFIRMATION" \
      --confirm-data-state NO_CKSDB_WRITES_SINCE_CUTOVER >/dev/null 2>&1; then
  fail "topology rollback reported success after legacy readiness failure"
fi
BACKUPS_AFTER_FAILED_ACTIVATION="$(grep -Fxc dump "$PONGDANG_FAKE_SHARED_DB_LOG" || true)"
(( BACKUPS_AFTER_FAILED_ACTIVATION == BACKUPS_BEFORE_TOPOLOGY_ROLLBACK + 1 )) \
  || fail "failed topology activation did not preserve exactly one current cksDB backup"
[[ ! -e "$LEGACY_TARGET/state/pre-cksdb-rollback.active" ]] \
  || fail "failed topology activation published a false active marker"
BACKUPS_BEFORE_SUCCESSFUL_ROLLBACK="$BACKUPS_AFTER_FAILED_ACTIVATION"

PATH="$FAKE_BIN:$PATH" "$LEGACY_TARGET/scripts/db-migration-rollback.sh" restore \
  --target "$LEGACY_TARGET" \
  --confirm "$ROLLBACK_CONFIRMATION" \
  --confirm-data-state NO_CKSDB_WRITES_SINCE_CUTOVER >/dev/null
BACKUPS_AFTER_TOPOLOGY_ROLLBACK="$(grep -Fxc dump "$PONGDANG_FAKE_SHARED_DB_LOG" || true)"
(( BACKUPS_AFTER_TOPOLOGY_ROLLBACK == BACKUPS_BEFORE_SUCCESSFUL_ROLLBACK + 1 )) \
  || fail "topology rollback did not take exactly one verified cksDB backup"
[[ -f "$LEGACY_TARGET/state/pre-cksdb-rollback.active" ]] \
  || fail "successful topology rollback did not publish its active marker"
grep -Fqx 'DATA_WARNING=SHARED_DB_BACKUP_NOT_APPLIED_TO_PG15' \
  "$LEGACY_TARGET/state/pre-cksdb-rollback.active" \
  || fail "topology rollback active marker hides the data-divergence boundary"
if PATH="$FAKE_BIN:$PATH" "$LEGACY_TARGET/scripts/postgres-backup.sh" \
    --target "$LEGACY_TARGET" >/dev/null 2>&1; then
  fail "normal shared-DB backup ran while the PG15 rollback was active"
fi
BACKUPS_AFTER_ACTIVE_GUARD="$(grep -Fxc dump "$PONGDANG_FAKE_SHARED_DB_LOG" || true)"
(( BACKUPS_AFTER_ACTIVE_GUARD == BACKUPS_AFTER_TOPOLOGY_ROLLBACK )) \
  || fail "active rollback guard allowed another shared database dump"
unset PONGDANG_FAKE_VOLUME_PROJECT

python3 - "$REPO_ROOT" <<'PY'
import sys
from pathlib import Path

root = Path(sys.argv[1])
overlay = (root / "docker-compose.deploy.yml").read_text()
compose = (root / "docker-compose.yml").read_text()
dev_compose = (root / "docker-compose.dev.yml").read_text()
dockerfile = (root / "backend/Dockerfile").read_text()
frontend_dockerfile = (root / "frontend/Dockerfile").read_text()
deploy = (root / "scripts/pi-deploy.sh").read_text()
deploy_common = (root / "scripts/deploy-common.sh").read_text()
backup = (root / "scripts/postgres-backup.sh").read_text()
restore = (root / "scripts/postgres-restore.sh").read_text()
db_migration_rollback = (root / "scripts/db-migration-rollback.sh").read_text()
pi_setup = (root / "scripts/pi-setup.sh").read_text()
ci = (root / ".github/workflows/ci.yml").read_text()
release = (root / ".github/workflows/release-images.yml").read_text()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")


require(overlay.count("build: !reset null") == 3, "deployment overlay does not remove every app build context")
require(overlay.count("pull_policy: always") == 3, "deployment overlay does not force image pulls")
require(overlay.count("      - multtara-db") == 2, "deployment overlay does not isolate DB access to backend and collector")
require("  multtara-db:\n    external: true\n    name: cksDB-multtara" in overlay, "deployment overlay does not pin the private DB network")
require("--no-build" in deploy and " config --format json" in deploy, "Pi deploy does not verify and prohibit builds")
require("postgres_volume_exists" not in deploy and "database_is_running" not in deploy, "Pi deploy still owns a private PostgreSQL lifecycle")
require(deploy.count("backup_before_change") == 3, "deploy and rollback do not both require pre-change backups")
require("production deployment service set must be exactly backend, collector, frontend" in deploy, "effective config validation permits extra or missing services")
require('set(services["frontend"].get("networks", {})) != {"default"}' in deploy, "effective config validation permits frontend network drift")
require("shared_network.get(\"name\") != \"cksDB-multtara\"" in deploy, "effective config validation does not enforce the private DB network")
require("--require-hashes" in dockerfile and "requirements.lock" in dockerfile, "backend image does not install the hash lock")
require("requirements.txt /tmp/requirements.txt" not in dockerfile, "backend image still installs the range manifest")
require("--no-control-socket" in dockerfile, "Gunicorn control socket conflicts with the read-only runtime")
require("USER nginx" in frontend_dockerfile and "EXPOSE 8080" in frontend_dockerfile, "frontend image is not explicitly unprivileged")
require(
    'ENTRYPOINT ["/usr/local/bin/portfolio-auth-entrypoint.sh"]' in frontend_dockerfile,
    "frontend does not replace the root image entrypoint with the auth guard",
)
require("/etc/portfolio-auth-build" in frontend_dockerfile, "frontend lacks immutable auth provenance")
require("/var/run:rw,noexec,nosuid,nodev,size=8m,mode=1777" in compose, "unprivileged Nginx PID path is not writable tmpfs")
require("unquote(encoded_password) != expected_password" in deploy_common, "database URL credentials are not cross-checked")
require('parsed.hostname != "cksdb"' in deploy_common, "production database host is not pinned to cksDB")
require("SHARED_DB_TOOL must be an absolute executable regular non-symlink file" in deploy_common, "shared DB tool path validation is incomplete")
require("SHARED_DB_TOOL_SHA256 must be a lowercase SHA-256 digest" in deploy_common, "shared DB tool digest is not pinned")
require("CKSDB_REVISION must be a full lowercase Git SHA" in deploy_common, "cksDB revision is not pinned")
require("cksdb.multtara-db" in deploy_common, "shared DB tool protocol is not pinned")
require("PONGDANG_MIN_COMPOSE_PATCH=4" in deploy_common, "Compose minimum does not cover !override")
require("\n  db:\n" not in compose and "postgres_data" not in compose, "production Compose still owns PostgreSQL")
require("image: postgres:16-alpine" in dev_compose, "development PostgreSQL is not version 16")
require("postgres16_data:/var/lib/postgresql/data" in dev_compose, "development PostgreSQL 16 is not persistent")
require("condition: service_healthy" in dev_compose, "development backend does not wait for PostgreSQL")
require(compose.count("driver: json-file") == 3, "not every production app service has bounded json-file logging")
require(compose.count("max-size: ${DOCKER_LOG_MAX_SIZE:-10m}") == 3, "production log size bounds are incomplete")
require(compose.count("pids_limit:") == 3, "production PID bounds are incomplete")
require(dev_compose.count("driver: json-file") == 1, "development PostgreSQL logging is not bounded")
require(dev_compose.count("pids_limit:") == 1, "development PostgreSQL PID usage is not bounded")
require(compose.count("cap_drop:") == 3, "application capabilities are not dropped consistently")
require(compose.count("/tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777") == 2, "backend/collector tmpfs modes are implicit")
require("/app/staticfiles:rw,noexec,nosuid,nodev,size=128m,mode=1777" in compose, "collectstatic tmpfs is not explicit and non-executable")
require("--confirm RESTORE:<project-name>:<database-name>" in restore, "restore confirmation contract is missing")
require("--skip-retention" in restore, "restore can prune its verified source backup before use")
require('"$PONGDANG_SHARED_DB_TOOL" ready' in backup, "backup does not check shared database readiness")
require('"$PONGDANG_SHARED_DB_TOOL" dump' in backup, "backup bypasses the shared DB operator")
require('"$PONGDANG_SHARED_DB_TOOL" verify --backup' in backup, "backup does not verify the shared DB archive")
require('"$PONGDANG_SHARED_DB_TOOL" restore' in restore, "restore bypasses the shared DB operator")
require('"$PONGDANG_SHARED_DB_TOOL" finalize' in restore, "restore never finalizes the retained previous database")
require("--confirm RESTORE:multtara:pongdang" in restore, "shared restore confirmation is not scoped to Multtara")
require('BUNDLE_NAME="pre-cksdb-rollback"' in db_migration_rollback, "migration rollback bundle path is not fixed")
require("rollback bundle already exists and will never be overwritten" in db_migration_rollback, "migration rollback can overwrite its secret bundle")
require('DATA_CONFIRMATION="NO_CKSDB_WRITES_SINCE_CUTOVER"' in db_migration_rollback, "migration rollback does not fail closed on data divergence")
require("postgres:15-alpine" in db_migration_rollback, "migration rollback does not pin the retained PG15 contract")
require("docker volume inspect" in db_migration_rollback and "VOLUME_CREATED_AT" in db_migration_rollback, "migration rollback does not bind the exact retained volume identity")
require('"$PONGDANG_TARGET/scripts/postgres-backup.sh"' in db_migration_rollback and "--skip-retention" in db_migration_rollback, "migration rollback does not create a verified shared-DB backup first")
require("--no-build" in db_migration_rollback and "--remove-orphans" in db_migration_rollback and "--wait" in db_migration_rollback, "migration rollback activation is not bounded to the staged release")
require("pre-cksdb-rollback.active" in deploy_common, "normal operations do not fail closed after PG15 rollback activation")
require("pongdang_validate_cutover_ready" in deploy, "deploy is not gated by the cutover-ready evidence marker")
require("SHA256SUMS.sha256" in db_migration_rollback and "--check --strict" in db_migration_rollback, "rollback bundle manifest is not independently checksum-pinned")
require("write_fingerprint_sql" in db_migration_rollback and "row-count" in db_migration_rollback, "cutover lacks deterministic schema and exact row-count fingerprints")
require("row_number() OVER (" in db_migration_rollback, "cross-major column fingerprint does not preserve logical ordinals")
require("'::character varying::text'" in db_migration_rollback, "cross-major constraint fingerprint does not normalize PostgreSQL 16 deparsing")
require("']::text[]'" in db_migration_rollback, "cross-major constraint fingerprint does not normalize PostgreSQL 15 deparsing")
require("AS collation_record" in db_migration_rollback, "fingerprint does not use a PostgreSQL 15-safe collation alias")
require("FINALIZE:multtara:pongdang_previous" in db_migration_rollback, "cutover marker can precede cksDB finalize")
require("scripts/db-migration-rollback.sh" in pi_setup, "Pi setup does not install the migration rollback tool")
require("scripts/test-ops-config.sh" in ci, "CI does not run the operations contract")
require("platforms: linux/arm64" in release, "release workflow does not target ARM64")
require(release.count("provenance: mode=max") == 2, "release provenance is incomplete")
require(release.count("sbom: true") == 2, "release SBOM attestations are incomplete")
require("BACKEND_IMAGE=%s@%s" in release and "FRONTEND_IMAGE=%s@%s" in release, "release bundle is not digest-pinned")
require("scripts/db-migration-rollback.sh" in release, "release bundle cannot stage the pre-change rollback artifact")
prepare_job = release[release.index("  prepare:\n") : release.index("  quality-gate:\n")]
deploy_job = release[release.index("  deploy:\n") :]
require("github.event_name == 'workflow_dispatch' && inputs.deploy_to_server" in deploy_job, "release deploy is not explicitly operator-gated")
require(
    'git merge-base --is-ancestor "$GITHUB_SHA" refs/remotes/origin/main' in prepare_job,
    "release revision is not constrained to origin/main history",
)
require("timeout-minutes: 60" in deploy_job, "release deploy timeout is not 60 minutes")
print("deployment static contract: PASS")
PY

echo "deployment tool integration: PASS"
