# self-model side-car governance hardening receipt

Date: 2026-04-18
Branch: `lyria/self-model-governance-hardening-20260418`
Status: implemented, verifier-backed
Topology: unchanged

## Change
Hardened the continuity side-car across the three gating areas called out by cross-validation:
1. authority-invariant resistance against accidental core DB writes
2. governed enable/disable reversibility with residue receipts
3. adjudicable provenance on derived continuity claims

## What landed
- added SQLite query-only runtime guard around snapshot build, migration compare, and autorun read paths
- exported `db_readonly_guard()` for explicit tests and future verifier reuse
- enriched attachments with:
  - `confidence`
  - `band`
  - `fragility`
  - `contradiction_pressure`
  - `release_state`
  - `latest_release_receipt_id`
  - per-attachment provenance payload
- added top-level provenance to snapshot, attachment-map, threat-feed, diff, compare-migration, and autorun receipts
- diff artifacts now carry:
  - `drift_class`
  - `risk_flags`
  - declared arbiter policy metadata
- enable/disable control changes now emit control-history receipts
- disable clears the active `latest.json` pointer and records the cleared snapshot id
- control/status now expose residue summary for snapshot/release/autorun state
- control receipt filenames now include a millisecond suffix to avoid audit-log clobbering

## Why now
Cross-validation said the line would stall below 8/10 unless restraint stopped living only in docs and operator judgment.
This pass turns the strongest claims into verifiable behavior:
- read paths are SQL-read-only while deriving continuity state
- disable leaves no active latest-pointer residue
- derived claims expose enough provenance to be triaged instead of merely admired

## Verifiers run
```bash
python3 -m unittest tests.test_self_model_sidecar -v
```

Result: 5 tests, all green.

## Claude second-brain review
Primary review receipt:
- `/root/.openclaw/workspace/.state/decision-council/claude_self_model_sidecar_governance_review.md`

Follow-up pass after fixes:
- `/root/.openclaw/workspace/.state/decision-council/claude_self_model_sidecar_governance_review_pass2.md`

## Remaining truth
- `arbiter_policy` is still policy metadata, not an executable dispute-resolution engine
- query-only guard protects SQL writes, not filesystem writes; filesystem writes remain intentional in the side-car run dir
- schemas gained additive fields on `v0`; downstream strict-schema consumers may need an explicit compatibility note or version bump in a later pass
- disable clears the active pointer but does not reconstruct a previous pointer automatically; re-enable still rebuilds via fresh snapshot generation

## Rollback
- revert the patch for `openclaw_mem/self_model_sidecar.py`, `openclaw_mem/cli.py`, and `tests/test_self_model_sidecar.py`
- remove `docs/2026-04-18_self-model-sidecar-governance-hardening-receipt.md`
- rerun `python3 -m unittest tests.test_self_model_sidecar -v`

## Files changed
- `openclaw_mem/self_model_sidecar.py`
- `openclaw_mem/cli.py`
- `tests/test_self_model_sidecar.py`
- `docs/2026-04-18_self-model-sidecar-governance-hardening-receipt.md`
