# Qdrant Edge live runtime integration v0

Date: 2026-05-09 (Asia/Taipei)
Status: Dry live-integration slice

## Verdict
The runtime can now parse and surface a retrieval backend plan and route recall search calls through a backend router while keeping LanceDB as the effective live backend. Qdrant Edge remains disabled by default; the router supports Qdrant-ready and Qdrant-fallback paths, but no Qdrant adapter is enabled in live runtime yet.

## Goal
Add the smallest safe live-runtime integration surface:

- configuration schema for backend selection;
- disabled-by-default Qdrant Edge config;
- registration-time backend plan receipt;
- query-path routing through a backend router;
- LanceDB fallback when Qdrant Edge is unavailable or dimension-incompatible;
- no live configuration mutation.

## Non-goals
- Do not enable Qdrant Edge as the live backend.
- Do not enable Qdrant Edge search in live runtime yet.
- Do not route canonical writes through Qdrant Edge.
- Do not change live runtime config or restart services.

## Implemented surface

### Config shape

```json
{
  "retrievalBackend": {
    "backend": "lancedb",
    "qdrantEdge": {
      "enabled": false,
      "shardRoot": "memory/qdrant-edge",
      "vectorName": "text",
      "optimizeOnRebuild": true,
      "fallbackBackend": "lancedb"
    }
  }
}
```

### Runtime registration receipt
At plugin registration, the engine resolves a retrieval backend plan and includes it in the startup log receipt:

```text
retrievalBackend=<selected>|reason=<reason>|fallback=<backend>|qdrant=<enabled|disabled>
```

For the current slice, Qdrant Edge runtime probes are intentionally false because the adapter is not enabled. Therefore:

- default config selects LanceDB;
- explicit Qdrant Edge config falls back to LanceDB until live wiring is implemented;
- canonical writes remain on the existing path.

### Query-path router
Recall full-text and vector searches now call a retrieval runtime router. The router:

- uses LanceDB by default;
- can call a Qdrant search function when one is supplied in a future slice;
- falls back to LanceDB when Qdrant search is unwired or throws;
- emits a bounded fallback receipt through the existing logger.
- includes retrieval backend plan fields in recall receipts for operator debugging.

## Safety properties
- LanceDB remains default.
- Qdrant Edge requires explicit opt-in before it can even be considered.
- Fallback backend is restricted to LanceDB.
- Qdrant Edge selected plans mark `canonicalWritesAllowed=false`.
- Current live runtime config is not modified by this slice.

## Verifier

```bash
node --test retrievalBackendBoundary.test.mjs retrievalRuntimeRouter.test.mjs retrievalBackendPluginSchema.test.mjs routeAuto.test.mjs embeddingClamp.test.mjs docsColdLane.test.mjs
node -e 'JSON.parse(fs.readFileSync("openclaw.plugin.json", "utf8")); console.log("plugin json ok")'
```

Expected:
- selected tests pass;
- plugin JSON parses;
- public hygiene scan has no findings.

## Current recommended live config
Use an explicit LanceDB/default retrieval backend block only after the next safe config-change window. Do not enable Qdrant Edge in live config yet:

```json
{
  "retrievalBackend": {
    "backend": "lancedb",
    "qdrantEdge": {
      "enabled": false,
      "shardRoot": "memory/qdrant-edge",
      "vectorName": "text",
      "optimizeOnRebuild": true,
      "fallbackBackend": "lancedb"
    }
  }
}
```

This makes the intended backend policy explicit while preserving current behavior.

## Next gate before Qdrant live enable
Before setting `backend: "qdrant-edge"`, implement real runtime adapter wiring and run:

1. query-path parity against LanceDB in the runtime shape;
2. fallback smoke with Qdrant package missing/unavailable;
3. dimension-mismatch smoke;
4. canonical-write isolation smoke;
5. config readback after restart in a safe window.

## Rollback
Remove the `retrievalBackend` config block or set `backend: "lancedb"` and `qdrantEdge.enabled: false`. Because this slice does not migrate data or own canonical writes, rollback has no data migration requirement.
