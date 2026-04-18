# self-model side-car MSP implementation receipt

Date: 2026-04-18
Branch: `feat/self-model-sidecar-msp`
Status: implemented on branch, verifier-backed
Topology: unchanged

## What landed
- continuity/self side-car CLI family:
  - `openclaw-mem continuity current`
  - `openclaw-mem continuity attachment-map`
  - `openclaw-mem continuity threat-feed`
  - `openclaw-mem continuity diff`
  - `openclaw-mem continuity release`
  - `openclaw-mem continuity compare-migration`
  - `openclaw-mem continuity enable|status|auto-run|disable`
- compatibility alias: `openclaw-mem self ...`
- new domain module: `openclaw_mem/self_model_sidecar.py`
- operator skill card: `skills/self-model-sidecar.ops.md`
- spec pack checked in under `docs/specs/self-model-sidecar-*.md`
- focused tests: `tests/test_self_model_sidecar.py`

## Boundary kept true
- reads only from `observations` / `episodic_events` and optional file inputs
- writes only under side-car `run_dir` receipts/snapshots
- no writes into core memory-of-record
- outputs are labeled derived/non-authoritative and use `continuity` as the operator surface

## Claude second-brain review
Reviewer lane: standalone Claude (`opus`)
Review focus:
- correctness
- CLI contract honesty
- rebuildability boundaries
- obvious regressions

Findings addressed in this pass:
1. compare-migration persistence no longer writes `latest.json`
2. file-only continuity paths avoid unnecessary DB init (`diff`, `release`, snapshot-backed `attachment-map` / `threat-feed`)
3. release receipts are scope/session-aware
4. snapshot-backed file-only paths and control-plane commands avoid unnecessary DB init
5. false `warm` vs `concise` tension pair removed
6. CLI help wording tightened

## Verifiers run
```bash
python3 -m unittest tests.test_self_model_sidecar tests.test_defaults -v
```

Result: 6 tests, all green.

## Remaining truth
- heuristics are intentionally simple v0 scoring, not model-based identity inference
- autonomous scheduling is currently bounded CLI-driven (`auto-run` / enable-disable config), not yet cron/plugin-driven
- release receipts are governed but still lightweight JSON receipts, not a heavier control plane
