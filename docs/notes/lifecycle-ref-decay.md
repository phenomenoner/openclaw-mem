# Notes — Reference-based decay (ref/last_used_at) for openclaw-mem

This note captures an architectural idea: model retention as a **use-based lifecycle**, not time-based deletion.

## Why this matters (signal > storage)
- Time-since-write is a poor proxy for importance.
- "Used recently / used often" is a strong proxy for importance and relevance.
- Our governance philosophy requires this to be **auditable** (receipts), **non-destructive**, and **reversible**.

## Proposed mechanism (MVP)

### Data fields (upgrade-safe first)
Store in `detail_json.lifecycle` initially (no DB migration required):
- `priority`: `P0|P1|P2`
- `last_used_at`: ISO timestamp
- `used_count`: integer (optional)
- `archived_at`: ISO timestamp (optional)

### Reference ("used") event definition
Default definition (cheap + observable):
- A record is considered **used** if it is **selected into the final `pack` bundle** and cited as `recordRef`.

Non-example:
- Bulk preload does **not** refresh `last_used_at`.

Optional later split:
- `last_retrieved_at`: candidate hit (weak signal)
- `last_included_at`: final bundle inclusion (strong signal)

### Lifecycle policy (example defaults)
- P0: never auto-archive
- P1: archive if `last_used_at` older than 90d
- P2: archive if `last_used_at` older than 30d

Important: thresholds are tunable; start conservative.

### Archive-first (soft delete)
- MVP: archive only (reversible).
- Retrieval: default excludes archived; optionally include in a fallback stage.

## Observability / receipts
- `pack --trace`: record which `recordRef`s were refreshed.
- Daily lifecycle job: emit an aggregate-only receipt with counts by:
  - `priority`, `trust`, `importance`, and action (`archived`, `skipped_p0`, `kept_recent`).

## Interaction with trust tiers
- Ref updates should never implicitly change trust.
- Consider stricter archive thresholds for `untrusted` (optional) so hostile inputs don’t stay forever just because they’re repeatedly retrieved.

## Sources / thought-links

Untrusted inspiration (idea source; treat as a field note, not as a spec):
- X thread: "给 Agent 装一个遗忘曲线——基于引用频率的记忆衰减系统" — <https://x.com/ohxiyu/status/2022924956594806821>

Trusted background:
- Cepeda et al. (2006) spaced repetition / distributed practice — <https://doi.org/10.1037/0033-2909.132.3.354>
- ARC cache replacement (recency+frequency) — <https://www.usenix.org/legacy/publications/library/proceedings/fast03/tech/full_papers/megiddo/megiddo.pdf>
