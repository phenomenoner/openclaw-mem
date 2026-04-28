# Spec — Dream Lite apply canary + self-reflection sidecar v0

## Status
- **Stage**: product / engineering spec
- **Scope**: post-`graph synth recommend` + `optimize governor-review` apply-capable canary
- **Default posture**: **dry-run first, governor-gated, rollbackable, local-only**
- **Mutation posture**: `refresh_card` only in v0; `compile_new_card` remains proposal-only

## Verdict
Proceed with a narrow Option 3: evolve Dream Lite from a zero-write recommendation loop into a **governed apply canary** that can refresh existing compiled-synthesis cards only after explicit governor approval.

The self-mode / self-reflection sidecar should participate as a **witness and reflection emitter**, not as a judge or writer. It makes the loop more product-magical without weakening authority boundaries.

In one line:

> Dream Lite may apply a tiny, reversible card refresh; the sidecar watches what changed, writes a reflection delta, and can flag coherence risk before the change becomes normal operating truth.

## Problem
Dream Lite already surfaces useful maintenance packets:
- `refresh_card`
- `compile_new_card`
- `no_action`

`optimize governor-review` already adds a zero-write judgment ladder:
- `ignore`
- `proposal_only`
- `approved_for_apply`
- `blocked_high_risk`

The remaining product gap is the safe bridge from **approved recommendation** to **actual maintained compiled truth**. If every approved refresh still requires manual application, Dream Lite remains advisory only. If auto-apply is too broad, it becomes hidden mutation and breaks the trust model.

The sidecar gap is adjacent: self-mode artifacts can notice behavior/persona drift, but they should not become durable truth owners. They need a governed way to witness and reflect on maintenance events.

## Product promise
Agents should not just remember. They should:
1. notice what is stale,
2. decide what is safe to update,
3. apply only the smallest reversible refresh,
4. leave a receipt and rollback handle,
5. reflect on whether the change shifts behavior or self-model.

User-facing promise:

> You wake up to a reviewable dream-apply receipt, not a silently mutated memory wiki.

## Scope v0
Included:
- apply-capable lane for `refresh_card` only
- hard precondition: matching governor decision is `approved_for_apply`
- dry-run planning before any wet run
- one candidate per run
- local receipt + rollback artifact per apply
- sidecar witness packet before/after apply
- verifier that can replay receipt integrity and rollback readiness

Excluded:
- `compile_new_card` auto-apply
- background scheduler enablement
- broad durable-memory writes
- self-sidecar approval authority
- graph-as-truth or personal-wiki expansion
- OpenClaw core `/dreaming` integration
- network / remote / GitHub writes

## Architecture

```text
Dream Lite recommendation
  openclaw-mem graph synth recommend
        |
        v
Governor judgment
  openclaw-mem optimize governor-review
        |
        v
Dream Lite apply canary
  validate -> dry-run -> snapshot -> sidecar witness -> apply -> receipt
        |
        v
Self-reflection sidecar
  witness packet -> reflection delta -> optional rollback flag
```

### Proposed command surface

Primary surface:

```bash
openclaw-mem dream-lite apply plan --governor-packet <path> --out <receipt.json>
openclaw-mem dream-lite apply run --plan <receipt.json>
openclaw-mem dream-lite apply rollback <receipt-id>
openclaw-mem dream-lite apply verify [--since <duration>]
```

Naming note: prefer `dream-lite apply` over `dream apply` to avoid confusion with OpenClaw core dreaming.

## Data / receipt contract

### Apply plan / receipt

Kind: `openclaw-mem.dream-lite.apply.v0`

Required fields:
- `run_id`
- `ts`
- `mode`: `dry_run | applied | aborted | rolled_back`
- `recommendation_packet_ref`
- `governor_packet_ref`
- `candidate_id`
- `recommended_action`: must be `refresh_card` in v0
- `governor_decision`: must be `approved_for_apply`
- `target.recordRef`
- `target.before_hash`
- `dry_run.diff_summary`
- `snapshot_ref`
- `sidecar_witness_ref`
- `after_hash` when applied
- `rollback_ref`
- `blocked_reason` when aborted

### Rollback artifact

Kind: `openclaw-mem.dream-lite.apply.rollback.v0`

Must contain enough local data to restore the exact pre-apply card state without DB surgery.

Required fields:
- `rollback_id`
- `apply_run_id`
- `target.recordRef`
- `before_hash`
- `after_hash`
- `restore_payload_ref`
- `created_at`

### Self-reflection witness packet

Kind: `openclaw-mem.self-reflection.dream-witness.v0`

Allowed verdicts:
- `ok`
- `flagged`
- `missing`

Required fields:
- `witness_id`
- `apply_run_id`
- `ts`
- `verdict`
- `reflection_delta_ref`
- `reasons[]`
- `coherence_risk`: `low | medium | high | unknown`

Rules:
- `flagged` blocks wet-run by default.
- `missing` blocks wet-run by default unless an explicit operator flag overrides it.
- sidecar may recommend rollback, but rollback still goes through the apply receipt path.

## Safety gates
Any failed gate aborts before mutation.

1. **Packet gate**: recommendation kind and schema are valid.
2. **Action gate**: action is exactly `refresh_card`.
3. **Governor gate**: decision is exactly `approved_for_apply`.
4. **TTL gate**: governor packet is fresh enough for apply.
5. **Target gate**: `recordRef` exists and maps to one canonical synthesis card.
6. **Hash gate**: current target hash matches expected pre-apply hash.
7. **Fanout gate**: one candidate, one target, one apply lane.
8. **Dry-run gate**: diff is bounded and reviewable.
9. **Snapshot gate**: rollback artifact is written and verified before wet-run.
10. **Sidecar gate**: witness verdict is `ok`, unless explicit override is provided.
11. **Rate gate**: apply count stays below configured canary cap.

Default caps:
- `max_candidates_per_run = 1`
- `max_refresh_writes_per_24h = 3`
- `max_diff_lines = 200`
- `max_retries_per_candidate = 1`

## Self-mode sidecar synergy
The sidecar should make the feature feel alive without becoming authority.

Allowed sidecar responsibilities:
- read Dream Lite apply plans and receipts
- compare the planned refresh against recent self-mode journal / persona receipts
- emit a reflection delta explaining behavioral or self-model impact
- flag coherence risk before wet-run
- recommend rollback after apply if the reflection window surfaces a mismatch

Forbidden sidecar responsibilities:
- create `refresh_card` apply packets
- upgrade `proposal_only` to `approved_for_apply`
- mutate synthesis cards or durable memory directly
- override Lyria / governor judgment upward

Product interpretation:
- Dream Lite maintains compiled knowledge.
- Governor decides whether maintenance is safe.
- Apply canary executes the smallest reversible refresh.
- Self sidecar explains what the change means to the agent's self-model.

## UX / demo flow

```bash
openclaw-mem graph synth recommend --json > recommend.json
openclaw-mem optimize governor-review --recommendations recommend.json --json > governor.json
openclaw-mem dream-lite apply plan --governor-packet governor.json --out apply-plan.json
openclaw-mem dream-lite apply run --plan apply-plan.json
openclaw-mem dream-lite apply verify --since 24h
```

Demo success line:

> One stale synthesis card refreshes itself through a governor-approved, sidecar-witnessed, rollbackable receipt chain.

A reviewer should be able to answer in under 30 seconds:
- What changed?
- Why was it allowed?
- Which source packets justified it?
- What did the sidecar think it meant?
- How do we undo it?

## Success criteria
- `compile_new_card` is never auto-applied in v0.
- malformed / stale / ambiguous packets abort before write.
- every applied run has before/after hashes and rollback artifact.
- rollback restores the previous state byte-for-byte for the target card.
- sidecar witness coverage is visible in receipts.
- verifier can detect missing receipt fields, hash mismatch, missing rollback artifact, and sidecar-flagged applies.
- runtime/system topology remains unchanged in v0.

## Verifier plan
Minimum tests / checks:
- schema validation for apply and rollback receipts
- negative tests for each safety gate
- dry-run produces no card mutation
- hash mismatch aborts wet-run
- `compile_new_card` with forged approval is rejected
- sidecar `flagged` blocks wet-run
- sidecar `missing` blocks wet-run unless explicit override is set
- apply -> rollback -> diff returns empty
- repeated run on same receipt is idempotent or aborts as already-applied

Suggested verifier command:

```bash
openclaw-mem dream-lite apply verify --json
```

## Rollout phases

### Phase 0 — Spec and schema
Land this spec and JSON schema(s). No mutation.

### Phase 1 — Dry-run-only lane
Implement `plan` and `run --dry-run`, emit receipts, wire sidecar as read-only witness. Review receipts manually for at least one week or 20 planned applies.

### Phase 2 — Wet-run canary
Allow wet-run for `refresh_card` only, one candidate per run, with rollback exercised intentionally before calling the lane healthy.

### Phase 3 — Blocking self-reflection witness
Make sidecar `flagged` verdict a default hard block and feed reflection deltas back into future recommendation context.

### Phase 4 — Cohort expansion only if metrics are clean
Raise caps or widen eligible target set. Do not add `compile_new_card` auto-apply without a separate spec.

## Open questions
1. Should apply receipts live inside the tracked repo, or under durable local state with periodic export?
2. What is the right TTL for governor approval before apply: 1h, 6h, or 24h?
3. Should sidecar witness be required for every wet-run, or only after Phase 3?
4. What is the exact reflection delta schema used by self-mode sidecar?
5. Does rollback refuse if a human edited the card after apply, or produce conflict artifacts?
6. Should this lane be exposed as `dream-lite apply` or folded under `optimize assist-apply` after proof?

## Non-regression constraints
- Do not confuse this with OpenClaw core dreaming.
- Do not turn self-mode sidecar into durable memory authority.
- Do not expand from `refresh_card` to new-card creation by flag only.
- Do not mutate without receipts and rollback.
- Do not provision background cron in v0.

## Topology statement
- Runtime/system topology: unchanged in this spec.
- Live cron topology: unchanged.
- Authority/document topology: changed by defining the next apply-capable product gate.
