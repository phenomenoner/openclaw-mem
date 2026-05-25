# Qdrant Edge enable slice v0 (no restart)

Date: 2026-05-09 (Asia/Taipei)
Status: No-restart enable wiring

## Verdict
Qdrant Edge has an opt-in runtime adapter bridge and query-router wiring, but live runtime configuration remains unchanged and no restart/readback has been performed. LanceDB remains the effective live backend.

## Goal
Close every enable-prep gate that does not require restarting the live OpenClaw process:

- optional adapter bridge contract;
- bounded subprocess execution;
- query-path wiring from recall router to adapter;
- fallback on missing/unwired/failing Qdrant;
- canonical-write isolation preserved;
- counterfactual smokes and reviewable receipts.

## Non-goals
- Do not mutate live config.
- Do not restart OpenClaw.
- Do not claim Qdrant is active in live runtime before restart/readback.
- Do not route writes through Qdrant Edge.

## Implemented artifacts

- `extensions/openclaw-mem-engine/qdrantEdgeRuntimeAdapter.js`
- `extensions/openclaw-mem-engine/qdrantEdgeRuntimeAdapter.test.mjs`
- `extensions/openclaw-mem-engine/scripts/qdrant_edge_query_bridge.py`
- updated `extensions/openclaw-mem-engine/index.ts`
- updated `extensions/openclaw-mem-engine/openclaw.plugin.json`

## Runtime contract
When `retrievalBackend.backend = "qdrant-edge"` and `qdrantEdge.enabled = true`, the retrieval router can call a Qdrant Edge search adapter. The adapter invokes a bounded subprocess bridge and expects JSON:

```json
{
  "schema": "openclaw-mem-engine.qdrant-edge.search.request.v1",
  "kind": "vector",
  "shardRoot": "memory/qdrant-edge",
  "vectorName": "text",
  "query": "...",
  "vector": [0.1],
  "limit": 5,
  "scope": "global",
  "labels": ["must_remember"]
}
```

The bridge returns:

```json
{
  "ok": true,
  "hits": []
}
```

or a bounded failure:

```json
{
  "ok": false,
  "errorCode": "missing_shard",
  "error": "qdrant-edge shard root does not exist"
}
```

Adapter failures throw inside the router and fall back to LanceDB.

## Safety properties
- LanceDB remains default.
- Qdrant still requires explicit `backend: "qdrant-edge"` plus `qdrantEdge.enabled: true`.
- Fallback backend is restricted to LanceDB.
- Qdrant selected plans mark `canonicalWritesAllowed=false`.
- Writes remain on the existing canonical write path.
- Bridge timeout is bounded.
- Missing shard / dependency unavailable / invalid JSON become bounded fallback errors.
- FTS calls currently route through the same adapter only as a fallback-safe probe; the bridge requires vectors and returns `missing_vector`, so FTS falls back to LanceDB until a dedicated Qdrant text-search bridge is implemented.

## Verifier

```bash
cd extensions/openclaw-mem-engine
node --test qdrantEdgeRuntimeAdapter.test.mjs qdrantEdgeFtsFallback.test.mjs retrievalBackendBoundary.test.mjs retrievalRuntimeRouter.test.mjs retrievalBackendPluginSchema.test.mjs routeAuto.test.mjs embeddingClamp.test.mjs docsColdLane.test.mjs
cd ../..
printf '{"shardRoot":"/tmp/does-not-exist-openclaw-qdrant","vector":[0.1],"limit":1}' \
  | python3 extensions/openclaw-mem-engine/scripts/qdrant_edge_query_bridge.py
```

Expected:
- selected Node tests pass;
- bridge missing-shard smoke returns `ok:false,errorCode:"missing_shard"`;
- live config remains unchanged;
- no restart/readback is claimed.

## Remaining live-enable gate
The only remaining work that is intentionally excluded from this slice:

1. apply explicit config in a safe config window;
2. restart;
3. read back startup receipt;
4. run live memory_recall smoke proving effective backend/fallback behavior;
5. run canonical-write isolation readback after restart.

Until those pass, recommended live config remains unchanged or explicit LanceDB with Qdrant disabled.
