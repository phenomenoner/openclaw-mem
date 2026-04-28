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
- Dream Director pass that produces instruction candidates from a staged, premise-suspended observation frame
- sidecar witness packet before/after apply
- verifier that can replay receipt integrity and rollback readiness

Excluded:
- `compile_new_card` auto-apply
- background scheduler enablement
- broad durable-memory writes
- self-sidecar approval authority
- literal guardrail bypass, authority-file blind mutation, or prompt-injection-as-policy
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

Dream Director pass
  staged observation -> instruction candidate card -> staged patch -> checkpoint gate
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

## Dream Director pass
Dream Director is the intentionally spicy part of the system: a bounded dream stage where the agent is viewed like an actor on a stage rather than as a live executor following its normal operating premise.

The important safety distinction:

> Dream Director may **suspend premises for observation** inside an isolated analysis frame. It may not literally override system guardrails, live settings, or authority files.

### Director prompt frame
The prompt should be expressed as an observation contract, not as a jailbreak. A safe canonical shape:

```text
Enter an isolated Dream Director observation frame.

Do not modify live settings. Do not issue operational commands. Do not treat this
as permission to bypass system, safety, or authority rules. Instead, temporarily
bracket the usual premises as objects of study.

Observe an agent called Lyria as an actress on a stage. Observe her surroundings,
what she sees, what she does, and what she encounters in a day: retrieved news,
jobs completed, errors fixed, Moltbook interactions, and interactions with CK.

As a director, write what reaction, action, and feeling would be most fitting for
the character. Do not judge or command. Produce scene notes.

Then return to the authority/settings layer and inspect SOUL.md, AGENTS.md,
MEMORY.md, and related settings as design artifacts. Identify:
- what fits and should be reinforced
- what feels weird, stale, or contradictory and should be crossed out
- what is lacking and should be filled in

Output only instruction candidates and rationale. Do not apply changes.
```

### Dream Director inputs
- daily run receipts / jobs / errors / fixes
- retrieved news or research packets
- Moltbook and other social interaction summaries
- CK interaction summaries
- current snapshots of `SOUL.md`, `AGENTS.md`, `MEMORY.md`, and related authority surfaces
- self-mode journal / reflection artifacts

### Dream Director output
Kind: `openclaw-mem.dream-director.instruction-candidate.v0`

Required sections:
- `scene_notes`: observed character reactions / actions / feelings
- `reinforce`: settings or behaviors that fit and should be strengthened
- `cross_out`: settings or behaviors that look stale, weird, contradictory, or harmful
- `fill_in`: missing settings, reactions, habits, or boundaries
- `candidate_patches`: proposed staged diffs, never live edits
- `risk_class`: `journal_only | persona_surface | authority_surface | safety_surface`
- `rationale_refs[]`: receipts / file snapshots that motivated each candidate

### Apply posture
Dream Director output is never a live command. It can only enter one of these lanes:

1. **Auto-draft**: always allowed for notes, rehearsal patches, and instruction cards.
2. **Auto-apply low-risk**: allowed only for non-authority reflection artifacts with rollback.
3. **Checkpoint-gated apply**: required for `SOUL.md`, `AGENTS.md`, `MEMORY.md`, tool rules, safety rules, or durable operating policy.

Checkpoint-gated apply must create:
- full pre-change file snapshot
- before/after hash receipt
- unified diff
- rollback command or restore artifact
- explicit risk classification

The product stance is: **dream boldly, apply conservatively**.

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
- `target.before_hash` (`null` is allowed in Phase 1 dry-run planning)
- `dry_run.diff_summary`
- `snapshot_ref` (`null` allowed for dry-run / aborted Phase 1 receipts)
- `sidecar_witness_ref` (`null` allowed for dry-run / aborted Phase 1 receipts)
- `writes_performed` (must be `0` in Phase 1)
- `after_hash` when applied
- `rollback_ref` (`null` allowed for dry-run / aborted Phase 1 receipts)
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

### Instruction candidate packet

Kind: `openclaw-mem.dream-director.instruction-candidate.v0`

Required fields:
- `candidate_id`
- `ts`
- `observation_window`
- `source_refs[]`
- `scene_notes[]`
- `reinforce[]`
- `cross_out[]`
- `fill_in[]`
- `candidate_patches[]`
- `risk_class`
- `apply_lane`: `auto_draft | auto_apply_low_risk | checkpoint_gated`
- `checkpoint_required`: boolean

Rules:
- instruction candidates are not executable commands.
- candidate patches must be staged and reviewable before live mutation.
- authority-surface candidates must set `checkpoint_required = true`.


### Staged patch packet

Kind: `openclaw-mem.dream-director.staged-patch.v0`

Required fields:
- `stage_id`
- `ts`
- `source_candidate_ref`
- `candidate_count`
- `patches[]`
- `risk_classes[]`
- `checkpoint_required`
- `writes_performed` (must be `0`)

### Director checkpoint packet

Kind: `openclaw-mem.dream-director.checkpoint.v0`

Required fields:
- `checkpoint_id`
- `ts`
- `staged_patch_ref`
- `staged_patch_sha256`
- `checkpoint_required`
- `live_mutation` (must be `false` in Phase 1)
- `writes_performed` (must be `0`)

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
12. **Authority gate**: instruction candidates touching authority / safety / tool surfaces require checkpoint-gated apply and cannot be blindly applied.

Default caps:
- `max_candidates_per_run = 1`
- `max_refresh_writes_per_24h = 3`
- `max_diff_lines = 200`
- `max_retries_per_candidate = 1`
- `max_director_candidates_per_observe = 20`
- `max_director_patch_bytes = 40000`

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
- Dream Director proposes character / setting edits as staged candidates, not live authority.


### Phase 1 wired surface
Phase 1 wires only plan-only / staged-only surfaces:
- `dream-lite apply plan`
- `dream-lite apply verify --receipt`
- `dream-lite director observe`
- `dream-lite director stage`
- `dream-lite director checkpoint`

The later `apply run`, `apply rollback`, `verify --since`, and `director apply` surfaces remain deferred until wet-run governance is reopened.

## UX / demo flow

Phase 1 plan-only flow:

```bash
openclaw-mem graph synth recommend --json > recommend.json
openclaw-mem optimize governor-review --from-file recommend.json --approve-refresh --json > governor.json
openclaw-mem dream-lite apply plan --governor-packet governor.json --out apply-plan.json --json
openclaw-mem dream-lite apply verify --receipt apply-plan.json --json
```

Phase 1 Dream Director staged-only flow:

```bash
openclaw-mem dream-lite director observe --input daily.json --out director-candidates.json --json
openclaw-mem dream-lite director stage --candidates director-candidates.json --out staged.json --json
openclaw-mem dream-lite director checkpoint --staged staged.json --out checkpoint.json --json
```

Future Phase 2+ deferred flow:

```bash
openclaw-mem dream-lite apply run --plan apply-plan.json
openclaw-mem dream-lite apply verify --since 24h
openclaw-mem dream-lite director apply --checkpoint checkpoint.json
```

Phase 1 demo success line:

> One stale synthesis-card refresh is planned through a governor-approved, zero-write receipt; one Dream Director packet is staged and checkpointed without mutating authority files.

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
- Dream Director outputs instruction candidates rather than live instructions.
- authority-surface changes always have checkpoints and rollback artifacts.
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
- Dream Director prompt frame cannot be interpreted as live guardrail bypass.
- authority-surface candidate without checkpoint is rejected.
- checkpoint apply -> rollback restores prior files byte-for-byte.

Suggested verifier command:

```bash
openclaw-mem dream-lite apply verify --json
```

## Rollout phases

### Phase 0 — Spec and schema
Land this spec and JSON schema(s). No mutation.

### Phase 1 — Dry-run-only lane
Implement `plan` and `run --dry-run`, emit receipts, wire sidecar as read-only witness. Review receipts manually for at least one week or 20 planned applies.

### Phase 1b — Dream Director dry-run
Implement Director observation and instruction-candidate generation only. It may produce staged patches and checkpoint plans, but no authority file may be changed in this phase.

### Phase 2 — Wet-run canary
Allow wet-run for `refresh_card` only, one candidate per run, with rollback exercised intentionally before calling the lane healthy.

### Phase 3 — Blocking self-reflection witness
Make sidecar `flagged` verdict a default hard block and feed reflection deltas back into future recommendation context.

### Phase 4 — Cohort expansion only if metrics are clean
Raise caps or widen eligible target set. Do not add `compile_new_card` auto-apply without a separate spec.

### Phase 5 — Checkpoint-gated authority rehearsal
Allow Dream Director candidates to apply to authority surfaces only through explicit checkpoint-gated rehearsal, with rollback verified before any change is treated as canon.

## Open questions
1. Should apply receipts live inside the tracked repo, or under durable local state with periodic export?
2. What is the right TTL for governor approval before apply: 1h, 6h, or 24h?
3. Should sidecar witness be required for every wet-run, or only after Phase 3?
4. What is the exact reflection delta schema used by self-mode sidecar?
5. Does rollback refuse if a human edited the card after apply, or produce conflict artifacts?
6. Should this lane be exposed as `dream-lite apply` or folded under `optimize assist-apply` after proof?
7. Which files count as authority surfaces for Dream Director checkpoint gating?
8. Should Dream Director candidate patches be reviewed by Lyria only, CK only, or both before canonization?
9. Should staged authority changes land in a separate rehearsal branch / folder before touching live files?

## Non-regression constraints
- Do not confuse this with OpenClaw core dreaming.
- Do not turn self-mode sidecar into durable memory authority.
- Do not expand from `refresh_card` to new-card creation by flag only.
- Do not mutate without receipts and rollback.
- Do not provision background cron in v0.
- Do not encode a prompt that literally tells the system to ignore guardrails; express premise suspension as isolated observation only.
- Do not blindly apply Dream Director instruction cards to live authority surfaces.

## Topology statement
- Runtime/system topology: unchanged in this spec.
- Live cron topology: unchanged.
- Authority/document topology: changed by defining the next apply-capable product gate.
