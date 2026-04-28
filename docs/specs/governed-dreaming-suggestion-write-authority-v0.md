# Spec — governed dreaming, suggestion judgment, and write authority v0

## Status
- Stage: **governance + bounded writer lane shipped**
- Scope: post-Dream-Lite maintenance governance plus one assist-apply canary lane
- Default posture: **zero-write by default, governor-gated write for whitelisted actions only**

## Intent
Establish a zero-write governance framework for maintenance automation after `graph synth recommend`.

This spec does **not** authorize a new autonomous write path yet.
It defines:
- who may harvest and packetize maintenance signals
- who may judge those signals
- who may write
- what receipts and rollback posture are mandatory before any future autonomous apply lane can be considered real

## Problem
`openclaw-mem` now has a bounded Dream Lite maintenance surface:
- `openclaw-mem graph synth recommend`

That surface can already surface useful next-step packets (`refresh_card`, `compile_new_card`, `no_action`).
The next risk is governance drift:
- helper lanes start acting like judges
- recommendation packets silently turn into mutation packets
- write authority becomes ambiguous across automation tiers

## Core role split

### 1) Scout/helper lane
Authorized to aggregate evidence and emit read-only recommendation packets.

Allowed:
- inspect recent evidence pressure
- run read-only recommendation surfaces
- cluster/packetize candidate actions
- attach receipts / refs / rationale / risk markers

Strictly prohibited:
- final recommendation judgment
- durable-memory or synthesis-card mutation
- hidden escalation from packetization into apply

### 2) Governor lane
Authorized to evaluate scout recommendations against the decision ladder and emit explicit governance packets.

Allowed:
- judge whether a recommendation should be ignored, retained as a proposal, or advanced toward a write gate
- combine evidence from Dream Lite, policy-loop, route-auto, and other bounded read-only surfaces
- emit a bounded governance decision packet with explicit reasons

Strictly prohibited:
- broad unbounded ingestion
- silent mutation without a write contract

### 3) Writer-of-record lane
Authorized to execute mutation only after the governor lane has produced an explicit approved packet.

Allowed:
- execute an apply path only after the governor lane has produced an explicit approved packet
- mutate only within the approved whitelist / cap / rollback contract for that lane

Requirements:
- before/after receipts are mandatory
- rollback artifact is mandatory
- every write must stay inside the approved whitelist/cap posture

Strictly prohibited:
- ad-hoc writes outside the approved packet
- mutation without before/after receipts and rollback artifact

## Decision ladder
Every maintenance candidate must end in exactly one of these outcomes:
1. `ignore`
2. `proposal_only`
3. `approved_for_apply`
4. `blocked_high_risk`

No helper lane may skip this ladder.

## Dreaming contract
"Dreaming" here means asynchronous or batch maintenance passes that try to turn accumulated evidence into better compiled truth.

Allowed dreaming behavior:
- detect repeated clusters / stale-card pressure / contradiction pressure
- propose bounded maintenance packets
- link every recommendation to source refs and receipt ids

Forbidden dreaming behavior:
- silent synthesis-card refresh
- automatic compilation of new cards without a governor decision
- broad world-wiki expansion or background content gardening

## Suggestion judgment contract
A valid judgment packet must include:
- `kind`
- `ts`
- `candidate_id`
- `recommended_action`
- `decision` (`ignore|proposal_only|approved_for_apply|blocked_high_risk`)
- `reasons[]`
- `evidence_refs[]`
- `risk_level`
- `apply_lane` (if approved)

Invariants:
- the judging lane must be explicit in the packet
- the packet must be reviewable after the fact
- recommendation and judgment must remain distinct objects

## Write-authority contract
Before any future autonomous apply path is implemented, it must inherit these rules:
- no write without an approved judgment packet
- writes must stay whitelist-scoped for the lane
- before/after receipts are mandatory
- rollback artifact is mandatory
- every write must reference the recommendation packet and the judgment packet
- any cap violation aborts before write

## Error / risk states
- missing evidence refs
- ambiguous candidate ownership
- conflicting governor decisions for the same candidate
- cap overflow
- recommendation packet too broad to review safely
- helper lane attempting to write or judge

These should fail closed for mutation and fail open for read-only recommendation surfaces.

## Current implementation surface
Shipped surfaces now follow the role split directly:

- **Scout/helper lane**
  - `openclaw-mem graph synth recommend`
  - `openclaw-mem optimize evolution-review`
- **Governor lane**
  - `openclaw-mem optimize governor-review`
- **Writer-of-record lane**
  - `openclaw-mem optimize assist-apply`

Current writer shape:
- accepts governor packets only
- applies only whitelisted low-risk observation lifecycle updates
- emits before/after + rollback receipts every run
- aborts before write on malformed packets or cap violations

The next whitelist expansion, if reopened later, must still stay behind an explicit write contract and rollback posture.

## Acceptance criteria for this governance phase
A reader should be able to answer:
1. who can scout
2. who can judge
3. who can write
4. why Dream Lite does not imply autonomous mutation
5. what artifact must exist before any future apply lane is allowed

## Non-goals / retired phase constraints
Historical v0 governance originally held "no new background jobs" and "no topology change" while the lane was plan-only.
That constraint is retired for the Dream Lite v1.9.4+ staging schedule: a deterministic cron-runner job may run read-only scout/governor/plan staging plus receipt-window verification.

Still non-goals:
- no unattended wet-run mutation without a valid plan + witness + canary gates
- no graph/store topology ownership change
- no attempt to automate the user’s whole world-model
- no role ambiguity between scout and governor

## Topology statement
- runtime/system topology changed after v1.9.4: deterministic cron-runner daily staging/verify at 03:20 Asia/Taipei is allowed
- the scheduled job is read-only for planning; write-capable `apply run` remains governed by plan + witness + rollback receipts
