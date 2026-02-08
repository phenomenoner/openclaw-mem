#!/usr/bin/env bash
set -euo pipefail

# Export OpenClaw memory artifacts into an Obsidian vault for human browsing.
#
# Usage:
#   scripts/obsidian_daily_export.sh /path/to/vault
#
# Creates/updates:
#   <vault>/OpenClaw/Daily/<YYYY-MM-DD>/...

VAULT_ROOT="${1:?Usage: obsidian_daily_export.sh /path/to/vault}"
DATE_TAIPEI="$(TZ=Asia/Taipei date +%F)"
OUTDIR="$VAULT_ROOT/OpenClaw/Daily/$DATE_TAIPEI"

WS="/home/agent/.openclaw/workspace"
MEMDIR="$WS/memory"
STATE_DIR="/home/agent/.openclaw/memory/openclaw-mem"

mkdir -p "$OUTDIR"

# 1) Durable memory markdown (human-curated-ish)
if [ -f "$MEMDIR/$DATE_TAIPEI.md" ]; then
  cp -f "$MEMDIR/$DATE_TAIPEI.md" "$OUTDIR/workspace-memory-$DATE_TAIPEI.md"
fi
if [ -f "$WS/MEMORY.md" ]; then
  cp -f "$WS/MEMORY.md" "$OUTDIR/workspace-MEMORY.md"
fi

# 2) openclaw-mem DB snapshot artifacts
cd "$WS/openclaw-mem"

uv run --python 3.13 -- python -m openclaw_mem status --json > "$OUTDIR/openclaw-mem-status.json"

# Ingest latest tool-result observations into the DB, but DO NOT embed (avoid API cost).
uv run --python 3.13 -- python -m openclaw_mem harvest --no-embed --json > "$OUTDIR/openclaw-mem-harvest.json"

# Route-A index (useful for grepping / backlinking)
if [ -f "$STATE_DIR/observations-index.md" ]; then
  cp -f "$STATE_DIR/observations-index.md" "$OUTDIR/observations-index.md"
fi

# Durable graph (Hub/Spoke) for human navigation + recall-friendly structure
uv run --python 3.13 -- python scripts/durable_structure.py --workspace "$WS" >/dev/null

# Mirror the durable graph into the vault (stable location, not per-day)
DURABLE_SRC="$WS/memory/durable"
DURABLE_DST="$VAULT_ROOT/OpenClaw/Durable"
mkdir -p "$DURABLE_DST"
# Replace the agent-managed folder content deterministically
rm -rf "$DURABLE_DST"/*
cp -a "$DURABLE_SRC"/* "$DURABLE_DST"/

# 3) Detailed markdown export for browsing in Obsidian
# (suppress stdout noise; file output is the artifact)
uv run --python 3.13 -- python -m openclaw_mem export \
  --to "$OUTDIR/openclaw-mem-export-last500.md" \
  --limit 500 --include-detail >/dev/null

# 4) Small human-readable header (+ day-over-day deltas if yesterday exists)
python3 - <<'PY' > "$OUTDIR/README.md"
import json
from pathlib import Path

outdir = Path("""$OUTDIR""")
daily_root = outdir.parent

def load_json(p: Path):
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))

status = load_json(outdir / "openclaw-mem-status.json") or {}
harvest = load_json(outdir / "openclaw-mem-harvest.json") or {}

# yesterday delta (best-effort)
prev = None
try:
    # Find previous daily folder by sorting folder names (YYYY-MM-DD)
    candidates = sorted([d for d in daily_root.iterdir() if d.is_dir() and d.name < outdir.name])
    if candidates:
        prev_dir = candidates[-1]
        prev = load_json(prev_dir / "openclaw-mem-status.json")
except Exception:
    prev = None

lines = []
lines.append(f"# Daily memory snapshot — {outdir.name} (Asia/Taipei)\n")

lines.append("## What this folder contains\n")
lines.append("- `workspace-memory-YYYY-MM-DD.md`: durable memories written by `openclaw-mem store` (OpenClaw workspace)\n")
lines.append("- `workspace-MEMORY.md`: compressed long-term memory (if present)\n")
lines.append("- `openclaw-mem-status.json`: DB counts\n")
lines.append("- `openclaw-mem-harvest.json`: ingest stats from tool-result capture log\n")
lines.append("- `openclaw-mem-export-last500.md`: last 500 observations (detailed)\n")
lines.append("- `observations-index.md`: Route-A index (optional)\n")

lines.append("\n## Quick stats\n")
count = status.get('count')
lines.append(f"- DB count: {count}\n")
if prev and isinstance(prev, dict):
    try:
        prev_count = prev.get('count')
        if isinstance(count, int) and isinstance(prev_count, int):
            lines.append(f"- Δ vs previous snapshot: {count - prev_count:+d}\n")
    except Exception:
        pass

emb = status.get("embeddings") or {}
lines.append(f"- Embeddings count: {emb.get('count')} (models={emb.get('models')})\n")
lines.append(f"- Harvest ingested this run: {harvest.get('ingested')}\n")

print("".join(lines))
PY

# Make exported artifacts readable in Obsidian (WSL/Windows) while still local-only.
chmod 0755 "$OUTDIR" || true
chmod 0644 "$OUTDIR"/*.md "$OUTDIR"/*.json 2>/dev/null || true

echo "ok: wrote $OUTDIR"
