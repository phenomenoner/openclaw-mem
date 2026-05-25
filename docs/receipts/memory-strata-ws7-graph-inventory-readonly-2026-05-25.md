# Memory Strata WS7 Graph / Topology Governance Inventory — 2026-05-25

Status: **completed / read-only inventory**  
Companion: `docs/specs/memory-strata-todo-v0.md#ws7--graph--topology-governance`  
Topology impact: **unchanged** — graph/status/readiness/help inspection only; no topology refresh, capture, config write, cron change, or runtime enablement.

## Goal

Inventory the currently shipped graph/topology surfaces before drafting topology-source governance or running any rebuild/diff counterfactual.

## Artifacts

- Raw capture: `.tmp/memory-strata-ws7/graph-inventory-readonly.txt`
- Machine receipt: `docs/receipts/artifacts/memory-strata-ws7-graph-inventory-readonly-2026-05-25.json`

## Current graph health

- Health ok: `True`
- Status: `stale`
- Stale: `True`
- Stale threshold hours: `24.0`
- Age hours: `1087.277`
- Node count: `557`
- Edge count: `915`
- Last refresh: `2026-04-09T23:15:54Z`
- Last source path: `/tmp/openclaw-mem-activation/topology-extract-full.json`

## Readiness

- Verdict: `red`
- Ready for autonomous match: `False`
- Checks: `{'fresh_graph_cache': False, 'non_empty_graph_cache': True, 'topology_source_present': False, 'topology_source_unchanged_since_refresh': True, 'graph_match_support_present': True}`
- Blockers: `['graph_cache_stale', 'topology_source_missing']`
- Topology source exists: `False`
- Source path: `/tmp/openclaw-mem-activation/topology-extract-full.json`

## Auto flags

- `OPENCLAW_MEM_GRAPH_AUTO_RECALL.enabled = False`
- `OPENCLAW_MEM_GRAPH_AUTO_CAPTURE.enabled = False`
- `OPENCLAW_MEM_GRAPH_AUTO_CAPTURE_MD.enabled = False`

## Surface inventory

The graph CLI exposes read/query/build surfaces including:

- `index`, `pack`, `preflight`, `match`
- `health`, `readiness`, `auto-status`
- `topology-refresh`, `topology-extract`, `topology-diff`, `query`
- `capture-git`, `capture-md`, `export`

## Product interpretation

The graph cache exists and is non-empty, but it is stale and its recorded topology source path is missing. Therefore graph/topology governance cannot treat the current graph as fresh authority. WS7 should next define a topology-source contract and then run any rebuild/diff only against a copied/fixture output path unless explicitly approved.

## Counterfactual / safety note

This inventory intentionally did **not** run:

- `graph topology-refresh`
- `graph topology-extract`
- `graph capture-git`
- `graph capture-md`
- `docs ingest`
- any production DB write or refresh

## Closure

WS7 read-only inventory is complete. Next WS7 step is topology-source contract drafting, not refresh/enablement.
