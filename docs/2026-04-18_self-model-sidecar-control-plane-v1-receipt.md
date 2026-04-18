# self-model side-car control plane v1 receipt

Date: 2026-04-18
Branch: `lyria/self-model-control-plane-v1-20260418`
Status: implemented, verifier-backed
Topology: unchanged

## Change
Upgraded the continuity side-car control plane from one-shot weakening receipts into explicit state-transition governance receipts.

## What landed
- extended continuity release control to support `weaken`, `retire`, and `rebind`
- each governance receipt now records:
  - `before_release_state`
  - `after_release_state`
  - `supersedes_receipt_id`
- latest release application now preserves control-state transition metadata on live attachments
- added `continuity release-history` for auditable control-plane inspection
- added verifier coverage for weaken -> rebind -> retire flow and resulting snapshot behavior

## Why now
After adjudication v1, the next honest backlog slice was the control plane itself.
This pass makes state transitions replayable and inspectable without starting claim-graph persistence.

## Verifiers run
```bash
python3 -m unittest tests.test_self_model_sidecar -v
```

Result: 8 tests, all green.

## Remaining truth
- control transitions are now explicit, but rebuild / migration approval are still separate future surfaces
- retired claims remain represented by receipts plus filtered snapshots, not lifecycle-aware claim objects
- this pass does not yet add counterfactual anti-delusion instrumentation

## Rollback
- revert `openclaw_mem/self_model_sidecar.py`, `openclaw_mem/cli.py`, and `tests/test_self_model_sidecar.py`
- remove `docs/2026-04-18_self-model-sidecar-control-plane-v1-receipt.md`
- rerun `python3 -m unittest tests.test_self_model_sidecar -v`

## Files changed
- `openclaw_mem/self_model_sidecar.py`
- `openclaw_mem/cli.py`
- `tests/test_self_model_sidecar.py`
- `docs/2026-04-18_self-model-sidecar-control-plane-v1-receipt.md`
