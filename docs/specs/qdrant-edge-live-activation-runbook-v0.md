# Qdrant Edge live activation runbook v0

Date: 2026-05-09 (Asia/Taipei)
Status: pre-restart ready; live config not applied in this document

## Verdict
Qdrant Edge is prepared for live activation but should not be considered live until the explicit config patch is applied and OpenClaw is manually restarted/read back.

## Current completed gates

- Optional runtime adapter bridge exists.
- `qdrant-edge-py==0.6.1` is installed in the repo virtualenv only.
- LanceDB export → Qdrant Edge rebuild works against the live memory table snapshot.
- Durable Qdrant Edge shard was built at `~/.openclaw/memory/qdrant-edge`.
- Bridge vector query against the built shard returns the expected known ID in top-3.
- Config enable patch and rollback patch are prepared as artifacts.
- Config resolver smoke confirms the enable patch selects `qdrant-edge` and keeps `canonicalWritesAllowed=false`.
- Gateway health pre-restart probe is connectivity-ok.

## Live activation patch

Prepared artifact:

```text
<workspace>/.state/openclaw-mem/qdrant-edge-live-activation-YYYYMMDD/config-patch-enable-qdrant-edge.json
```

Effective retrieval backend config:

```json
{
  "retrievalBackend": {
    "backend": "qdrant-edge",
    "qdrantEdge": {
      "enabled": true,
      "shardRoot": "memory/qdrant-edge",
      "vectorName": "text",
      "optimizeOnRebuild": true,
      "fallbackBackend": "lancedb",
      "searchCommand": "<repo>/.venv/bin/python",
      "searchCommandArgs": [
        "<repo>/extensions/openclaw-mem-engine/scripts/qdrant_edge_query_bridge.py"
      ],
      "timeoutMs": 1500
    }
  }
}
```

Rollback patch:

```text
<workspace>/.state/openclaw-mem/qdrant-edge-live-activation-YYYYMMDD/config-patch-rollback-lancedb.json
```

## Pre-restart verifier artifacts

Root:

```text
<workspace>/.state/openclaw-mem/qdrant-edge-live-activation-YYYYMMDD/
```

Receipts:

- `dependency-preflight.json`
- `uv-pip-dry-run-qdrant-edge-py.log`
- `uv-pip-install-qdrant-edge-py.log`
- `qdrant-import-after-install.json`
- `lancedb-export-all.count`
- `qdrant-rebuild-live-prestart.json`
- `qdrant-live-query-smoke-summary.json`
- `config-patch-resolver-smoke.json`
- `gateway-status-pre-restart.txt`

Expected summary:

- `qdrant-edge-py` import works in repo venv.
- LanceDB export count equals Qdrant rebuild stored count.
- Qdrant query smoke has `ok:true` and `expectedInTop3:true`.
- Resolver smoke has `selectedBackend:"qdrant-edge"`, `fallbackBackend:"lancedb"`, `canonicalWritesAllowed:false`.

## Manual restart gate

After applying the patch, OpenClaw must be manually restarted by the operator. Do not claim live activation before post-restart readback.

Post-restart checks:

1. `openclaw gateway status` connectivity ok.
2. Startup or registration receipt shows selected backend `qdrant-edge` or a bounded fallback reason.
3. `memory_recall` live smoke returns results and receipt includes retrieval backend plan.
4. `memory_store` smoke proves canonical write still lands in LanceDB and Qdrant remains read-index/cache only.
5. If any check fails, apply rollback patch and restart back to LanceDB.

## Known caveat
FTS still falls back to LanceDB because the current Qdrant Edge bridge is vector-only. This is intentional and tested. Dedicated Qdrant text search is a later optimization, not a live-activation blocker because LanceDB fallback is preserved.
