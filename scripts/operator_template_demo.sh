#!/usr/bin/env bash
set -euo pipefail

# Operator template demo (synthetic)
# Usage:
#   ./scripts/operator_template_demo.sh [/path/to/demo.sqlite]
#
# Creates a privacy-safe mini operator workspace, ingests a few durable-looking
# project facts into an isolated demo DB, then packs an onboarding handoff query
# with citations. It does not mutate OpenClaw config or the host memory journal.

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
DB_PATH=${1:-/tmp/openclaw-mem-operator-template.sqlite}
DEMO_WS=${DEMO_WS:-$(mktemp -d /tmp/openclaw-mem-operator-template.XXXXXX)}
CLI=(uv run --python 3.13 --frozen -- python -m openclaw_mem)

mkdir -p "$DEMO_WS/DECISIONS" "$DEMO_WS/RUNBOOKS" "$DEMO_WS/receipts"
cd "$ROOT_DIR"
rm -f "$DB_PATH"

cat > "$DEMO_WS/DECISIONS/2026-02-12-demo.md" <<'MD'
# Demo decision: sidecar-first memory rollout

- Decision: start with sidecar capture before promoting a memory engine.
- Success criteria: local recall works, receipts are inspectable, rollback is one config change.
- Rollback: disable capture and remove the demo SQLite DB.
MD

cat > "$DEMO_WS/RUNBOOKS/memory-demo.md" <<'MD'
# Memory demo runbook

1. Store project facts with category and importance.
2. Pack a small handoff bundle for the operator query.
3. Inspect citations before trusting the answer.
MD

cat > "$DEMO_WS/observations.jsonl" <<'JSONL'
{"ts":"2026-02-12T08:00:00Z","kind":"decision","summary":"Demo project decision: adopt openclaw-mem as a sidecar first; promote engine only after receipt-backed local recall proves useful.","importance_score":0.88,"detail":{"source_path":"DECISIONS/2026-02-12-demo.md","synthetic":true}}
{"ts":"2026-02-12T08:01:00Z","kind":"preference","summary":"Operator handoffs should lead with verdict, next action, rollback, and receipts.","importance_score":0.82,"detail":{"synthetic":true}}
{"ts":"2026-02-12T08:02:00Z","kind":"fact","summary":"Demo runbook lives at RUNBOOKS/memory-demo.md and demonstrates Store / Pack / Observe with synthetic data only.","importance_score":0.76,"detail":{"source_path":"RUNBOOKS/memory-demo.md","synthetic":true}}
{"ts":"2026-02-12T08:03:00Z","kind":"fact","summary":"Rollback posture: delete the demo DB and workspace; no OpenClaw gateway restart or config mutation is required.","importance_score":0.74,"detail":{"synthetic":true}}
JSONL

echo "[template] Using DB: $DB_PATH"
echo "[template] Using workspace: $DEMO_WS"
echo "[template] Ingesting synthetic operator records..."
"${CLI[@]}" ingest --db "$DB_PATH" --file "$DEMO_WS/observations.jsonl" --json

echo
echo "[template] Packing operator handoff..."
"${CLI[@]}" pack --db "$DB_PATH" \
  --query "operator handoff sidecar rollout rollback receipts runbook" \
  --limit 8 --budget-tokens 700 --trace | tee "$DEMO_WS/receipts/operator-template-pack.json"

echo
echo "[template] Done. Inspect: $DEMO_WS/receipts/operator-template-pack.json"
