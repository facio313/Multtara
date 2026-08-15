#!/usr/bin/env bash
# Raspberry Pi deploy: build and start Compose services.
# Provide secrets via a local .env next to docker-compose.yml. Do not commit .env.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

docker compose up -d --build
