#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$REPO_ROOT"

bash -n \
  scripts/db-migration-rollback.sh \
  scripts/setup-worktrees.sh \
  scripts/test-setup-worktrees.sh \
  scripts/portfolio-auth-mode.sh \
  scripts/test-portfolio-auth-mode.sh

python3 - "$REPO_ROOT" <<'PY'
from __future__ import annotations

import re
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
compose = (root / "docker-compose.yml").read_text()
dev_compose = (root / "docker-compose.dev.yml").read_text()
deploy_compose = (root / "docker-compose.deploy.yml").read_text()
nginx = (root / "frontend/nginx.conf").read_text()
frontend_dockerfile = (root / "frontend/Dockerfile").read_text()
backend_dockerfile = (root / "backend/Dockerfile").read_text()
auth_entrypoint = (root / "scripts/portfolio-auth-entrypoint.sh").read_text()
root_urls = (root / "backend/config/urls.py").read_text()
frontend_package = json.loads((root / "frontend/package.json").read_text())
wsgi = (root / "backend/config/wsgi.py").read_text()
asgi = (root / "backend/config/asgi.py").read_text()
manage = (root / "backend/manage.py").read_text()
ci_workflow = (root / ".github/workflows/ci.yml").read_text()
release_workflow = (root / ".github/workflows/release-images.yml").read_text()
vite_config = (root / "frontend/vite.config.js").read_text()
app_source = (root / "frontend/src/App.jsx").read_text()
index_html = (root / "frontend/index.html").read_text()
api_source = (root / "frontend/src/services/api.js").read_text()
profile_source = (root / "frontend/src/pages/ProfilePage.jsx").read_text()
readme = (root / "README.md").read_text()
agents = (root / "AGENTS.md").read_text()
operations_runbook = (root / "docs/operations-runbook.md").read_text()
dockerignore = (root / ".dockerignore").read_text()
deploy_common = (root / "scripts/deploy-common.sh").read_text()
pi_deploy = (root / "scripts/pi-deploy.sh").read_text()
postgres_backup = (root / "scripts/postgres-backup.sh").read_text()
postgres_restore = (root / "scripts/postgres-restore.sh").read_text()
db_migration_rollback = (root / "scripts/db-migration-rollback.sh").read_text()
pi_setup = (root / "scripts/pi-setup.sh").read_text()

compile(wsgi, str(root / "backend/config/wsgi.py"), "exec")
compile(asgi, str(root / "backend/config/asgi.py"), "exec")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def location_block(path: str) -> str:
    marker = f"    location {path} {{"
    start = nginx.find(marker)
    require(start >= 0, f"missing Nginx location {path}")
    end = nginx.find("\n    }", start)
    require(end >= 0, f"unterminated Nginx location {path}")
    return nginx[start:end]


require("DATABASE_URL=postgresql://${POSTGRES_" not in compose, "raw DB credentials are assembled into a URL")
require(
    re.search(r"^  db:\s*$", compose, flags=re.MULTILINE) is None,
    "production Compose still defines an application PostgreSQL service",
)
require("postgres_data" not in compose, "production Compose still owns a PostgreSQL volume")
require('user: "${PONGDANG_BACKEND_RUNTIME_USER:-pongdang:root}"' in compose, "backend must retain a non-root UID with the rootless private group")
require(compose.count("DATABASE_URL: ${DATABASE_URL:?") == 2, "backend and collector must receive DATABASE_URL")
require(compose.count("APPLICATION_BASE_PATH: ${APPLICATION_BASE_PATH:-}") == 2, "application base path must reach both Django processes")
require(compose.count("CORS_ALLOWED_ORIGINS: ${CORS_ALLOWED_ORIGINS:-}") == 2, "CORS setting is not passed to both Django processes")
require(compose.count("SECURE_SSL_REDIRECT: ${SECURE_SSL_REDIRECT:-True}") == 2, "SSL redirect setting is not passed to both Django processes")
require(compose.count("ROUTING_MATRIX_URL: ${ROUTING_MATRIX_URL:-}") == 2, "routing URL must reach backend and collector only")
require("--route-matrix-interval=${ROUTE_MATRIX_INTERVAL_SECONDS:-86400}" in compose, "collector route refresh cadence is not wired")
require("check_condition_pipeline_health" in compose and '- "900"' in compose, "collector freshness healthcheck is missing")
require(deploy_compose.count("build: !reset null") == 3, "deployment overlay leaves a local build context")
require(deploy_compose.count("pull_policy: always") == 3, "deployment overlay lacks pull_policy")
require(deploy_compose.count("      - multtara-db") == 2, "private DB network must reach backend and collector only")
require("  multtara-db:\n    external: true\n    name: cksDB-multtara" in deploy_compose, "Multtara DB network is not fixed and external")

require("image: postgres:16-alpine" in dev_compose, "local development PostgreSQL is not version 16")
require("postgres16_data:/var/lib/postgresql/data" in dev_compose, "local PostgreSQL 16 data is not persistent")
require(
    "depends_on:\n      db:\n        condition: service_healthy" in dev_compose,
    "local backend does not wait for its PostgreSQL service",
)
require("postgres16_data:\n    driver: local" in dev_compose, "local PostgreSQL 16 volume declaration is missing")
require("LOCAL_DATABASE_URL:?LOCAL_DATABASE_URL is required" in dev_compose, "local database URL is not explicit")

require('PONGDANG_SHARED_DB_TOOL="$(pongdang_env_value "$file" SHARED_DB_TOOL)"' in deploy_common, "shared DB tool is not loaded from the protected deployment environment")
require('parsed.hostname != "cksdb"' in deploy_common, "production DATABASE_URL is not pinned to cksDB")
require("SHARED_DB_TOOL must be an absolute executable regular non-symlink file" in deploy_common, "shared DB tool path validation is incomplete")
require("SHARED_DB_TOOL_SHA256 must be a lowercase SHA-256 digest" in deploy_common, "shared DB tool digest is not pinned")
require("CKSDB_REVISION must be a full lowercase Git SHA" in deploy_common, "cksDB revision is not pinned")
require("cksdb.multtara-db" in deploy_common, "shared DB tool protocol is not pinned")
require('"$PONGDANG_SHARED_DB_TOOL" ready' in postgres_backup, "backup does not verify shared PostgreSQL readiness")
require('"$PONGDANG_SHARED_DB_TOOL" dump' in postgres_backup, "backup bypasses the shared DB operator boundary")
require('"$PONGDANG_SHARED_DB_TOOL" verify --backup' in postgres_backup, "backup archive is not verified by the shared DB operator")
require('"$PONGDANG_SHARED_DB_TOOL" restore' in postgres_restore, "restore bypasses the shared DB operator boundary")
require('"$PONGDANG_SHARED_DB_TOOL" finalize' in postgres_restore, "restore never finalizes the retained previous database")
require("production deployment service set must be exactly backend, collector, frontend" in pi_deploy, "effective deployment validation permits extra or missing services")
require('set(services["frontend"].get("networks", {})) != {"default"}' in pi_deploy, "effective deployment permits frontend network drift")
require("shared_network.get(\"name\") != \"cksDB-multtara\"" in pi_deploy, "effective deployment validation does not enforce the private DB network")
require(pi_deploy.count("backup_before_change") == 3, "deploy and rollback must both take a pre-change backup")
require('BUNDLE_NAME="pre-cksdb-rollback"' in db_migration_rollback, "pre-cksDB rollback bundle path is not fixed")
require("rollback bundle already exists and will never be overwritten" in db_migration_rollback, "pre-cksDB rollback bundle can be overwritten")
require('DATA_CONFIRMATION="NO_CKSDB_WRITES_SINCE_CUTOVER"' in db_migration_rollback, "topology rollback can ignore post-cutover writes")
require("postgres:15-alpine" in db_migration_rollback, "topology rollback does not validate PostgreSQL 15")
require("docker volume inspect" in db_migration_rollback and "VOLUME_CREATED_AT" in db_migration_rollback, "topology rollback does not bind the retained volume identity")
require("--no-build" in db_migration_rollback and "--remove-orphans" in db_migration_rollback and "--wait" in db_migration_rollback, "topology rollback activation can drift from the staged release")
require("pre-cksdb-rollback.active" in deploy_common, "normal shared-DB operations ignore an active standalone rollback")
require("pongdang_validate_cutover_ready" in pi_deploy, "shared-DB deploy is not gated by cutover evidence")
require("SOURCE_FINGERPRINT_SHA256" in deploy_common and "TARGET_FINGERPRINT_SHA256" in deploy_common, "cutover marker does not bind both database fingerprints")
require("SHA256SUMS.sha256" in db_migration_rollback and "--check --strict" in db_migration_rollback, "rollback bundle manifest lacks an independent strict checksum")
require("write_fingerprint_sql" in db_migration_rollback and "row-count" in db_migration_rollback, "cutover does not compute deterministic schema and exact row-count evidence")
require("row_number() OVER (" in db_migration_rollback, "cross-major column fingerprint does not preserve logical ordinals")
require("'::character varying::text'" in db_migration_rollback, "cross-major constraint fingerprint does not normalize PostgreSQL 16 deparsing")
require("']::text[]'" in db_migration_rollback, "cross-major constraint fingerprint does not normalize PostgreSQL 15 deparsing")
require("AS collation_record" in db_migration_rollback, "fingerprint does not use a PostgreSQL 15-safe collation alias")
require("--interactive" in db_migration_rollback[db_migration_rollback.index("target_psql()") : db_migration_rollback.index("fingerprint_target_database()")], "target fingerprint container cannot consume SQL from stdin")
require("FINALIZE:multtara:pongdang_previous" in db_migration_rollback, "cutover can publish evidence before cksDB finalize")
require("scripts/db-migration-rollback.sh" in pi_setup, "Pi setup does not install the migration rollback tool")
require("scripts/db-migration-rollback.sh" in release_workflow, "release bundle cannot stage the pre-change rollback artifact")
require("NO_CKSDB_WRITES_SINCE_CUTOVER" in operations_runbook, "operations runbook hides the rollback data-divergence boundary")
require("/opt/pongdang-multtara" in operations_runbook and "--deploy-user cks" in operations_runbook and "--project-name pongdang-multtara" in operations_runbook, "operations examples do not match the real Multtara target identity")
require("**/state/pre-cksdb-rollback/" in dockerignore, "secret rollback bundle can enter a Docker build context")
require("**/state/cksdb-cutover-ready.env" in dockerignore, "runtime cutover evidence can enter a Docker build context")

for port in ("DEV_POSTGRES_PORT", "DEV_BACKEND_PORT", "DEV_FRONTEND_PORT"):
    require(f"${{DEV_BIND_ADDRESS:-127.0.0.1}}:${{{port}" in dev_compose, f"{port} is not loopback-bound")
require("ports: !override" in dev_compose, "development frontend does not replace production ports")
require("http://127.0.0.1:5173/" in dev_compose, "development frontend healthcheck does not probe Vite")
require("listen 8080;" in nginx, "production Nginx does not use an unprivileged port")
require(
    "USER nginx" in frontend_dockerfile
    and 'ENTRYPOINT ["/usr/local/bin/portfolio-auth-entrypoint.sh"]' in frontend_dockerfile,
    "production Nginx runtime does not use the unprivileged auth guard",
)
require("ARG VITE_APP_BASE_PATH=/" in frontend_dockerfile, "frontend image does not accept an application base path")
require("ARG VITE_CSRF_COOKIE_NAME=pongdang_csrftoken" in frontend_dockerfile, "frontend image does not pin the isolated CSRF cookie")
require("ARG VITE_SSO_ENABLED" in frontend_dockerfile, "frontend image cannot adapt the legacy SSO flag")
require("org.opencontainers.image.ref.name" in frontend_dockerfile, "frontend branch audit label is missing")
require("io.bonifacio.portfolio.auth-mode" in frontend_dockerfile, "frontend auth-mode audit label is missing")
for name, content in (("backend", backend_dockerfile), ("frontend", frontend_dockerfile)):
    require(
        '${PORTFOLIO_BRANCH#refs/heads/}' in content,
        f"{name} Docker build does not normalize refs/heads branches",
    )
    require(
        "/etc/portfolio-auth-build" in content and "chmod 0444" in content,
        f"{name} image lacks an immutable auth build contract",
    )
require("portfolio-auth-mode.sh contract" in auth_entrypoint, "frontend entrypoint bypasses the resolver")
require("if not settings.PONGDANG_SSO_ENABLED" in root_urls, "SSO mode still registers Django admin")
require("dockerfile: frontend/Dockerfile" in compose, "frontend does not use the guarded root context")
require("**" in dockerignore and "!frontend/**" in dockerignore, "root frontend context is not allowlisted")
require("!scripts/portfolio-auth-mode.sh" in dockerignore, "root context omits the canonical resolver")
require("file: ${{ matrix.dockerfile }}" in ci_workflow, "CI image matrix ignores its Dockerfile")
require("file: ./frontend/Dockerfile" in release_workflow, "release frontend Dockerfile is not explicit")
for command in ("dev", "preview"):
    require("PORTFOLIO_AUTH_MODE=local" in frontend_package["scripts"][command], f"{command} is not local-only")
    require("../scripts/portfolio-auth-mode.sh exec --" in frontend_package["scripts"][command], f"{command} bypasses the resolver")
require("base: environment.VITE_APP_BASE_PATH || '/'" in vite_config, "Vite base path is not configurable")
require("<BrowserRouter basename={routerBaseName}>" in app_source, "React routes do not honor the Vite base path")
require(index_html.count("%BASE_URL%") >= 3, "HTML metadata/assets are not rooted at the Vite base path")
require("VITE_CSRF_COOKIE_NAME" in api_source and "pongdang_csrftoken" in api_source, "Axios CSRF cookie does not match Django")
require("VITE_SSO_ENABLED" in api_source, "frontend runtime does not expose the SSO mode")
logout_handler = profile_source[
    profile_source.index("  const handleLogout = async () => {") :
    profile_source.index("  const submitProfile = async", profile_source.index("  const handleLogout = async () => {"))
]
require(
    "finally {" in logout_handler
    and logout_handler.index("window.location.assign") > logout_handler.index("finally {"),
    "central SSO logout is not guaranteed after the local logout attempt",
)
require("PONGDANG_SSO_ENABLED: ${PONGDANG_SSO_ENABLED:?" in compose, "backend SSO adapter is not fail-closed")
require(compose.count("PORTFOLIO_BRANCH: ${PORTFOLIO_BRANCH:?") == 5, "canonical branch is not injected into every app build/runtime")
require(compose.count("PORTFOLIO_AUTH_MODE: ${PORTFOLIO_AUTH_MODE:?") == 5, "canonical auth mode is not injected into every app build/runtime")
require("PONGDANG_RUNTIME_ROLE: web" in compose, "backend web runtime role is not explicit")
require("PONGDANG_RUNTIME_ROLE: worker" in compose, "collector worker runtime role is not explicit")
require("PONGDANG_SSO_EDGE_SECRET: ${PONGDANG_SSO_EDGE_SECRET:-}" in compose, "backend SSO edge secret is not wired")
require("PONGDANG_SSO_EDGE_SECRET_FILE: ${PONGDANG_SSO_EDGE_SECRET_FILE:-}" in compose, "backend SSO secret file is not wired")
require(
    len(re.findall(r"^\s+PONGDANG_SSO_EDGE_SECRET:", compose, flags=re.MULTILINE)) == 1,
    "SSO edge secret reaches a service other than the backend",
)
require(
    len(re.findall(r"^\s+PONGDANG_SSO_EDGE_SECRET_FILE:", compose, flags=re.MULTILINE)) == 1,
    "SSO secret file reaches a service other than the backend",
)
require("source: ${PONGDANG_SSO_EDGE_SECRET_MOUNT:-/dev/null}" in compose, "backend lacks the optional private SSO secret bind")
require("target: /run/secrets/pongdang_sso_edge_secret" in compose, "backend SSO secret bind target changed")
require(nginx.count("proxy_set_header Remote-User $http_remote_user;") >= 2, "frontend proxy does not preserve trusted SSO identity")
require(nginx.count("proxy_set_header Remote-Groups $http_remote_groups;") >= 2, "frontend proxy does not preserve central role groups")
require(nginx.count("proxy_set_header X-Portfolio-Edge-Secret $http_x_portfolio_edge_secret;") >= 2, "frontend proxy does not forward the private edge credential")
require("127.0.0.1}:${FRONTEND_PORT:-8080}:8080" in compose, "production Nginx mapping does not target port 8080")
require(dev_compose.count("DJANGO_SETTINGS_MODULE: config.settings.dev") == 2, "backend and collector do not share the explicit development settings path")
for path in ("= /admin", "/admin/"):
    block = location_block(path)
    require("return 404;" in block, f"{path} is not fail-closed")
    require("proxy_pass" not in block, f"{path} still exposes Django admin")

for path in ("/static/",):
    block = location_block(path)
    for directive in (
        "proxy_pass http://backend:8000;",
        "proxy_set_header Host $host;",
        "proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;",
        "proxy_connect_timeout 5s;",
        "proxy_read_timeout 30s;",
        "proxy_send_timeout 30s;",
    ):
        require(directive in block, f"{path} lacks {directive}")

prod_default = 'os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")'
dev_default = 'os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")'
require(prod_default in wsgi and prod_default in asgi, "WSGI/ASGI do not fail closed to production settings")
require(dev_default in manage, "manage.py is not the explicit development entry point")
require("  workflow_call:\n" in ci_workflow, "CI is not reusable as a release quality gate")
require("      - main\n" in ci_workflow and "      - dev\n" in ci_workflow, "main/dev CI triggers are incomplete")
require(
    "  quality-gate:\n" in release_workflow
    and "uses: ./.github/workflows/ci.yml" in release_workflow,
    "release workflow does not invoke the full CI quality gate",
)
require(
    release_workflow.count("needs: [prepare, quality-gate]") == 2,
    "release images can be published before the quality gate succeeds",
)
prepare_job = release_workflow[
    release_workflow.index("  prepare:\n") : release_workflow.index("  quality-gate:\n")
]
deploy_job = release_workflow[release_workflow.index("  deploy:\n") :]
require("fetch-depth: 0" in prepare_job, "release ancestry proof lacks complete history")
require(
    'git merge-base --is-ancestor "$GITHUB_SHA" refs/remotes/origin/main' in prepare_job,
    "release tag revision is not constrained to origin/main history",
)
require(
    'if [[ "$tagged_commit" != "$GITHUB_SHA" ]]' in prepare_job,
    "release tag is not constrained to the exact workflow revision",
)
require(
    "timeout-minutes: 60" in deploy_job,
    "restricted server deployment timeout must remain 60 minutes",
)
for document_name, document in (
    ("README", readme),
    ("AGENTS", agents),
    ("operations runbook", operations_runbook),
):
    require(
        "origin/main" in document,
        f"{document_name} does not describe the main-bound release contract",
    )
    require(
        "/sso/admin/" in document and "404" in document,
        f"{document_name} does not describe the centralized admin contract",
    )
require("VITE_APP_BASE_PATH=/multtara/" in release_workflow, "release assets are not built for the portfolio subpath")
require("VITE_API_BASE_URL=/multtara/api/v1/" in release_workflow, "release API is not isolated below the portfolio subpath")
require("VITE_SSO_ENABLED=true" in release_workflow, "release frontend does not enable portfolio SSO")
require("PORTFOLIO_BRANCH: main" in release_workflow, "release branch is not pinned to main")
require("PORTFOLIO_AUTH_MODE: sso" in release_workflow, "release auth mode is not pinned to SSO")
require("deploy multtara $DEPLOY_VERSION $DEPLOY_SHA $BACKEND_DIGEST $FRONTEND_DIGEST" in release_workflow, "release workflow does not request the restricted Multtara deployment")
require("github.event_name == 'workflow_dispatch' && inputs.deploy_to_server" in release_workflow, "tag pushes can still mutate the production server automatically")

# Ensure the override tag is attached only to the intended ports declaration.
require(len(re.findall(r"^\s+ports: !override$", dev_compose, flags=re.MULTILINE)) == 1, "unexpected !override usage")
print("static ops contract: PASS")
PY

if command -v ruby >/dev/null 2>&1; then
  ruby -e 'require "yaml"; YAML.parse_file("docker-compose.yml"); YAML.parse_file("docker-compose.dev.yml")'
  echo "compose YAML syntax: PASS"
else
  echo "compose YAML syntax: SKIP (Ruby YAML parser unavailable)"
fi

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  compose_json="$(mktemp "${TMPDIR:-/tmp}/pongdang-compose.XXXXXX")"
  cleanup_compose() {
    case "$compose_json" in
      "${TMPDIR:-/tmp}"/pongdang-compose.*) find "$compose_json" -delete ;;
      *) echo "refusing unexpected cleanup path: $compose_json" >&2 ;;
    esac
  }
  trap cleanup_compose EXIT INT TERM

  env \
    POSTGRES_PASSWORD='p@ss/word' \
    DATABASE_URL='postgresql://pongdang:p%40ss%2Fword@cksDB:5432/pongdang' \
    LOCAL_DATABASE_URL='postgresql://pongdang:p%40ss%2Fword@db:5432/pongdang' \
    SECRET_KEY='0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMN' \
    ALLOWED_HOSTS='localhost,127.0.0.1' \
    APPLICATION_BASE_PATH='/multtara' \
    FRONTEND_BIND_ADDRESS='127.0.0.1' \
    PORTFOLIO_BRANCH='codex-auth-contract' \
    PORTFOLIO_AUTH_MODE='local' \
    PONGDANG_SSO_ENABLED='false' \
    VITE_SSO_ENABLED='false' \
    FRONTEND_PORT='8080' \
    DEV_BIND_ADDRESS='127.0.0.1' \
    DEV_POSTGRES_PORT='5432' \
    DEV_BACKEND_PORT='8000' \
    DEV_FRONTEND_PORT='5173' \
    BACKEND_IMAGE='ghcr.io/example/pongdang/backend@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' \
    FRONTEND_IMAGE='ghcr.io/example/pongdang/frontend@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb' \
    docker compose -f docker-compose.yml -f docker-compose.dev.yml config --format json > "$compose_json"

  python3 - "$compose_json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as source:
    config = json.load(source)

services = config["services"]
if set(services) != {"backend", "collector", "db", "frontend"}:
    raise SystemExit(f"FAIL: development services changed unexpectedly: {sorted(services)}")
expected = {
    "db": ("127.0.0.1", 5432, 5432),
    "backend": ("127.0.0.1", 8000, 8000),
    "frontend": ("127.0.0.1", 5173, 5173),
}
for service, wanted in expected.items():
    ports = services[service].get("ports", [])
    if len(ports) != 1:
        raise SystemExit(f"FAIL: {service} exposes unexpected ports: {ports}")
    port = ports[0]
    actual = (port.get("host_ip"), int(port["published"]), int(port["target"]))
    if actual != wanted:
        raise SystemExit(f"FAIL: {service} port {actual} != {wanted}")

health_test = " ".join(services["frontend"]["healthcheck"]["test"])
if "127.0.0.1:5173" not in health_test:
    raise SystemExit("FAIL: effective frontend healthcheck does not probe Vite")

if services["db"].get("image") != "postgres:16-alpine":
    raise SystemExit("FAIL: local development does not use PostgreSQL 16")
db_volumes = services["db"].get("volumes", [])
if not any(
    mount.get("type") == "volume"
    and mount.get("source") == "postgres16_data"
    and mount.get("target") == "/var/lib/postgresql/data"
    for mount in db_volumes
):
    raise SystemExit(f"FAIL: local PostgreSQL volume is missing: {db_volumes}")
db_dependency = services["backend"].get("depends_on", {}).get("db", {})
if db_dependency.get("condition") != "service_healthy":
    raise SystemExit(f"FAIL: local backend does not wait for PostgreSQL health: {db_dependency}")
for service in ("backend", "collector", "db", "frontend"):
    if set(services[service].get("networks", {})) != {"default"}:
        raise SystemExit(f"FAIL: local {service} escaped the project network")
if "postgres16_data" not in config.get("volumes", {}):
    raise SystemExit("FAIL: local PostgreSQL 16 named volume was not rendered")
if "postgres_data" in config.get("volumes", {}):
    raise SystemExit("FAIL: local PostgreSQL 16 reused the former PG15 volume")

expected_database_url = "postgresql://pongdang:p%40ss%2Fword@db:5432/pongdang"
for service in ("backend", "collector"):
    environment = services[service]["environment"]
    if environment.get("DATABASE_URL") != expected_database_url:
        raise SystemExit(f"FAIL: {service} did not receive the exact DATABASE_URL")
    if environment.get("CORS_ALLOWED_ORIGINS") != "":
        raise SystemExit(f"FAIL: {service} same-origin CORS default changed")
    if environment.get("SECURE_SSL_REDIRECT") != "True":
        raise SystemExit(f"FAIL: {service} SSL redirect default changed")
    if environment.get("PORTFOLIO_BRANCH") != "codex-auth-contract":
        raise SystemExit(f"FAIL: {service} did not receive the local branch")
    if environment.get("PORTFOLIO_AUTH_MODE") != "local":
        raise SystemExit(f"FAIL: {service} did not receive local auth mode")
if services["backend"]["environment"].get("PONGDANG_RUNTIME_ROLE") != "web":
    raise SystemExit("FAIL: backend runtime role is not web")
if services["collector"]["environment"].get("PONGDANG_RUNTIME_ROLE") != "worker":
    raise SystemExit("FAIL: collector runtime role is not worker")
if services["backend"]["environment"].get("PONGDANG_SSO_EDGE_SECRET_FILE") != "":
    raise SystemExit("FAIL: backend SSO secret file should default to environment fallback")
if services["backend"].get("user") != "pongdang:root":
    raise SystemExit("FAIL: backend default runtime user changed")
if "PONGDANG_SSO_EDGE_SECRET" in services["collector"]["environment"]:
    raise SystemExit("FAIL: collector received an SSO edge secret")
secret_mounts = services["backend"].get("volumes", [])
if not any(
    mount.get("source") == "/dev/null"
    and mount.get("target") == "/run/secrets/pongdang_sso_edge_secret"
    and mount.get("read_only") is True
    for mount in secret_mounts
):
    raise SystemExit(f"FAIL: backend optional secret bind is unsafe: {secret_mounts}")
print("effective Compose contract: PASS")
PY

  env \
    POSTGRES_PASSWORD='p@ss/word' \
    DATABASE_URL='postgresql://pongdang:p%40ss%2Fword@cksDB:5432/pongdang' \
    SECRET_KEY='0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMN' \
    ALLOWED_HOSTS='localhost,127.0.0.1' \
    APPLICATION_BASE_PATH='/multtara' \
    FRONTEND_BIND_ADDRESS='127.0.0.1' \
    PORTFOLIO_BRANCH='main' \
    PORTFOLIO_AUTH_MODE='sso' \
    PONGDANG_SSO_ENABLED='true' \
    VITE_SSO_ENABLED='true' \
    FRONTEND_PORT='8080' \
    BACKEND_IMAGE='ghcr.io/example/pongdang/backend@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' \
    FRONTEND_IMAGE='ghcr.io/example/pongdang/frontend@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb' \
    docker compose -f docker-compose.yml -f docker-compose.deploy.yml config --format json > "$compose_json"

  python3 - "$compose_json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as source:
    config = json.load(source)

services = config["services"]
if set(services) != {"backend", "collector", "frontend"}:
    raise SystemExit(f"FAIL: production services changed unexpectedly: {sorted(services)}")
if config.get("volumes"):
    raise SystemExit(f"FAIL: production retained application volumes: {config['volumes']}")

expected = {
    "backend": "ghcr.io/example/pongdang/backend@sha256:" + "a" * 64,
    "collector": "ghcr.io/example/pongdang/backend@sha256:" + "a" * 64,
    "frontend": "ghcr.io/example/pongdang/frontend@sha256:" + "b" * 64,
}
for name, image in expected.items():
    service = services[name]
    if service.get("build"):
        raise SystemExit(f"FAIL: deployment retained build for {name}")
    if service.get("image") != image or service.get("pull_policy") != "always":
        raise SystemExit(f"FAIL: immutable image contract failed for {name}")
expected_database_url = "postgresql://pongdang:p%40ss%2Fword@cksDB:5432/pongdang"
for name in ("backend", "collector"):
    if services[name]["environment"].get("DATABASE_URL") != expected_database_url:
        raise SystemExit(f"FAIL: production {name} does not target cksDB")
    if set(services[name].get("networks", {})) != {"default", "multtara-db"}:
        raise SystemExit(f"FAIL: production {name} is not isolated to app + private DB networks")
if set(services["frontend"].get("networks", {})) != {"default"}:
    raise SystemExit("FAIL: production frontend can reach the shared DB network")
shared_network = config.get("networks", {}).get("multtara-db", {})
if shared_network.get("name") != "cksDB-multtara" or shared_network.get("external") is not True:
    raise SystemExit(f"FAIL: private DB network contract failed: {shared_network}")
if "db" in services["backend"].get("depends_on", {}):
    raise SystemExit("FAIL: production backend still depends on an application DB service")
ports = services["frontend"].get("ports", [])
if len(ports) != 1 or ports[0].get("host_ip") != "127.0.0.1" or int(ports[0]["target"]) != 8080:
    raise SystemExit(f"FAIL: deployment frontend port contract failed: {ports}")
print("effective deployment overlay: PASS")
PY
else
  echo "effective Compose contract: SKIP (Docker Compose unavailable)"
fi

scripts/test-setup-worktrees.sh
scripts/test-portfolio-auth-mode.sh
scripts/test-deployment-tools.sh
