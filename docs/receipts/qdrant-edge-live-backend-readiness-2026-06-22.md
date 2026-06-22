# Qdrant Edge Live Backend Readiness - 2026-06-22

Status: local read-index probe ready; live gateway backend not switched.

## Verdict

Qdrant Edge is restored as a verified local read-index/cache lane in the active
Windows harness home. It is ready for an operator-approved live backend cutover
preflight, but not yet active as the live gateway retrieval backend.

Canonical writes must remain outside Qdrant Edge. SQLite/vector/text/writeback
stays the rollback path.

## Current Readback

- Package: `qdrant-edge-py==0.6.1` locked in `pyproject.toml` and `uv.lock`.
- Wrapper runtime: `openclaw-mem*.cmd` prefers
  `D:\Warehouse\Rust-OpenClaw-Core\.tmp\openclaw-mem-work\.venv\Scripts\python.exe`.
- Shard root:
  `D:\Warehouse\Rust-OpenClaw-Core\.agent-harness\memory\qdrant-edge`
- `openclaw-mem qdrant status` against the active DB reports:
  - `nativeRecallAvailable=true`
  - `vectorDimension=1536`
  - `indexedRowCount=1385`
  - `probeError=null`
  - `writesPerformed=false`
- `openclaw-mem qdrant recall --vector <1536-dim-json> --json` reports:
  - `ok=true`
  - `backend=qdrant-edge`
  - `fallbackUsed=false`
  - `hits=5`
  - `writesPerformed=false`

## Required Before Live Gateway Backend Switch

1. Preflight live harness:
   - `agent-harness.exe healthz --harness-home ... --require-writable-state`
   - `agent-harness.exe memory-service-status --harness-home ...`
   - `agent-harness.exe memory-read-path-smoke --harness-home ...`
2. Preflight Qdrant Edge:
   - dependency import through the same Python lane used by wrappers
   - `qdrant status` with `nativeRecallAvailable=true`
   - 1536-dim vector recall with `fallbackUsed=false`
   - one known semantic query parity check once a query-to-vector helper is available
3. Prepare config patch and rollback patch before applying either.
4. Apply only under explicit live-control approval/cutover.
5. Post-cutover readback must prove:
   - live recall receipt selects `qdrant-edge`, or records a bounded fallback reason
   - live recall still returns useful hits
   - store/writeback smoke keeps canonical writes out of Qdrant Edge
   - rollback patch returns the system to SQLite/vector/service-writeback

## Candidate Config Shape

The exact harness config surface must be verified before applying. The intended
retrieval backend shape is:

```json
{
  "retrievalBackend": {
    "backend": "qdrant-edge",
    "qdrantEdge": {
      "enabled": true,
      "shardRoot": "memory/qdrant-edge",
      "vectorName": "text",
      "fallbackBackend": "sqlite-vector+service-writeback",
      "searchCommand": "D:\\Warehouse\\Rust-OpenClaw-Core\\.tmp\\openclaw-mem-work\\.venv\\Scripts\\python.exe",
      "searchCommandArgs": [
        "D:\\Warehouse\\Rust-OpenClaw-Core\\.tmp\\openclaw-mem-work\\extensions\\openclaw-mem-engine\\scripts\\qdrant_edge_query_bridge.py"
      ],
      "timeoutMs": 1500
    },
    "canonicalWritesAllowed": false
  }
}
```

## Rollback

Rollback must be config-only:

- set backend back to the current SQLite/vector/service-writeback path, or remove
  the retrieval backend override;
- keep Qdrant Edge shard/cache as disposable read-index state;
- do not migrate or delete canonical memory data during rollback.

## Verification Already Passed

- `uv lock`
- `uv run --python 3.13 -- python -m unittest tests.test_cli tests.test_pack_artifacts -q`
  - 160 tests passed
- Focused Qdrant contract test passed:
  - `tests.test_cli.TestCliM0.test_service_and_qdrant_contract_probes_are_shadow_only`
- Wrapper regression passed for MCP tool descriptions, Channel A fixture, and hooks
  install-config.

## Non-Goals

- No live gateway restart in this slice.
- No live backend selection change in this slice.
- No canonical writes through Qdrant Edge.
- No claim that Qdrant Edge replaces SQLite/vector/service-writeback until live
  recall and rollback readbacks are green.
