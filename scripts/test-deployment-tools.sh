#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$REPO_ROOT"

bash -n \
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

# Exercise the backup and restore control flow with a deterministic Docker CLI
# boundary. The fake preserves command/stream behavior but does not claim a real
# PostgreSQL recovery; that remains an ARM64 drill obligation.
cp \
  scripts/deploy-common.sh \
  scripts/pi-deploy.sh \
  scripts/postgres-backup.sh \
  scripts/postgres-prune-backups.sh \
  scripts/postgres-restore.sh \
  "$TARGET/scripts/"
chmod +x "$TARGET/scripts/"*.sh
cp docker-compose.yml docker-compose.deploy.yml "$TARGET/"
{
  printf 'POSTGRES_DB=pongdang_test\n'
  printf 'POSTGRES_USER=pongdang\n'
  printf 'POSTGRES_PASSWORD=0123456789abcdef\n'
  printf 'DATABASE_URL=postgresql://pongdang:0123456789abcdef@db:5432/pongdang_test\n'
  printf 'SECRET_KEY=0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMN\n'
  printf 'ALLOWED_HOSTS=localhost\n'
  printf 'SECURE_SSL_REDIRECT=True\n'
  printf 'FRONTEND_BIND_ADDRESS=127.0.0.1\n'
  printf 'ROUTING_MATRIX_URL=\n'
  printf 'BACKUP_RETENTION_DAYS=14\n'
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
  %a) echo 600 ;;
  %u) echo 1000 ;;
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
if [[ " $* " == *" compose version --short "* ]]; then
  echo "${PONGDANG_FAKE_COMPOSE_VERSION:-v2.24.4}"
  exit 0
fi
for token in "$@"; do
  case "$token" in
    pg_dump)
      echo pg_dump >> "$PONGDANG_FAKE_DOCKER_LOG"
      printf 'FAKE_CUSTOM_ARCHIVE\n'
      exit 0
      ;;
    pg_restore)
      if [[ " $* " == *" --list "* ]]; then
        echo pg_restore-list >> "$PONGDANG_FAKE_DOCKER_LOG"
        cat >/dev/null
        printf '1; 0 0 TABLE public test pongdang\n'
      else
        echo pg_restore-restore >> "$PONGDANG_FAKE_DOCKER_LOG"
        cat >/dev/null
      fi
      exit 0
      ;;
    pg_isready)
      echo pg_isready >> "$PONGDANG_FAKE_DOCKER_LOG"
      exit 0
      ;;
    psql)
      echo psql >> "$PONGDANG_FAKE_DOCKER_LOG"
      cat >/dev/null
      exit 0
      ;;
    config)
      echo config >> "$PONGDANG_FAKE_DOCKER_LOG"
      printf '{"services":{"backend":{"image":"%s","pull_policy":"always"},"collector":{"image":"%s","pull_policy":"always"},"frontend":{"image":"%s","pull_policy":"always","ports":[{"host_ip":"127.0.0.1","published":"8080","target":8080}]}}}\n' \
        "$BACKEND_IMAGE" "$BACKEND_IMAGE" "$FRONTEND_IMAGE"
      exit 0
      ;;
    ps)
      if [[ "${PONGDANG_FAKE_DB_RUNNING:-1}" == "1" ]]; then
        echo db
      fi
      exit 0
      ;;
    volume)
      case "${2:-}" in
        inspect)
          [[ "${PONGDANG_FAKE_VOLUME_EXISTS:-0}" == "1" ]]
          ;;
        ls)
          if [[ "${PONGDANG_FAKE_VOLUME_EXISTS:-0}" == "1" ]]; then
            echo pongdang-test_postgres_data
          fi
          ;;
        *) exit 1 ;;
      esac
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
      exit 0
      ;;
  esac
done
exit 0
SH
chmod +x "$FAKE_BIN/"*
export PONGDANG_FAKE_DOCKER_LOG="$TMP_ROOT/fake-docker.log"
: > "$PONGDANG_FAKE_DOCKER_LOG"

if PONGDANG_FAKE_COMPOSE_VERSION=v2.24.3 PATH="$FAKE_BIN:$PATH" \
    "$TARGET/scripts/postgres-backup.sh" --target "$TARGET" >/dev/null 2>&1; then
  fail "Docker Compose 2.24.3 was accepted despite the !override contract"
fi

cp "$TARGET/.env" "$TARGET/.env.valid"
sed 's#^DATABASE_URL=.*#DATABASE_URL=postgresql://pongdang:different-password@db:5432/pongdang_test#' \
  "$TARGET/.env.valid" > "$TARGET/.env"
chmod 0600 "$TARGET/.env"
if PATH="$FAKE_BIN:$PATH" "$TARGET/scripts/postgres-backup.sh" \
    --target "$TARGET" >/dev/null 2>&1; then
  fail "mismatched DATABASE_URL credentials were accepted"
fi
mv "$TARGET/.env.valid" "$TARGET/.env"

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
  --confirm RESTORE:pongdang-test:pongdang_test >/dev/null
grep -Fqx psql "$PONGDANG_FAKE_DOCKER_LOG" || fail "restore never replaced the database"
grep -Fqx pg_restore-restore "$PONGDANG_FAKE_DOCKER_LOG" || fail "restore never streamed the archive"
grep -Fqx up "$PONGDANG_FAKE_DOCKER_LOG" || fail "restore never restarted digest-pinned services"

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
PATH="$FAKE_BIN:$PATH" "$TARGET/scripts/pi-deploy.sh" deploy \
  --target "$TARGET" \
  --release-file "$DEPLOY_RELEASE" >/dev/null
grep -Fqx 'RELEASE_VERSION=v2.0.0' "$TARGET/state/current.release.env" \
  || fail "successful deploy did not publish the selected release"
grep -Fqx 'RELEASE_VERSION=v1.2.3' "$TARGET/state/previous.release.env" \
  || fail "successful deploy did not preserve the prior release"

PATH="$FAKE_BIN:$PATH" "$TARGET/scripts/pi-deploy.sh" rollback \
  --target "$TARGET" >/dev/null
grep -Fqx 'RELEASE_VERSION=v1.2.3' "$TARGET/state/current.release.env" \
  || fail "rollback did not atomically select the prior release"
grep -Fqx 'RELEASE_VERSION=v2.0.0' "$TARGET/state/previous.release.env" \
  || fail "rollback did not retain the release it replaced"
grep -Fqx config "$PONGDANG_FAKE_DOCKER_LOG" || fail "deploy never inspected effective Compose"
grep -Fqx pull "$PONGDANG_FAKE_DOCKER_LOG" || fail "deploy never pulled digest-pinned images"

STOPPED_RELEASE="$RELEASE_DIR/v3.0.0.env"
{
  printf 'RELEASE_VERSION=v3.0.0\n'
  printf 'RELEASE_COMMIT=abcdefabcdefabcdefabcdefabcdefabcdefabcd\n'
  printf 'BACKEND_IMAGE=ghcr.io/example/pongdang/backend@sha256:%064d\n' 5
  printf 'FRONTEND_IMAGE=ghcr.io/example/pongdang/frontend@sha256:%064d\n' 6
} > "$STOPPED_RELEASE"
(
  cd "$RELEASE_DIR"
  sha256sum "${STOPPED_RELEASE##*/}" > "${STOPPED_RELEASE##*/}.sha256"
)
if PONGDANG_FAKE_DB_RUNNING=0 PATH="$FAKE_BIN:$PATH" \
    "$TARGET/scripts/pi-deploy.sh" deploy \
      --target "$TARGET" \
      --release-file "$STOPPED_RELEASE" >/dev/null 2>&1; then
  fail "stopped existing database was treated as a first deployment"
fi

mv "$TARGET/state/current.release.env" "$TARGET/state/current.release.saved"
mv "$TARGET/state/previous.release.env" "$TARGET/state/previous.release.saved"
if PONGDANG_FAKE_DB_RUNNING=0 PONGDANG_FAKE_VOLUME_EXISTS=1 PATH="$FAKE_BIN:$PATH" \
    "$TARGET/scripts/pi-deploy.sh" deploy \
      --target "$TARGET" \
      --release-file "$STOPPED_RELEASE" >/dev/null 2>&1; then
  fail "existing PostgreSQL volume without release state was treated as first deployment"
fi
mv "$TARGET/state/current.release.saved" "$TARGET/state/current.release.env"
mv "$TARGET/state/previous.release.saved" "$TARGET/state/previous.release.env"

python3 - "$REPO_ROOT" <<'PY'
import sys
from pathlib import Path

root = Path(sys.argv[1])
overlay = (root / "docker-compose.deploy.yml").read_text()
compose = (root / "docker-compose.yml").read_text()
dockerfile = (root / "backend/Dockerfile").read_text()
frontend_dockerfile = (root / "frontend/Dockerfile").read_text()
deploy = (root / "scripts/pi-deploy.sh").read_text()
restore = (root / "scripts/postgres-restore.sh").read_text()
ci = (root / ".github/workflows/ci.yml").read_text()
release = (root / ".github/workflows/release-images.yml").read_text()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")


require(overlay.count("build: !reset null") == 3, "deployment overlay does not remove every app build context")
require(overlay.count("pull_policy: always") == 3, "deployment overlay does not force image pulls")
require("--no-build" in deploy and " config --format json" in deploy, "Pi deploy does not verify and prohibit builds")
require("postgres_volume_exists" in deploy and "prior release state or PostgreSQL volume exists" in deploy, "stopped existing database can bypass the pre-change backup")
require("--require-hashes" in dockerfile and "requirements.lock" in dockerfile, "backend image does not install the hash lock")
require("requirements.txt /tmp/requirements.txt" not in dockerfile, "backend image still installs the range manifest")
require("USER nginx" in frontend_dockerfile and "EXPOSE 8080" in frontend_dockerfile, "frontend image is not explicitly unprivileged")
require("ENTRYPOINT []" in frontend_dockerfile, "frontend still depends on the root image entrypoint")
require("/var/run:rw,noexec,nosuid,nodev,size=8m,mode=1777" in compose, "unprivileged Nginx PID path is not writable tmpfs")
require("unquote(encoded_password) != expected_password" in (root / "scripts/deploy-common.sh").read_text(), "database URL credentials are not cross-checked")
require("PONGDANG_MIN_COMPOSE_PATCH=4" in (root / "scripts/deploy-common.sh").read_text(), "Compose minimum does not cover !override")
require(compose.count("driver: json-file") == 4, "not every service has bounded json-file logging")
require(compose.count("max-size: ${DOCKER_LOG_MAX_SIZE:-10m}") == 4, "log size bounds are incomplete")
require(compose.count("pids_limit:") == 4, "PID bounds are incomplete")
require(compose.count("cap_drop:") == 3, "application capabilities are not dropped consistently")
require(compose.count("/tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777") == 2, "backend/collector tmpfs modes are implicit")
require("/app/staticfiles:rw,noexec,nosuid,nodev,size=128m,mode=1777" in compose, "collectstatic tmpfs is not explicit and non-executable")
require("--confirm RESTORE:<project-name>:<database-name>" in restore, "restore confirmation contract is missing")
require("--skip-retention" in restore, "restore can prune its verified source backup before use")
require("scripts/test-ops-config.sh" in ci, "CI does not run the operations contract")
require("platforms: linux/arm64" in release, "release workflow does not target ARM64")
require(release.count("provenance: mode=max") == 2, "release provenance is incomplete")
require(release.count("sbom: true") == 2, "release SBOM attestations are incomplete")
require("BACKEND_IMAGE=%s@%s" in release and "FRONTEND_IMAGE=%s@%s" in release, "release bundle is not digest-pinned")
print("deployment static contract: PASS")
PY

echo "deployment tool integration: PASS"
