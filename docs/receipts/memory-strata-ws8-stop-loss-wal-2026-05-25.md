# WS8 Stop-loss / WAL — Pack lifecycle-write production DB excursion

Status: **filed / rollback verified**  
Date: 2026-05-25  
Line: memory-strata WS1–WS10 non-stop  
Related receipt: `docs/receipts/memory-strata-ws8-pack-trace-2026-05-25.md`

## What happened

During WS8 Pack trace evaluation, a counterfactual command was run with `--pack-lifecycle-write on` without an isolated fixture DB. The command used the default production OpenClaw memory DB:

- `/root/.openclaw/memory/openclaw-mem.sqlite`

It updated `observations.detail_json.lifecycle` for two selected records:

- `obs:31998`
- `obs:48512`

The lifecycle write receipt showed:

- `memory_mutation`: `detail_json.lifecycle_refresh`
- `writes_observations`: `2`
- `used_count_before`: `0`
- `used_count_after`: `1`

## Why this matters

This was a near-miss boundary violation against the memory-strata contract:

- Pack should be treated as a consumer/trace surface when lifecycle writes are off.
- `--pack-lifecycle-write on` is a durable write path.
- WS5/WS9 must govern any future Pack → lifecycle / Working Set / durable writeback behavior.

## Correction taken

A rollback removed the lifecycle fields added by the counterfactual run.

Artifacts:

- Rollback: `docs/receipts/artifacts/memory-strata-ws8-lifecycle-write-rollback-2026-05-25.json`
- Verification: `docs/receipts/artifacts/memory-strata-ws8-rollback-verification-2026-05-25.json`

Verification result:

- `all_lifecycle_absent_after_rollback`: `true`
- `pre_write_absence_confirmed`: `false`

The pre-write field absence cannot be proven after the fact because no separate pre-mutation snapshot existed. The lifecycle write receipt did record `used_count_before=0`; the rollback verification confirms no lifecycle field remains now.

## Rule added for the rest of this line

Any counterfactual likely to touch durable state must run on one of:

1. an isolated fixture DB,
2. a copied production DB fixture, or
3. an explicitly approved production mutation window with pre-snapshot + rollback plan.

This applies especially to:

- `--pack-lifecycle-write on`
- durable memory store/import/forget
- docs ingest into production DB
- episodes ingest/redact/GC on production DB
- graph capture/refresh against production DB

## M3 entry condition

Milestone 3 may not start until this WAL is committed and second-brain review accepts the stop-loss handling.
