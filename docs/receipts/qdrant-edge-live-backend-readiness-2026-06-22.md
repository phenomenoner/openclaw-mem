# Qdrant Edge Live Backend Readiness - 2026-06-22

Status: local read-index probe ready; live gateway backend not switched.

Update 2026-06-23: live backend activation was requested, but blocked during
preflight. The Qdrant Edge shard is still usable as a local read-index/cache
when invoked through the OpenClaw-mem CLI with UTF-8 subprocess output enabled.
The active Agent Harness live recall path still reports
`sqlite-vector+service-writeback` and the current harness source hardcodes that
path in `recall_openclaw_mem_service`; a config-only patch would not activate
Qdrant Edge as the live recall backend.

## Verdict

Qdrant Edge is restored as a verified local read-index/cache lane in the active
Windows harness home. It is ready for an implementation-backed live backend
cutover preflight, but not yet active as the live gateway retrieval backend.

Canonical writes must remain outside Qdrant Edge. SQLite/vector/text/writeback
stays the rollback path.

## Current Readback

- Package: `qdrant-edge-py==0.6.1` locked in `pyproject.toml` and `uv.lock`.
- Wrapper runtime: `openclaw-mem*.cmd` used the repo-local virtual environment
  interpreter under `<openclaw-mem-repo>`.
- Shard root:
  `<harness-home>/memory/qdrant-edge`
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

2026-06-23 readback:

- `agent-harness.exe healthz --harness-home ... --require-writable-state`
  reports `ready=true`, `live=true`, all 8 loop heartbeats non-stale, and no
  stop files. The output has pre-existing sampled-ledger warnings and large
  historical queue/outbox counts; those are not Qdrant backend blockers.
- `agent-harness.exe memory-service-status --harness-home ... --json` reports
  `status=ready`, `serviceMode=local-in-process`, `activeSlotOwner=mem-engine`,
  `qdrantEdgeMode=preserved-snapshot`, and
  `qdrantNativeRecall=snapshot-preserved-native-recall-inactive`.
- `agent-harness.exe memory-read-path-smoke --harness-home ... --query
  "qdrant edge" --json` reports `status=ready`, but the recall receipt still
  uses `backend=sqlite-vector+service-writeback` and warns that Qdrant Edge is
  preserved snapshot evidence rather than the active live recall backend.
- Direct package import through the wrapper venv succeeds with import name
  `qdrant_edge`; package metadata directory is
  `qdrant_edge_py-0.6.1.dist-info`.
- Direct Qdrant status through the wrapper venv reports
  `nativeRecallAvailable=true`, `vectorDimension=1536`, `indexedRowCount=1385`,
  and `probeError=null`.
- Direct Qdrant vector recall without UTF-8 subprocess output failed on Windows
  with `UnicodeEncodeError: 'cp950' codec can't encode character ...` from
  `extensions/openclaw-mem-engine/scripts/qdrant_edge_query_bridge.py`.
- The same direct Qdrant vector recall with `PYTHONIOENCODING=utf-8` and
  `PYTHONUTF8=1` succeeds with `ok=true`, `backend=qdrant-edge`,
  `fallbackUsed=false`, and `writesPerformed=false`.

## Activation Blockers Found 2026-06-23

1. Current live Agent Harness recall does not implement Qdrant backend
   selection. Source inspection of
   `crates/agent-harness-core/src/memory.rs::recall_openclaw_mem_service`
   shows the live service recall path warns that Qdrant Edge is preserved
   snapshot evidence, then uses SQLite vector recall and sets
   `backend="sqlite-vector+service-writeback"` when vector recall is ready.
   There is no implemented read of
   `/plugins/entries/openclaw-mem-engine/config/retrievalBackend/backend` for
   live recall selection.
2. The Qdrant Edge Python bridge needs an explicit UTF-8 subprocess output
   contract on Windows. Without it, non-ASCII hit text can make the bridge fail
   before emitting JSON.
3. The status surface contains a stale/confusing mem-engine canary section:
   top-level ownership reports `activeOwner=mem-engine` and
   `promotionStatus=promoted`, while the nested `memEngineCanary` still says
   `available-not-promoted` / `activeSlotOwner=snapshot-adapter`. This is not a
   Qdrant data blocker, but it should be cleaned before using the status output
   as an operator gate.

Do not claim `qdrant-edge-live-backend` active until these blockers are fixed
and live recall readback reports `backend=qdrant-edge` or an explicit bounded
fallback reason.

## Required Before Live Gateway Backend Switch

1. Implement the live recall backend switch in Agent Harness:
   - read the verified config key, preferably
     `/plugins/entries/openclaw-mem-engine/config/retrievalBackend/backend`;
   - when it is `qdrant-edge`, embed the query with the existing harness memory
     credential bridge, call the Qdrant Edge bridge with `PYTHONIOENCODING=utf-8`
     and `PYTHONUTF8=1`, and return hits with `backend=qdrant-edge`;
   - preserve SQLite/vector/service-writeback as fallback and record fallback
     reasons in the receipt;
   - keep canonical writes outside Qdrant Edge.
2. Preflight live harness:
   - `agent-harness.exe healthz --harness-home ... --require-writable-state`
   - `agent-harness.exe memory-service-status --harness-home ...`
   - `agent-harness.exe memory-read-path-smoke --harness-home ...`
3. Preflight Qdrant Edge:
   - dependency import through the same Python lane used by wrappers
   - `qdrant status` with `nativeRecallAvailable=true`
   - 1536-dim vector recall with `fallbackUsed=false`
   - one known semantic query parity check once a query-to-vector helper is available
4. Prepare config patch and rollback patch before applying either.
5. Apply only under explicit live-control approval/cutover.
6. Post-cutover readback must prove:
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
      "searchCommand": "<openclaw-mem-repo>\\.venv\\Scripts\\python.exe",
      "searchCommandArgs": [
        "<openclaw-mem-repo>\\extensions\\openclaw-mem-engine\\scripts\\qdrant_edge_query_bridge.py"
      ],
      "timeoutMs": 1500
    },
    "canonicalWritesAllowed": false
  }
}
```

As of the 2026-06-23 preflight, this config shape is still a candidate
contract, not an activation mechanism by itself. The live harness recall path
must implement it before this patch can be used as a real backend switch.

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
