# Remote Mem-Engine Service Contract v0

## Status

- Surface: `openclaw-mem service *`
- Posture: contract-first, shadow-only
- Writes: none
- Active ownership: never granted by v0 commands

## Commands

```powershell
openclaw-mem service status --json
openclaw-mem service recall --query "memory engine recovery" --limit 5 --json
openclaw-mem service lease --owner agent-harness --ttl-ms 60000 --json
```

## `service status`

Emits `openclaw-mem.service.status.v0` with:

- `serviceVersion`
- `engineOwnerId`
- `activeSlotId`
- `rollbackSlotId`
- `shadowMode`
- `promotionReady`
- `promotionBlockedReasons`
- `graphReadiness`
- `embeddingModelNamespace`
- `qdrantNativeRecallMode`
- `dbPath`
- `writesPerformed`

In v0, `shadowMode` is true, `promotionReady` is false, and promotion is blocked until a fresh heartbeat, compatible schema version, and rollback proof exist.

## `service recall`

Emits `openclaw-mem.service.recall.v0`. It uses the local pack lane to produce a comparable `context_pack` receipt while keeping `activePromptOwner=false`.

## `service lease`

Emits `openclaw-mem.service.lease.v0`. A v0 lease is a shadow contract receipt only. Stale leases are never active owners:

```json
{
  "activeOwner": false,
  "staleLeaseIsActiveOwner": false
}
```

## Verification

```powershell
uv run --python 3.13 pytest tests/test_cli.py::TestCliM0::test_service_and_qdrant_contract_probes_are_shadow_only -q
openclaw-mem service status --json
openclaw-mem service lease --owner agent-harness --ttl-ms 60000 --json
```
