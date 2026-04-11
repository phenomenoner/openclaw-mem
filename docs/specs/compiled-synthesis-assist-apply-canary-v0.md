# Spec — compiled synthesis assist-apply canary v0

## Status
- **Stage**: design / governance only
- **Scope**: post-`governor-review` canary gate for compiled-synthesis maintenance
- **Default posture**: **dry-run / zero-write by default**

## Intent
Define the smallest rollbackable bridge between governed review and future mutation for compiled-synthesis maintenance.

This spec **does not** authorize background autonomous mutation. It defines conditions under which a future canary apply lane could be considered safe enough to test.

## Why this exists
`openclaw-mem` now utilizes Dream Lite recommendation packets and governor judgment packets. To mitigate the risk of jumping straight from judgment into mutation, this spec inserts a **bounded canary gate**. The first apply path, if ever implemented, must be:
- **Packet-driven**
- **Whitelist-scoped**
- **Receipt-heavy**
- **Rollbackable**
- **Easy to turn off**

## Scope
This v0 canary contract is strictly for compiled-synthesis maintenance. 
It covers two possible actions:
1. `refresh_card`
2. `compile_new_card`

This v0 does **not** authorize arbitrary memory writes, broad world-model gardening, or auto-capture expansion.

## Required upstream artifacts
A future apply run is invalid unless **all** of the following exist:
1. **Recommendation packet**: `openclaw-mem.graph.synth.recommend.v0`
2. **Governor decision packet**: `openclaw-mem.optimize.governor-review.v0`
3. **Explicit canary invocation context**: operator / lane / scope / run id

## Apply-eligibility rules
A candidate is eligible for canary apply **only if**:
- [ ] Governor decision is exactly `approved_for_apply`
- [ ] `recommended_action` is recognized and supported by the lane
- [ ] Evidence refs are present and bounded
- [ ] Target metadata is complete enough for deterministic replay
- [ ] The lane caps below are not exceeded

Otherwise, the run **must abort before write**.

## Supported action classes (v0)

### 1) `refresh_card` (Eligible in v0)
Potentially eligible because it targets an existing canonical synthesis card.
- **Required target fields**: `recordRef`
- **Required lane mapping**: `apply_lane = graph.synth.refresh`

### 2) `compile_new_card` (Not auto-eligible in v0)
- **Reason**: Creates a new canonical artifact; scope/ownership/title ambiguity is higher; review burden is materially larger than refresh.
- **v0 posture**: Can be packetized and judged, but **cannot be auto-applied**. Requires human or later gated review surface.

## Hard caps
If any cap is exceeded, the lane **must abort before write**.
- `max_candidates_per_run`: **1**
- `max_refresh_writes_per_24h`: **3**
- `max_supported_action_classes`: **1** (`refresh_card` only in v0 canary)
- `max_retries_per_candidate`: **1**
- `max_scope_fanout_per_run`: **1**

## Required execution posture
The first apply-capable lane, if implemented later, must support:
- **`--dry-run`** first-class mode
- Explicit single-candidate execution
- Explicit operator/lane label in receipts
- Canary-only enable switch
- Rollback artifact per run
- Fail-closed mutation on malformed packets or cap violations

## Mandatory receipts

### 1) Before receipt (`kind = openclaw-mem.synth.assist-apply.before.v0`)
- **Required keys**: `run_id`, `ts`, `operator`, `lane`, `dry_run`, `recommendation_packet_ref`, `governor_packet_ref`, `candidate_id`, `target`, `caps`, `before_hashes`

### 2) After receipt (`kind = openclaw-mem.synth.assist-apply.after.v0`)
- **Required keys**: `run_id`, `ts`, `result` (`dry_run|applied|aborted|rolled_back`), `applied_count`, `blocked_reason`, `after_hashes`, `rollback_ref`, `policy`

### 3) Rollback artifact (`kind = openclaw-mem.synth.assist-apply.rollback.v0`)
- Must preserve enough information to restore the pre-run synthesis-card state or revert the newly created replacement card relationship.

## Rollback posture
The first canary lane must be reversible without DB surgery.
- **Restore** previous synthesis-card lifecycle/detail state for refresh flows.
- **Revert** new replacement cards and superseded linkages if undo is required.
- Keep rollback artifacts **local and explicit**.

## Non-goals
- No background scheduler enablement in this phase.
- No multi-candidate batch apply.
- No `compile_new_card` autonomous write in v0 canary.
- No mutation without explicit packet refs.
- No hidden fallback from malformed packet to best-effort write.

## Recommended next implementation slice
If this line continues, the next acceptable implementation slice is a **dry-run canary apply validator** that:
- Reads governor packets.
- Validates caps and supported action class.
- Emits before/after canary receipts.
- Performs **no write** unless an explicit later gate is approved.

## Topology statement
- **Runtime/system topology**: unchanged
- This spec changes governance/apply-readiness truth only.
