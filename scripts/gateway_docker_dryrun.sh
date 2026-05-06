#!/usr/bin/env bash
set -euo pipefail

# Safe dry-run for openclaw-mem-gateway sidecar.
# This script intentionally does NOT stop/remove/down/prune existing Docker containers.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT="openclaw-mem-gateway-dryrun"
SERVICE="openclaw-mem-gateway"
ENV_FILE="$ROOT/.env.gateway.local"
RECEIPT_DIR="${OPENCLAW_MEM_GATEWAY_DRYRUN_RECEIPT_DIR:-/tmp/openclaw-mem-gateway-dryrun}"
PORT="${OPENCLAW_MEM_GATEWAY_DRYRUN_PORT:-18765}"
mkdir -p "$RECEIPT_DIR"

cd "$ROOT"

need() {
  command -v "$1" >/dev/null 2>&1 || { echo "missing required command: $1" >&2; exit 127; }
}
need docker
need python3
need curl

docker compose version >/dev/null

# Never overwrite an operator-provided env file. If absent, create throwaway dry-run tokens.
if [[ ! -f "$ENV_FILE" ]]; then
  umask 077
  python3 - <<'PY' > "$ENV_FILE"
import secrets
print('OPENCLAW_MEM_GATEWAY_TOKENS=' + ','.join([
    secrets.token_urlsafe(32) + ':read',
    secrets.token_urlsafe(32) + ':write',
    secrets.token_urlsafe(32) + ':admin',
]))
PY
fi

docker ps --format 'table {{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Ports}}' > "$RECEIPT_DIR/pre-ps.txt"

# Safety: fail if the sidecar compose file lost localhost-only publish.
python3 - <<'PY'
from pathlib import Path
p = Path('deploy/docker/compose.gateway.localhost.yml')
s = p.read_text(encoding='utf-8')
needle = '127.0.0.1:${OPENCLAW_MEM_GATEWAY_HOST_PORT:-18765}:8765'
if needle not in s:
    raise SystemExit(f'compose safety check failed: missing {needle}')
PY

docker compose --env-file "$ENV_FILE" \
  -f deploy/docker/compose.gateway.localhost.yml \
  -p "$PROJECT" \
  build "$SERVICE" | tee "$RECEIPT_DIR/build.log"

docker compose --env-file "$ENV_FILE" \
  -f deploy/docker/compose.gateway.localhost.yml \
  -p "$PROJECT" \
  up -d "$SERVICE" | tee "$RECEIPT_DIR/up.log"

# Capture exact sidecar identity and port publish.
docker ps --filter "name=${PROJECT}" \
  --format 'table {{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Ports}}' > "$RECEIPT_DIR/sidecar-ps.txt"

CONTAINER_ID="$(docker ps --filter "name=${PROJECT}-${SERVICE}" --format '{{.ID}}' | head -n 1)"
if [[ -z "$CONTAINER_ID" ]]; then
  echo "sidecar container not found" >&2
  exit 1
fi

docker inspect "$CONTAINER_ID" --format '{{json .NetworkSettings.Ports}}' > "$RECEIPT_DIR/sidecar-ports.json"
python3 - <<'PY' "$RECEIPT_DIR/sidecar-ports.json"
import json, sys
ports = json.loads(open(sys.argv[1], encoding='utf-8').read())
entries = ports.get('8765/tcp') or []
host_ips = {e.get('HostIp') for e in entries}
if host_ips != {'127.0.0.1'}:
    raise SystemExit(f'unsafe host bind for 8765/tcp: {entries!r}')
PY

# Health probe.
curl -sS "http://127.0.0.1:${PORT}/health" | tee "$RECEIPT_DIR/health.json"
python3 - <<'PY' "$RECEIPT_DIR/health.json"
import json, sys
payload = json.load(open(sys.argv[1], encoding='utf-8'))
assert payload.get('ok') is True, payload
PY

READ_TOKEN="$(python3 - <<'PY' "$ENV_FILE"
from pathlib import Path
raw = Path(__import__('sys').argv[1]).read_text().strip().split('=', 1)[1]
for item in raw.split(','):
    token, role = item.rsplit(':', 1)
    if role == 'read':
        print(token)
        break
PY
)"

curl -sS "http://127.0.0.1:${PORT}/v1/status" \
  -H "Authorization: Bearer ${READ_TOKEN}" | tee "$RECEIPT_DIR/status-read.json"
python3 - <<'PY' "$RECEIPT_DIR/status-read.json"
import json, sys
payload = json.load(open(sys.argv[1], encoding='utf-8'))
assert payload.get('ok') is True, payload
assert payload.get('role') == 'read', payload
assert 'db' not in payload and 'workspace' not in payload, payload
assert payload.get('direct_store_enabled') is False, payload
PY

NOAUTH_CODE="$(curl -sS -o "$RECEIPT_DIR/status-noauth.json" -w '%{http_code}' "http://127.0.0.1:${PORT}/v1/status")"
[[ "$NOAUTH_CODE" == "401" ]] || { echo "expected no-auth 401, got $NOAUTH_CODE" >&2; exit 1; }

READ_WRITE_CODE="$(curl -sS -o "$RECEIPT_DIR/read-write-denied.json" -w '%{http_code}' \
  "http://127.0.0.1:${PORT}/v1/store/propose" \
  -H "Authorization: Bearer ${READ_TOKEN}" \
  -H 'Content-Type: application/json' \
  -d '{"scope":"dryrun","agent_id":"dryrun","text":"read token must not write"}')"
[[ "$READ_WRITE_CODE" == "403" ]] || { echo "expected read-write denied 403, got $READ_WRITE_CODE" >&2; exit 1; }

docker ps --format 'table {{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Ports}}' > "$RECEIPT_DIR/post-ps.txt"

python3 - <<'PY' "$RECEIPT_DIR"
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
summary = {
    'ok': True,
    'receipt_dir': str(root),
    'pre_ps': str(root / 'pre-ps.txt'),
    'post_ps': str(root / 'post-ps.txt'),
    'sidecar_ps': str(root / 'sidecar-ps.txt'),
    'sidecar_ports': str(root / 'sidecar-ports.json'),
    'health': str(root / 'health.json'),
    'status_read': str(root / 'status-read.json'),
    'noauth_status_code': 401,
    'read_write_denied_code': 403,
    'cleanup': 'not performed; use targeted stop only after operator confirmation',
}
(root / 'summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n', encoding='utf-8')
print(json.dumps(summary, indent=2, sort_keys=True))
PY
