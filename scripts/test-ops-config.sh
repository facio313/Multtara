#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$REPO_ROOT"

bash -n scripts/setup-worktrees.sh scripts/test-setup-worktrees.sh

python3 - "$REPO_ROOT" <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
compose = (root / "docker-compose.yml").read_text()
dev_compose = (root / "docker-compose.dev.yml").read_text()
deploy_compose = (root / "docker-compose.deploy.yml").read_text()
nginx = (root / "frontend/nginx.conf").read_text()
frontend_dockerfile = (root / "frontend/Dockerfile").read_text()
wsgi = (root / "backend/config/wsgi.py").read_text()
asgi = (root / "backend/config/asgi.py").read_text()
manage = (root / "backend/manage.py").read_text()
ci_workflow = (root / ".github/workflows/ci.yml").read_text()
release_workflow = (root / ".github/workflows/release-images.yml").read_text()
vite_config = (root / "frontend/vite.config.js").read_text()
app_source = (root / "frontend/src/App.jsx").read_text()
index_html = (root / "frontend/index.html").read_text()
api_source = (root / "frontend/src/services/api.js").read_text()

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
require(compose.count("DATABASE_URL: ${DATABASE_URL:?") == 2, "backend and collector must receive DATABASE_URL")
require(compose.count("APPLICATION_BASE_PATH: ${APPLICATION_BASE_PATH:-}") == 2, "application base path must reach both Django processes")
require(compose.count("CORS_ALLOWED_ORIGINS: ${CORS_ALLOWED_ORIGINS:-}") == 2, "CORS setting is not passed to both Django processes")
require(compose.count("SECURE_SSL_REDIRECT: ${SECURE_SSL_REDIRECT:-True}") == 2, "SSL redirect setting is not passed to both Django processes")
require(compose.count("ROUTING_MATRIX_URL: ${ROUTING_MATRIX_URL:-}") == 2, "routing URL must reach backend and collector only")
require("--route-matrix-interval=${ROUTE_MATRIX_INTERVAL_SECONDS:-86400}" in compose, "collector route refresh cadence is not wired")
require("check_condition_pipeline_health" in compose and '- "900"' in compose, "collector freshness healthcheck is missing")
require(deploy_compose.count("build: !reset null") == 3, "deployment overlay leaves a local build context")
require(deploy_compose.count("pull_policy: always") == 3, "deployment overlay lacks pull_policy")

for port in ("DEV_POSTGRES_PORT", "DEV_BACKEND_PORT", "DEV_FRONTEND_PORT"):
    require(f"${{DEV_BIND_ADDRESS:-127.0.0.1}}:${{{port}" in dev_compose, f"{port} is not loopback-bound")
require("ports: !override" in dev_compose, "development frontend does not replace production ports")
require("http://127.0.0.1:5173/" in dev_compose, "development frontend healthcheck does not probe Vite")
require("listen 8080;" in nginx, "production Nginx does not use an unprivileged port")
require("USER nginx" in frontend_dockerfile and "ENTRYPOINT []" in frontend_dockerfile, "production Nginx runtime is not explicitly unprivileged")
require("ARG VITE_APP_BASE_PATH=/" in frontend_dockerfile, "frontend image does not accept an application base path")
require("ARG VITE_CSRF_COOKIE_NAME=pongdang_csrftoken" in frontend_dockerfile, "frontend image does not pin the isolated CSRF cookie")
require("ARG VITE_SSO_ENABLED=false" in frontend_dockerfile, "frontend image cannot select the portfolio SSO contract")
require("base: process.env.VITE_APP_BASE_PATH || '/'" in vite_config, "Vite base path is not configurable")
require("<BrowserRouter basename={routerBaseName}>" in app_source, "React routes do not honor the Vite base path")
require(index_html.count("%BASE_URL%") >= 3, "HTML metadata/assets are not rooted at the Vite base path")
require("VITE_CSRF_COOKIE_NAME" in api_source and "pongdang_csrftoken" in api_source, "Axios CSRF cookie does not match Django")
require("VITE_SSO_ENABLED" in api_source, "frontend runtime does not expose the SSO mode")
require("PONGDANG_SSO_ENABLED: ${PONGDANG_SSO_ENABLED:-false}" in compose, "backend SSO setting is not wired")
require(nginx.count("proxy_set_header Remote-User $http_remote_user;") >= 2, "frontend proxy does not preserve trusted SSO identity")
require("127.0.0.1}:${FRONTEND_PORT:-8080}:8080" in compose, "production Nginx mapping does not target port 8080")
require(dev_compose.count("DJANGO_SETTINGS_MODULE: config.settings.dev") == 2, "backend and collector do not share the explicit development settings path")
require("location = /admin" in nginx, "bare /admin is not routed to the operator surface")

for path in ("= /admin", "/admin/", "/static/"):
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
require(
    "  quality-gate:\n" in release_workflow
    and "uses: ./.github/workflows/ci.yml" in release_workflow,
    "release workflow does not invoke the full CI quality gate",
)
require(
    release_workflow.count("needs: [prepare, quality-gate]") == 2,
    "release images can be published before the quality gate succeeds",
)
require("VITE_APP_BASE_PATH=/multtara/" in release_workflow, "release assets are not built for the portfolio subpath")
require("VITE_API_BASE_URL=/multtara/api/v1/" in release_workflow, "release API is not isolated below the portfolio subpath")
require("VITE_SSO_ENABLED=true" in release_workflow, "release frontend does not enable portfolio SSO")
require("deploy multtara $DEPLOY_VERSION $DEPLOY_SHA $BACKEND_DIGEST $FRONTEND_DIGEST" in release_workflow, "release workflow does not request the restricted Multtara deployment")

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
    DATABASE_URL='postgresql://pongdang:p%40ss%2Fword@db:5432/pongdang' \
    SECRET_KEY='0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMN' \
    ALLOWED_HOSTS='localhost,127.0.0.1' \
    APPLICATION_BASE_PATH='/multtara' \
    FRONTEND_BIND_ADDRESS='127.0.0.1' \
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

expected_database_url = "postgresql://pongdang:p%40ss%2Fword@db:5432/pongdang"
for service in ("backend", "collector"):
    environment = services[service]["environment"]
    if environment.get("DATABASE_URL") != expected_database_url:
        raise SystemExit(f"FAIL: {service} did not receive the exact DATABASE_URL")
    if environment.get("CORS_ALLOWED_ORIGINS") != "":
        raise SystemExit(f"FAIL: {service} same-origin CORS default changed")
    if environment.get("SECURE_SSL_REDIRECT") != "True":
        raise SystemExit(f"FAIL: {service} SSL redirect default changed")
print("effective Compose contract: PASS")
PY

  env \
    POSTGRES_PASSWORD='p@ss/word' \
    DATABASE_URL='postgresql://pongdang:p%40ss%2Fword@db:5432/pongdang' \
    SECRET_KEY='0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMN' \
    ALLOWED_HOSTS='localhost,127.0.0.1' \
    APPLICATION_BASE_PATH='/multtara' \
    FRONTEND_BIND_ADDRESS='127.0.0.1' \
    FRONTEND_PORT='8080' \
    BACKEND_IMAGE='ghcr.io/example/pongdang/backend@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' \
    FRONTEND_IMAGE='ghcr.io/example/pongdang/frontend@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb' \
    docker compose -f docker-compose.yml -f docker-compose.deploy.yml config --format json > "$compose_json"

  python3 - "$compose_json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as source:
    services = json.load(source)["services"]

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
ports = services["frontend"].get("ports", [])
if len(ports) != 1 or ports[0].get("host_ip") != "127.0.0.1" or int(ports[0]["target"]) != 8080:
    raise SystemExit(f"FAIL: deployment frontend port contract failed: {ports}")
print("effective deployment overlay: PASS")
PY
else
  echo "effective Compose contract: SKIP (Docker Compose unavailable)"
fi

scripts/test-setup-worktrees.sh
scripts/test-deployment-tools.sh
