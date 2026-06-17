# Native Qdrant Recall Contract v0

## Status

- Surface: `openclaw-mem qdrant *`
- Posture: read-only status and fail-closed native recall probe
- Default fallback: SQLite pack/search lane
- Writes: none

## Modes

`qdrantNativeRecall` is one of:

- `not-present`: no qdrant-edge artifact found next to the configured DB.
- `snapshot-preserved`: qdrant-edge artifact exists, but native recall is not active.

Future implementations may add `active` and `stale`, but v0 does not claim active native recall.

## Commands

```powershell
openclaw-mem qdrant status --db .agent-harness\memory\openclaw-mem.sqlite --json
openclaw-mem qdrant recall --db .agent-harness\memory\openclaw-mem.sqlite --query "memory engine recovery" --json
```

## `qdrant status`

Emits `openclaw-mem.qdrant.status.v0` with:

- `qdrantNativeRecall`
- `path`
- `collection`
- `vectorDimension`
- `embeddingModelNamespace`
- `indexedRowCount`
- `lastRefresh`
- `nativeRecallAvailable`
- `fallback`
- `writesPerformed`

For v0, `nativeRecallAvailable=false`.

## `qdrant recall`

Emits `openclaw-mem.qdrant.recall.v0`. If native recall is not active, it returns:

```json
{
  "ok": false,
  "error": "native_qdrant_recall_not_active",
  "fallback": "use openclaw-mem pack/search sqlite lane"
}
```

This is fail-closed by design so callers do not mistake SQLite fallback for native Qdrant evidence.

## Verification

```powershell
uv run --python 3.13 pytest tests/test_cli.py::TestCliM0::test_service_and_qdrant_contract_probes_are_shadow_only -q
openclaw-mem qdrant status --json
openclaw-mem qdrant recall --query "memory engine recovery" --json
```
