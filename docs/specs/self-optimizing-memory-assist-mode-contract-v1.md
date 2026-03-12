# Spec — Self-optimizing memory 1.5a assist-mode mutation contract (v1)

## Status
- Stage: **governance/spec only** (no apply-path implementation in this phase)
- Scope: `assist` mode only
- Auto mode: **explicitly forbidden**

## Intent
Define a narrow, rollbackable mutation contract for future operator-assisted apply runs.
This document does **not** authorize autonomous mutation.

## Allowed mutable fields (exact whitelist)
Only these JSON-pointer targets inside `observations.detail_json` may change:

1. `/importance/score`
   - number in `[0.0, 1.0]`
   - absolute delta per apply `<= 0.15`
2. `/importance/label`
   - enum: `ignore | nice_to_have | must_remember | unknown`
   - must be consistent with score bucket at receipt time
3. `/lifecycle/stale_candidate`
   - boolean only
4. `/lifecycle/stale_reason_code`
   - enum: `age_threshold | repeated_miss_pressure | duplicate_cluster | operator_override`
5. `/optimization/assist`
   - object with bounded metadata only:
     - `proposal_id` (string)
     - `evidence_refs` (array of receipt refs, max 5)
     - `applied_at` (ISO-8601 UTC)
     - `operator` (string)
     - `rollback_ref` (string)

No other field is in scope.

## Explicitly forbidden
- Any write outside the whitelist above
- Insert/delete of rows in `observations`
- Mutating `summary`, `summary_en`, `tool_name`, `kind`, `ts`, `embedding_id`, scope/provenance/trust payloads, citations, or pack policy receipts
- Cross-row merge/split operations
- Any cron/config/model routing mutation as part of 1.5a
- Background/automatic apply without an operator-approved packet

## Hard budgets / caps
- `max_rows_per_apply_run`: **5**
- `max_rows_per_24h`: **20**
- `max_field_families_per_row`: **1** (`importance` OR `lifecycle`, not both in same row)
- `max_score_delta_per_row`: **0.15**
- `max_evidence_refs_per_row`: **5**
- `max_retries_per_packet`: **1**
- Must run with explicit row-id list (no wildcard query-driven mass apply)

If any cap is exceeded, run must abort before write.

## Rollback record format (required)
Each apply run must emit an append-only rollback file:

```json
{
  "kind": "openclaw-mem.optimize.assist.rollback.v1",
  "run_id": "<uuid>",
  "ts": "<iso8601>",
  "db": "<path>",
  "operator": "<id>",
  "mutations": [
    {
      "observation_id": 123,
      "proposal_id": "prop-...",
      "before_detail_json": {"...": "..."},
      "after_detail_json": {"...": "..."},
      "before_sha256": "...",
      "after_sha256": "..."
    }
  ]
}
```

Rollback operation is defined as restoring `before_detail_json` for listed `observation_id` values in order.

## Before/after receipt schema expectations
Two receipts are mandatory per run:

### 1) Before receipt
`kind = openclaw-mem.optimize.assist.before.v1`
Required keys:
- `run_id`, `ts`, `operator`, `db`, `scope`
- `packet` (approved candidate list)
- `caps` (effective cap values)
- `target_rows` (row ids)
- `before_hashes` (per-row detail hash)
- `dry_run` (bool)

### 2) After receipt
`kind = openclaw-mem.optimize.assist.after.v1`
Required keys:
- `run_id`, `ts`, `operator`
- `result` (`applied|aborted|rolled_back`)
- `applied_rows`, `skipped_rows`, `blocked_by_caps`
- `after_hashes` (per-row detail hash)
- `rollback_ref` (path/id to rollback artifact)
- `diff_summary` (field-level patch summary only; no raw sensitive text)

Both receipts must include `policy.memory_mutation` and `policy.writes_performed` for parity with existing optimize reports.

## Approval gate
Before any future implementation:
1. contract doc approved,
2. receipt schemas reviewed,
3. dry rehearsal packet validated,
4. rollback replay tested on fixture DB.

Until then, 1.5a remains parked at recommendation/shadow posture.
