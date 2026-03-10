# Topology knowledge demo — bounded subgraph + provenance (5 min)

This demo is **synthetic / repo-local**. It shows how L3 topology knowledge can answer navigation/impact questions deterministically:

- **Who writes this artifact?**
- **What jobs/scripts are adjacent to this node?**
- **How to emit only a bounded subgraph with provenance** (pack-style, injection-ready)

## Prereqs
- `uv`
- from repo root: `uv sync` (or let `uv run ...` build on demand)

## Run

```bash
./scripts/topology_demo.sh
```

## What you should see

1) A deterministic refresh from the curated topology file:

- input: `docs/topology.json`
- output: a small SQLite topology graph
- plus a refresh receipt (stored in `graph_refresh_receipts`)

2) A **writers** query:

```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem \
  graph --db /tmp/mem.sqlite --no-json query writers artifact.openclaw-mem.sqlite
```

3) A **bounded subgraph** query with **provenance-first edges**:

```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem \
  graph --db /tmp/mem.sqlite --no-json query subgraph artifact.openclaw-mem.sqlite \
  --hops 2 --direction upstream
```

Optional: tighten the output further with **edge-type** / **node-type** filters:

```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem \
  graph --db /tmp/mem.sqlite --no-json query subgraph artifact.openclaw-mem.sqlite \
  --hops 2 --direction upstream \
  --edge-type writes --include-node-type cron_job --include-node-type artifact
```

The `subgraph` result is intentionally small:
- bounded by `--hops`, `--max-nodes`, `--max-edges`
- stable ordering
- each edge includes a `provenance` reference (file/line/url/etc)

## Notes
- This is meant as a **demo path**, not a full graph system.
- Treat topology as **reference with provenance**, not durable memory.
