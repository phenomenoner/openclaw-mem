# Working Set / Backbone Contract v0

Status: **draft contract / public-facing product doc**  
Date: 2026-05-25  
Companion: `docs/specs/memory-strata-boundary-map-v0.md`, `docs/receipts/memory-strata-ws8-stop-loss-wal-2026-05-25.md`  
Topology impact: **none** — documentation contract only.

## 1. Purpose

The Working Set / Backbone lane is an activation aid, not a durable truth store.

It exists to keep current constraints, active goals, and high-value state available without forcing every `must_remember` durable record into every prompt.

## 2. Ownership

| Concern | Owner |
|---|---|
| Durable facts/preferences/decisions | durable memory / governed promotion |
| Session/event evidence | episodic ledger |
| Long-form specs/receipts | docs cold lane / repo authors |
| Relationship expansion | graph/topology derived cache |
| Working Set / Backbone | derived activation artifact |
| Final prompt bundle | Pack / Proactive Pack |

Working Set content must cite or derive from governed sources. It must not originate uncited truth.

## 3. Allowed sources

A Working Set item may be generated from:

- durable memory records,
- docs cold-lane specs/receipts,
- active goal/controller receipts,
- reviewed episodic summaries,
- graph/topology paths with provenance.

A Working Set item must carry enough source information to be auditable. If the source is private/ops-only, the item must stay scoped accordingly.

## 4. Activation semantics

Working Set injection may happen before or alongside hot recall, but it must expose trace fields:

- `enabled`
- `generated`
- `id`
- `chars`
- `sections`
- `consumedCount`
- `suppressedRecallCount`
- `persisted`

If Working Set content suppresses duplicated recall hits, the receipt should make that visible.

## 5. Persistence and TTL

Default stance:

- `persist=false` is safest for local/runtime activation.
- Persisted Working Set artifacts are derived caches, not truth.
- Persisted artifacts need TTL or refresh triggers.

Minimum stale-detection triggers:

- source record deleted/redacted/forgotten,
- source receipt superseded,
- active goal completed/paused/cleared,
- scope or privacy policy changes,
- source citation missing or no longer resolvable.

## 6. Pack lifecycle writeback

`openclaw-mem pack --pack-lifecycle-write on` is a real durable write path because it refreshes `observations.detail_json.lifecycle` for selected records.

Contract:

1. Pack lifecycle writeback is **off by default**.
2. Pack lifecycle writeback must not be used as a hidden Working Set updater.
3. Pack lifecycle writeback is allowed only under a governed lifecycle/writeback contract with:
   - explicit operator intent,
   - selected-record receipt,
   - pre-snapshot or fixture DB,
   - rollback plan,
   - bounded row count,
   - no schema/config/topology mutation.
4. Default/runtime use requires WS9 promotion/writeback governance and second-brain review.

## 7. Fixture/counterfactual rule

Any test likely to touch durable state must run on one of:

- isolated fixture DB,
- copied production DB fixture,
- explicitly approved production mutation window with pre-snapshot and rollback plan.

This rule was added after WS8 proved that Pack lifecycle writeback mutates production observations when enabled.

## 8. Product API / receipt requirements

A product-ready Working Set implementation should expose:

- source refs per item,
- section/type per item,
- generated-at timestamp,
- stale/valid status,
- dedupe/suppression counts,
- persistence status,
- scope/privacy label,
- rollback or regeneration command when persisted.

## 9. Non-goals

Working Set must not:

- become a second durable memory store,
- auto-promote episodic evidence,
- silently mutate Pack or durable memory,
- hide source citations,
- bypass scope/privacy policy.

## 10. Open implementation questions

- Should persisted Working Set artifacts live in SQLite, file receipts, or both?
- Should Pack consume Working Set as a separate lane or as protected tail context?
- What TTL is appropriate for active-goal backbone items?
- Should stale Working Set warnings fail closed or degrade gracefully?

## 11. Acceptance criteria for WS5

- Current live config inspected.
- Contract written.
- WS8 lifecycle-write incident incorporated as governing example.
- No runtime/config/data changes made.
- Second-brain review accepts the boundary before WS2/WS5 are treated as M3 complete.
