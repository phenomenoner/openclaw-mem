# Spec — Use-based decay v0

## Status
- Stage: **install/enable slice reached on stable main** (2026-03-26)
- Scope: recommendation-only recent-use protection for review commands
- Delivery posture: no runtime mutation, no auto-archive, no canonical rewrite

## Problem
Age-only decay is too blunt.

A row can be old and still useful. In `openclaw-mem`, the cleanest observable proof of usefulness already exists: recent selection into trust-aware packs, recorded in `pack_lifecycle_shadow_log`.

That means the first installable slice of use-based decay should not try to rewrite memory truth. It should first improve **review judgment**.

## Decision
Use recent `pack_lifecycle_shadow_log` selection evidence as the first shipped proxy for utility.

Specifically:
- parse recent lifecycle receipts
- extract `selection.pack_selected_refs`
- map `obs:<id>` refs back to observation rows
- use that evidence to protect rows from naive age-only stale/archive recommendations

## Shipped behavior
### 1) `optimize review`
- new input surface: `--lifecycle-limit <n>`
- scans recent lifecycle-shadow receipts in addition to `observations`
- emits `signals.recent_use`
- emits `signals.staleness.protected_recent_use`
- old rows that still show recent pack selection are not counted as ordinary stale candidates

### 2) `optimize consolidation-review`
- new input surface: `--lifecycle-limit <n>`
- when an episodic row is nearing GC/archive review, its `refs` are inspected for `obs:<id>` links
- if those referenced observation rows still show recent pack use, the episodic row is protected from archive recommendation
- report surfaces:
  - `signals.recent_use`
  - `candidates.archive.protected_by_recent_use`

## Hard boundaries
- no automatic archive/delete/writeback
- no runtime scoring mutation
- no canonical memory rewrite
- no graph truth mutation

## Why this is the right first cut
It gives the system a real notion of utility without granting hidden power.

This is the correct sequence:
1. observe use
2. protect against bad decay decisions
3. later, if needed, add reviewed apply paths

Not this sequence:
1. infer importance
2. silently rewrite memory
3. hope the operator agrees later

## Acceptance checks
- review commands remain strict zero-write
- recent-use protection is visible in JSON receipts
- disabling/ignoring lifecycle evidence falls back to prior recommendation-only behavior
- local smoke can prove that an old selected observation is protected while an equally old unused observation still surfaces as stale/archive-worthy

## Postpone
- outcome-quality weighting beyond simple selection evidence
- probabilistic utility scoring for runtime recall
- auto-archive or auto-promote flows
- cross-lane utility fusion from engine receipts / task success metrics

## Product framing
Use-based decay in `openclaw-mem` begins as a **protection layer against dumb forgetting**, not as a hidden optimizer that rewrites memory behind the operator’s back.
