# 五氣朝元 — Memory Strata Stale-rule Retirement Sweep — 2026-05-25

## 1. Changed truth

Canonical memory-strata truth is now split across Store, Episodic, Docs Cold Lane, Graph, Working Set, Pack, and Promotion Governor. Derived lanes do not own durable truth. Pack lifecycle writeback is a durable mutation and is off/governed by default.

## 2. Surfaces checked

- `docs/specs/memory-strata-boundary-map-v0.md`
- `docs/specs/memory-strata-todo-v0.md`
- `docs/specs/memory-strata-blade-map-2026-05-25.md`
- `docs/specs/working-set-backbone-contract-v0.md`
- `docs/specs/graph-topology-governance-contract-v0.md`
- `docs/specs/promotion-writeback-governor-v0.md`
- `docs/specs/auto-recall-activation-vs-retention-v1.md`
- `docs/specs/verbatim-semantic-lane-v0.md`
- `extensions/openclaw-mem-engine/README.md`
- `skills/openclaw-mem` operator overlay via workspace skill reference
- relevant WS receipts under `docs/receipts/memory-strata-*2026-05-25.md`

## 3. Retired or amended stale rules

No direct stale-rule patch was applied in this sweep. The older docs found are not direct contradictions if read with the new boundary contracts:

- `auto-recall-activation-vs-retention-v1.md` already states `tier_quota_v1` default remains rollback-first / gated.
- `verbatim-semantic-lane-v0.md` already states episodic has no auto-promotion.
- Launch/relaunch docs mentioning optional mem-engine promotion are historical/product-launch surfaces, not current authority for writeback.

New canonical docs supersede ambiguous interpretation:

- `working-set-backbone-contract-v0.md`
- `graph-topology-governance-contract-v0.md`
- `promotion-writeback-governor-v0.md`
- `memory-strata-final-closure-2026-05-25.md`

## 4. Topology delta

Unchanged.

The non-stop local controller install synced a CLI symlink / skill / script and read back the active goal. It did not change Gateway, model routing, cron topology, runtime plugin enablement, or external write behavior.

## 5. Verification

- WS1–WS10 receipts exist.
- Second-brain reviews passed through final closure-bundle start.
- WS8 production lifecycle mutation was rolled back and verified absent afterward.
- Graph auto flags remain disabled; graph readiness remains red/stale/source-missing.
- Git commits exist for the memory-strata documentation/audit line through WS9.

## 6. Remaining follow-up

The carry-forward list in `docs/receipts/memory-strata-final-closure-2026-05-25.md` remains active. None of those follow-ups are silently closed by this sweep.
