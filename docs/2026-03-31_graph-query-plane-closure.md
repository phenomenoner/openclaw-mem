# 2026-03-31 — graph query plane closure packet

This packet closes roadmap item **1.7a) Graphic Memory query plane (operator-facing graph interface)**.

## Verdict
The bounded operator query plane is now treated as **DONE**.

Why this is honest:
- repo-backed topology remains the source of truth
- the derived SQLite graph is rebuildable/disposable
- refresh / upstream / provenance / drift operator paths work on current repo truth
- pack-facing provenance/fail-open contracts are covered by targeted tests

Follow-on work is still real, but it belongs to other roadmap items:
- `1.7` graph consumption / auto-trigger integration
- `1.7b` topology-seed automation
- `6` higher-level graph semantic memory

## Fresh receipts
Stored under:
- `handoffs/receipts/2026-03-31_graph-query-plane/01-topology-refresh.json`
- `handoffs/receipts/2026-03-31_graph-query-plane/02-query-upstream.json`
- `handoffs/receipts/2026-03-31_graph-query-plane/03-query-provenance.json`
- `handoffs/receipts/2026-03-31_graph-query-plane/04-query-drift.json`

Synthetic live-state drift fixture used for the drift path:
- `handoffs/receipts/2026-03-31_graph-query-plane/live-topology-missing-artifact.json`

## Commands run
From repo root:

```bash
PYTHONPATH=. python3 -m openclaw_mem graph --db handoffs/receipts/2026-03-31_graph-query-plane/graph-query-plane-smoke.sqlite --json topology-refresh --file docs/topology.json
PYTHONPATH=. python3 -m openclaw_mem graph --db handoffs/receipts/2026-03-31_graph-query-plane/graph-query-plane-smoke.sqlite --json query upstream artifact.openclaw-mem.sqlite
PYTHONPATH=. python3 -m openclaw_mem graph --db handoffs/receipts/2026-03-31_graph-query-plane/graph-query-plane-smoke.sqlite --json query provenance --node-id artifact.openclaw-mem.sqlite
PYTHONPATH=. python3 -m openclaw_mem graph --db handoffs/receipts/2026-03-31_graph-query-plane/graph-query-plane-smoke.sqlite --json query drift --live-json handoffs/receipts/2026-03-31_graph-query-plane/live-topology-missing-artifact.json
```

## Observed results
### Refresh
- kind: `openclaw-mem.graph.topology-refresh.v0`
- `ok=true`
- `node_count=5`
- `edge_count=3`
- deterministic topology digest emitted

### Upstream query
- kind: `openclaw-mem.graph.query.v0`
- query: `upstream`
- node: `artifact.openclaw-mem.sqlite`
- result count: `1`
- returned writer edge: `script.harvest -> artifact.openclaw-mem.sqlite`

### Provenance query
- kind: `openclaw-mem.graph.query.v0`
- query: `provenance`
- node: `artifact.openclaw-mem.sqlite`
- provenance grouping emitted with normalized `provenance_ref`
- provenance quality summary emitted (`edge_count`, `structured_edge_count`, kind counts)

### Drift query
- kind: `openclaw-mem.graph.query.v0`
- query: `drift`
- synthetic runtime state intentionally omitted `artifact.openclaw-mem.sqlite`
- drift correctly reported:
  - `missing_in_runtime.count = 1`
  - `missing_in_runtime.node_ids = ["artifact.openclaw-mem.sqlite"]`

## Targeted verification
Graph query plane core tests:

```bash
PYTHONPATH=. python3 -m unittest -q \
  tests.test_graph_query \
  tests.test_graph_query_cli \
  tests.test_graph_refresh
```

Result:
- `Ran 45 tests in 2.912s`
- `OK`

Pack-facing provenance / fail-open compatibility tests:

```bash
PYTHONPATH=. python3 -m unittest -q \
  tests.test_cli.TestCliM0.test_pack_use_graph_on_adds_graph_payload_and_trace_extensions \
  tests.test_cli.TestCliM0.test_pack_use_graph_on_provenance_policy_filters_unstructured_graph_candidates \
  tests.test_cli.TestCliM0.test_pack_use_graph_on_provenance_policy_fail_open_on_query_error \
  tests.test_cli.TestCliM0.test_pack_use_graph_on_provenance_policy_contract_shape_is_stable \
  tests.test_cli.TestCliM0.test_pack_graph_provenance_and_trust_policy_contracts_are_compatible
```

Result:
- `Ran 5 tests in 0.094s`
- `OK`

## Closure interpretation
This item is closed because the operator-facing query plane promise is now met:
- deterministic rebuild from curated topology
- usable upstream/provenance/drift queries
- normalized provenance in query output
- pack-facing fail-open / provenance-gate contract remains covered

## Non-change
- No topology authority moved.
- No new repo was created.
- No automatic graph-consumption trigger was promoted here.
- No topology-seed automation claim was added here.
