# Qdrant Edge implementation boundary v0

Date: 2026-05-09 (Asia/Taipei)
Status: Draft implementation boundary

## Verdict
Qdrant Edge can move behind a disabled-by-default backend-selection boundary. The boundary must make LanceDB the fallback and must prevent Qdrant Edge from owning canonical writes.

## Goal
Close the optional-backend backlog by defining the code boundary for:

- backend selection;
- disabled-by-default configuration;
- fallback to LanceDB;
- canonical-truth isolation;
- verifier coverage before runtime integration.

## Non-goals
- Do not enable Qdrant Edge by default.
- Do not change live runtime configuration.
- Do not introduce Qdrant Server or port exposure.
- Do not make Qdrant Edge a canonical durable memory store.

## Boundary contract
A default LanceDB retrieval backend plan has this shape:

```json
{
  "selectedBackend": "lancedb",
  "fallbackBackend": null,
  "reason": "default_or_configured_lancedb",
  "canonicalWritesAllowed": true,
  "qdrantEdge": {
    "enabled": false,
    "shardRoot": "memory/qdrant-edge",
    "vectorName": "text",
    "optimizeOnRebuild": true,
    "fallbackBackend": "lancedb"
  }
}
```

An explicitly enabled Qdrant Edge read-index plan has this shape:

```json
{
  "selectedBackend": "qdrant-edge",
  "fallbackBackend": "lancedb",
  "reason": "qdrant_edge_ready",
  "canonicalWritesAllowed": false,
  "qdrantEdge": {
    "enabled": true,
    "shardRoot": "memory/qdrant-edge",
    "vectorName": "text",
    "optimizeOnRebuild": true,
    "fallbackBackend": "lancedb"
  }
}
```

Rules:

1. Default selection is LanceDB.
2. `backend: "qdrant-edge"` is invalid unless `qdrantEdge.enabled === true`.
3. Qdrant Edge fallback must be LanceDB.
4. If Qdrant Edge is unavailable or vector dimensions mismatch, selection falls back to LanceDB.
5. If Qdrant Edge is selected, `canonicalWritesAllowed` must be false.
6. Qdrant Edge state is an index/cache and must be deletable/rebuildable.

## Implementation receipt
The first implementation boundary lives in:

- `extensions/openclaw-mem-engine/retrievalBackendBoundary.js`
- `extensions/openclaw-mem-engine/retrievalBackendBoundary.test.mjs`

This is a dry boundary module. It does not alter live runtime selection yet. Runtime wiring should happen only after this boundary is reviewed and a larger lifecycle/load run remains green.

## Verifier

```bash
node --test extensions/openclaw-mem-engine/retrievalBackendBoundary.test.mjs
```

Expected coverage:

- default LanceDB selection;
- explicit Qdrant Edge opt-in;
- disabled Qdrant Edge rejection;
- unavailable Qdrant Edge fallback;
- dimension mismatch fallback;
- canonical write isolation;
- unknown config key rejection.

## Runtime integration plan
After this boundary is accepted:

1. Add public config schema fields for backend selection while keeping defaults unchanged.
2. Add runtime probes for Qdrant Edge package availability and vector dimension compatibility.
3. Route read/search calls through the selected backend plan.
4. Keep write/canonical-store operations on the existing canonical path.
5. Emit compact receipts showing selected backend and fallback reason.
6. Run lifecycle/load gates before enabling any non-default path.

## Rollback
Remove the boundary module/tests and continue using LanceDB. Since this module is not live-wired, rollback has no data migration or runtime topology impact.
