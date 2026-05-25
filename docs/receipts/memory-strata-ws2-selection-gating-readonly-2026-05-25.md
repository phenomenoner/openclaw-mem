# Memory Strata WS2 Selection/Gating Read-only Audit — 2026-05-25

Status: **completed / read-only**  
Companion: `docs/specs/memory-strata-todo-v0.md#ws2--durable--long-term-memory-policy-hardening`  
Topology impact: **unchanged** — read-only config/source/help inspection only.

## Goal

Confirm current engine selection mode and `tier_quota_v1` gating/default state before any synthetic selection-mode fixture.

## Evidence

- Raw read-only capture: `.tmp/memory-strata-ws2/selection-gating-readonly.txt`
- Sanitized machine receipt: `docs/receipts/artifacts/memory-strata-ws2-selection-gating-readonly-2026-05-25.json`

## Findings

- Source default selection mode: `tier_first_v1`.
- Plugin schema default selection mode: `tier_first_v1`.
- Live config `autoRecall.selectionMode`: `tier_quota_v1`.
- Live config `autoRecall.enabled`: `False`.
- Live config `autoRecall.routeAuto.enabled`: `True`.
- Working Set enabled: `True`; persisted: `False`.
- Retrieval backend: `qdrant-edge`; qdrant-edge enabled: `True`; fallback: `lancedb`.

## Interpretation

`tier_quota_v1` is configured in live config, but `autoRecall.enabled=false`, so this does not prove active autoRecall injection is using quota mode. The safe next step is a synthetic fixture/copy-db regression that exercises selection behavior without touching production rows.

## Security note

The live config includes credentials. This receipt intentionally omits secret values.

## Closure

WS2 read-only gating audit is complete. Proceed to WS2 synthetic regression fixture under the WS8 stop-loss rule: no durable-touching counterfactuals against production DB.
