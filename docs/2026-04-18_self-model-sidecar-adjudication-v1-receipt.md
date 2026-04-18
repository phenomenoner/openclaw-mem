# self-model side-car adjudication v1 receipt

Date: 2026-04-18
Branch: `lyria/self-model-adjudication-v1-20260418`
Status: implemented, verifier-backed
Topology: unchanged

## Change
Promoted continuity adjudication from passive metadata into a deterministic rule surface, and added a bounded public-safe export lane.

## What landed
- added executable adjudication policy `self_model_sidecar_adjudication_v1`
- each derived attachment now carries:
  - `adjudication_state`
  - `adjudication_reasons`
  - publication visibility flags and hedge text
- added `continuity adjudication` for operator-safe state inspection
- added `continuity public-summary` for restrained public-safe continuity export
- attachment-map now reports adjudication counts
- snapshot/diff/threat outputs now carry adjudication context
- added negative fixtures for:
  - prior-only claim
  - low-evidence high-coherence claim
  - contested claim under contradiction pressure
  - weakened claim requiring revalidation

## Why now
The remaining honest gate after governance hardening was adjudication theater.
This pass makes the state model inspectable and deterministic enough for downstream control-plane work, without starting claim-graph persistence.

## Verifiers run
```bash
python3 -m unittest tests.test_self_model_sidecar -v
```

Result: 6 tests, all green.

## Remaining truth
- this is still rule-only adjudication over snapshot attachments, not lifecycle-aware claim objects
- `retired` remains a control-plane state expressed through release receipts rather than persisted current-snapshot claims
- public-safe summary stays deliberately narrow and does not attempt rich narrative identity rendering

## Rollback
- revert `openclaw_mem/self_model_sidecar.py`, `openclaw_mem/cli.py`, and `tests/test_self_model_sidecar.py`
- remove `docs/2026-04-18_self-model-sidecar-adjudication-v1-receipt.md`
- rerun `python3 -m unittest tests.test_self_model_sidecar -v`

## Files changed
- `openclaw_mem/self_model_sidecar.py`
- `openclaw_mem/cli.py`
- `tests/test_self_model_sidecar.py`
- `docs/2026-04-18_self-model-sidecar-adjudication-v1-receipt.md`
