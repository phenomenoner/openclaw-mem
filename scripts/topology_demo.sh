#!/usr/bin/env bash
set -euo pipefail

# Topology query + bounded-subgraph demo (synthetic / repo-local)
#
# Shows how L3 topology knowledge can answer:
# - who writes this artifact?
# - what jobs/scripts are adjacent?
# - how to emit a bounded subgraph with provenance (pack-style)

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found; install uv first" >&2
  exit 1
fi

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

DB="$tmpdir/mem.sqlite"

echo "== Refresh topology from docs/topology.json"
uv run --python 3.13 --frozen -- python -m openclaw_mem graph --db "$DB" --no-json \
  topology-refresh --file docs/topology.json

echo
echo "== Who writes artifact.openclaw-mem.sqlite?"
uv run --python 3.13 --frozen -- python -m openclaw_mem graph --db "$DB" --no-json \
  query writers artifact.openclaw-mem.sqlite

echo
echo "== Bounded subgraph (upstream, 2 hops) around artifact.openclaw-mem.sqlite"
uv run --python 3.13 --frozen -- python -m openclaw_mem graph --db "$DB" --no-json \
  query subgraph artifact.openclaw-mem.sqlite --hops 2 --direction upstream

echo
echo "== Filtered subgraph (edge-types runs+writes; node types cron_job+script+artifact) around artifact.openclaw-mem.sqlite"
uv run --python 3.13 --frozen -- python -m openclaw_mem graph --db "$DB" --no-json \
  query subgraph artifact.openclaw-mem.sqlite --hops 2 --direction upstream \
  --edge-type runs --edge-type writes \
  --include-node-type cron_job --include-node-type script --include-node-type artifact
