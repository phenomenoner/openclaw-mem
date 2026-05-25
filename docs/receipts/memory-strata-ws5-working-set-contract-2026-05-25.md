# Memory Strata WS5 Working Set / Backbone Contract — 2026-05-25

Status: **completed / documentation contract**  
Companion: `docs/specs/working-set-backbone-contract-v0.md`  
Topology/data impact: **unchanged** — read-only config inspection and docs only.

## Goal

Define the Working Set / Backbone contract before any activation/writeback default changes.

## Evidence

- Contract: `docs/specs/working-set-backbone-contract-v0.md`
- Config receipt: `docs/receipts/artifacts/memory-strata-ws5-working-set-config-2026-05-25.json`
- WS8 incident: `docs/receipts/memory-strata-ws8-stop-loss-wal-2026-05-25.md`

## Current config snapshot

- `workingSet.enabled = true`
- `workingSet.persist = false`
- `workingSet.maxChars = 900`
- `workingSet.maxItemsPerSection = 3`
- `workingSet.maxGoalChars = 180`
- `workingSet.maxItemChars = 160`

## Contract decisions

- Working Set is a derived activation artifact, not a truth owner.
- Working Set items must cite or derive from governed sources.
- Persisted Working Set artifacts are caches and need TTL/stale detection.
- Pack lifecycle writeback is a real durable write path and remains off by default.
- Pack lifecycle writeback must not become a hidden Working Set updater.
- Any durable-touching counterfactual must use fixture/copy DB or approved mutation window with pre-snapshot + rollback.

## WS8 case incorporated

WS8 proved that `--pack-lifecycle-write on` mutates `observations.detail_json.lifecycle`. The contract therefore gates Pack lifecycle writeback behind WS9 governance before any default/runtime use.

## Verifier

- Config inspected read-only.
- Contract explicitly names ownership, allowed sources, trace requirements, persistence/TTL, writeback gate, fixture rule, and non-goals.
- No code/config/runtime changes were made.

## Closure

WS5 is complete as a boundary contract. It does not enable persisted Working Set or Pack lifecycle writeback.
