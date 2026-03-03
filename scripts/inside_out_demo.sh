#!/usr/bin/env bash
set -euo pipefail

# Inside-Out Memory demo (synthetic)
# Usage:
#   ./scripts/inside_out_demo.sh [/path/to/demo.sqlite]

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
DB_PATH=${1:-/tmp/openclaw-mem-inside-out-demo.sqlite}
DEMO_WS=${DEMO_WS:-$(mktemp -d /tmp/openclaw-mem-demo-ws.XXXXXX)}
mkdir -p "$DEMO_WS/memory"

cd "$ROOT_DIR"

rm -f "$DB_PATH"

echo "[demo] Using DB: $DB_PATH"
echo "[demo] Using workspace: $DEMO_WS (markdown memory stays here)"

echo "[demo] Storing synthetic memories..."
uv run openclaw-mem store --db "$DB_PATH" --workspace "$DEMO_WS" --category preference --importance 0.85 \
  "Prefers using Asia/Taipei (UTC+8) timezone for time displays and references."

uv run openclaw-mem store --db "$DB_PATH" --workspace "$DEMO_WS" --category preference --importance 0.95 \
  "Demo content must use synthetic data; do not leak private notes, credentials, or personal details."

uv run openclaw-mem store --db "$DB_PATH" --workspace "$DEMO_WS" --category preference --importance 0.80 \
  "Writing style: index-first / bounded reveal; lead with the decision then 2–3 receipts."

uv run openclaw-mem store --db "$DB_PATH" --workspace "$DEMO_WS" --category decision --importance 0.75 \
  "Showcase theme: openclaw-mem (memory/self) as the main protagonist."

uv run openclaw-mem store --db "$DB_PATH" --workspace "$DEMO_WS" --category decision --importance 0.70 \
  "Killer demo goal: before/after transcript + architecture diagram + reproducible runbook."


echo
echo "[demo] Packing memories for query (with trace)..."
uv run openclaw-mem pack --db "$DB_PATH" \
  --query "timezone privacy demo style" \
  --limit 12 --budget-tokens 900 --trace | cat

echo
echo "[demo] Done. Next: open docs/showcase/inside-out-demo.md"
