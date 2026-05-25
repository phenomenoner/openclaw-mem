# Memory Strata WS2 Durable / Long-term Policy Hardening — 2026-05-25

Status: **completed / synthetic selection fixture**  
Companion: `docs/specs/memory-strata-todo-v0.md#ws2--durable--long-term-memory-policy-hardening`  
Topology/data impact: **unchanged** — source inspection + existing unit tests + synthetic in-process fixture only; no production DB writes.

## Goal

Verify whether quota-mode selection separates retention priority from activation priority by preventing a large `must_remember` pool from monopolizing prompt activation.

## Artifacts

- Read-only gating audit: `docs/receipts/memory-strata-ws2-selection-gating-readonly-2026-05-25.md`
- Synthetic fixture result: `docs/receipts/artifacts/memory-strata-ws2-selection-synthetic-2026-05-25.json`
- Unit-test output: `.tmp/memory-strata-ws2/tier-selection-test.out`

## Gating finding

- Source/plugin default remains `tier_first_v1`.
- Live config sets `autoRecall.selectionMode=tier_quota_v1`, but `autoRecall.enabled=false`.
- Therefore quota mode is configured but not proof of active autoRecall injection behavior.

## Synthetic fixture

Scenario: must pool saturation vs nice reservation.

- Limit: `4`
- Quotas: `{'mustMax': 2, 'niceMin': 2, 'unknownMax': 1}`
- `tier_quota_v1` selected: `['m1', 'm2', 'n1', 'n2']`
- `tier_first_v1` selected: `['m1', 'm2', 'm3', 'm4']`

## Checks

| Check | Result |
|---|---:|
| quota_caps_must_at_2 | PASS |
| quota_reserves_nice_at_2 | PASS |
| quota_selected_expected | PASS |
| tier_first_saturates_must | PASS |

## Existing unit-test verifier

`node --test extensions/openclaw-mem-engine/tierSelection.test.mjs` passed:

- tests: 10
- pass: 10
- fail: 0

Covered behaviors include:

- deterministic score/recency tie-break
- `tier_quota_v1` must cap + nice reservation
- wildcard spill
- robustness with empty tiers
- budget-lower-than-quota behavior
- `tier_first_v1` early exit / must saturation behavior

## Boundary notes

- No selection-mode config was changed.
- No production memories were inserted, edited, forgotten, or re-ranked.
- This fixture validates the selector mechanics only; it does not prove live runtime autoRecall injection quality.

## Product conclusions

- `tier_quota_v1` does what the product needs mechanically: it can cap must saturation and reserve nice recall under a constrained activation budget.
- `tier_first_v1` preserves rollback/default behavior and can saturate activation with must records.
- Promotion of quota mode as runtime default still requires a live-style autoRecall fixture with receipt fields and a full WS10 quality rerun.

## Carry-forward to WS5 / WS9

- Working Set dedupe and Pack lifecycle writeback must remain separate from quota selection.
- Any future default/runtime change requires second-brain review and push-review gate.

## Closure

WS2 is complete for this milestone as a verifier-backed product mechanics audit. It is not a runtime enablement claim.
