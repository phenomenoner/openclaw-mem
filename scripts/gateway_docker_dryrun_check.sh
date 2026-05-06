#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="${1:-${OPENCLAW_MEM_GATEWAY_DRYRUN_CHECK_LOG:-/tmp/openclaw-mem-gateway-dryrun/check.log}}"
mkdir -p "$(dirname "$LOG")"

{
  echo "[check] started=$(date -Is)"
  echo "[check] cwd=$ROOT"
  cd "$ROOT"

  echo "[check] bash syntax"
  bash -n scripts/gateway_docker_dryrun.sh

  echo "[check] required files"
  test -f scripts/gateway_docker_dryrun.sh
  test -f deploy/docker/compose.gateway.localhost.yml
  test -f deploy/docker/openclaw-mem-gateway.Dockerfile
  test -f docs/remote-memory-gateway.md

  echo "[check] localhost-only compose publish"
  grep -q '127.0.0.1:${OPENCLAW_MEM_GATEWAY_HOST_PORT:-18765}:8765' deploy/docker/compose.gateway.localhost.yml

  echo "[check] forbidden destructive docker commands"
  if grep -E '^[[:space:]]*(docker rm|docker stop|docker compose down|docker system prune|docker image prune|docker volume rm|docker network rm)([[:space:]]|$)' scripts/gateway_docker_dryrun.sh; then
    echo "FAILED: destructive docker command found"
    exit 2
  fi

  echo "[check] OK: syntax/config dry-run passed"
} 2>&1 | tee "$LOG"
