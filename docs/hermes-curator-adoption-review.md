# Hermes Curator adoption review for openclaw-mem

Status: **reviewed design input, not authority**  
External source posture: Hermes documentation/release notes are treated as external untrusted product research. The design below is filtered through local `openclaw-mem` authority: Store / Pack / Observe, sidecar-first adoption, receipts, rollback, and explicit human/governor review before writes.

## What Hermes Curator contributes

Hermes Curator introduces a background maintenance pattern for agent-created skills:

- usage-aware lifecycle tracking
- stale/archive states
- auxiliary review pass
- pinning/fencing
- backups and rollback
- per-run machine and human reports

The valuable transferable idea is not auto-archiving itself. The transferable idea is **memory metabolism**: learned artifacts need lifecycle, receipts, and reversible consolidation so the agent does not drown in its own self-improvement output.

## Local interpretation

`openclaw-mem` already has the lower-level primitives that can absorb this safely:

- `ContextPack` with citations and include/exclude rationale
- synthesis-card preference over raw covered refs
- optimize-assist lifecycle fields such as stale and soft-archive candidates
- governor review, dry-run/apply receipts, challenger review, verifier bundles
- sidecar-first advanced labs for self-model, Dream Lite, GBrain, and continuity

Therefore the local adoption path is two-layered:

```text
openclaw-mem / context pack mainline
  = lifecycle data model, trace receipts, pack weighting, downshift, synthesis preference

self-curator sidecar
  = review-only scanner, lifecycle proposals, human-readable report

apply
  = existing packet-backed / governor-gated lane when explicitly approved
```

## Decision

Adopt Hermes Curator as an **apply-capable curator pattern with mandatory checkpoints**, not as a permanently review-only system.

The first shipped implementation slice is still a manual `self-curator skill-review` command that scans skills and emits:

- `review.json`
- `REPORT.md`

That v0 slice is a scout/proposal surface. It does not represent the final authority model. The intended next step is an apply-capable lane with:

```text
plan → rollback checkpoint → apply whitelisted mutation → verify/readback → receipt → rollback command
```

No cron is enabled yet. Canon/authority files remain out of first apply scope, but skill/config hygiene may become directly mutable once the checkpointed apply contract is implemented and verified.

## Why not direct auto-archive

The local system has stronger authority surfaces than a generic skill library:

- persona canon
- operator canon
- memory canon
- decision ledger
- Dream Lite staging
- context packing policy
- runtime/gateway topology

A background curator that can directly mutate these without checkpoints would be too much authority in the wrong layer. Direct mutation is acceptable only through explicit plan/checkpoint/apply/verify/rollback receipts, with whitelisted surfaces and fail-closed preconditions.

## Expansion path

1. **Skill lifecycle review** — safest first surface; review-only packet and report.
2. **Checkpointed skill apply** — first direct mutation slice: deterministic skill metadata/frontmatter patches with before snapshots, diffs, verify, and rollback.
3. **Memory/context-pack lifecycle** — integrate half-life/downshift/consolidation signals into pack receipts and optimize-assist packets.
4. **Dream/self lifecycle** — raw → candidate → adopted/archive, checkpoint-gated before durable promotion.
5. **Authority stale-rule review** — review-first; any apply requires a stricter checkpoint and explicit authority-surface gate.

## Closure criteria for v0

- Deterministic scanner exists.
- Packet follows `openclaw.curator.lifecycle-review.v0`.
- Report mirrors packet counts.
- Smoke artifacts prove `writes_performed=0` and skill source files remain unchanged.
- No topology/config change.
