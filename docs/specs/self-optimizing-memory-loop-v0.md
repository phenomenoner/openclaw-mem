# Spec — Self-Optimizing Memory Loop v0

## Status
- Stage: **DONE / governed assist-apply bridge shipped on stable main**
- Scope: review loop + governor judgment + bounded assist apply for low-risk lifecycle updates
- Posture: **recommendation-first, governor-gated mutation**

## Problem
Today `openclaw-mem` can capture, grade, recall, and expose receipts — but it does not yet close the loop on its own.

It can remember, but it does not robustly learn from:
- repeated misses
- repeated low-value recalls
- user corrections
- successful/unsuccessful retrieval outcomes
- evidence that some memory should be promoted, merged, demoted, or decayed

This leaves value on the table.

## Goal
Add a **safe self-optimization loop** so the memory layer can improve over time without becoming an opaque self-modifying mess.

Core idea:

> observe → propose → verify → optionally apply

## Design stance
- **Source of truth stays human-auditable**.
- Optimization proposals are **derived artifacts**, not instant truth.
- Start with **shadow mode / recommendation mode**.
- Only low-risk metadata changes can ever become auto-apply candidates, and only behind an explicit flag.

## Non-goals (v0)
- no autonomous prompt rewriting
- no autonomous config mutation of provider/model/routing
- no silent deletion of memory rows
- no unbounded self-reinforcement loop
- no fully automatic importance regrading of all memory without receipts

## Why this is attractive
A self-optimizing memory layer is compelling because it could:
- reduce repeated irrelevant recalls
- promote high-signal facts faster
- detect stale or low-value memories
- create provenance-backed improvement suggestions automatically
- turn memory quality from a static config into a measurable feedback system

## What is true vs what is risky
### What is true
- The system already emits enough ingredients to support a loop:
  - capture events
  - recall receipts
  - importance grading
  - graph / topology direction
  - user-visible correction moments

### Main risk
The sexy version becomes dangerous if the memory layer can mutate itself without control.
That would create:
- hidden drift
- self-justifying errors
- hard-to-debug regressions
- prompt-injection amplification risks

So v0 must be conservative.

## Proposed model

### Layer A — observation ledger
Store optimization-relevant signals, for example:
- recall hit used / not used
- repeated same-query misses
- user correction against recalled fact
- explicit user feedback: wrong / irrelevant / stale / useful
- repeated re-surfacing of same low-value memory
- strong evidence that a memory helped solve a task

Suggested outputs:
- observation records with timestamps
- memory refs / scope / query context
- safe aggregate counters

### Layer B — proposal engine
Generate bounded proposals such as:
- `promote_importance`
- `demote_importance`
- `mark_stale`
- `merge_candidates`
- `strengthen_edge`
- `suppress_low_signal_pattern`
- `widen_scope_candidate`
- `narrow_scope_candidate`

Each proposal must include:
- why
- evidence
- confidence
- rollback
- whether it is safe for auto-apply

### Layer C — verification
Before any proposal is accepted/applied:
- compare before/after quality
- ensure no recall collapse
- ensure no spike in false negatives
- keep receipts and reversibility

### Layer D — application policy
v0 should default to:
- **recommend only**

Later, optional controlled modes:
- `shadow`: generate proposals only
- `assist`: allow operator approval
- `auto_low_risk`: only bounded metadata tweaks with receipts

## Candidate low-risk auto-apply actions (future only)
These are the *only* things I’d even consider for auto-apply later:
- mark a memory as stale candidate
- add a bounded evidence counter
- add a proposal record for merge candidate
- adjust a non-destructive score/weight field within a small range

Not auto-apply:
- deleting memories
- overwriting user-authored summaries
- changing system prompts/config
- cross-scope promotion without evidence

## Repo shape (current v0.1)

```text
docs/specs/
  self-optimizing-memory-loop-v0.md

openclaw_mem/
  optimization.py

tests/
  test_optimize_review.py
```

## Suggested first shipped slice
### v0.1 — recommendation-only (**shipped**)
- CLI: `openclaw-mem optimize review`
- bounded input surface: `observations` table only (row limit configurable; default 1000)
- low-risk signals implemented:
  - staleness
  - duplication
  - bloat
  - weakly-connected candidates
  - repeated no-result `memory_recall` miss patterns
- structured report: `openclaw-mem.optimize.review.v0`
- no auto-apply
- zero writes to memory rows (observe + propose only)

### v0.2 — operator review lane (**shipped foundation**)
- keep `optimize review` contract stable and add adjacent review outputs rather than silent mutation paths
- shipped read-only commands:
  - `openclaw-mem optimize consolidation-review --json`
    - scans `episodic_events`
    - emits candidate-only summary compression groups, archive-review rows, and cross-session link proposals (receipt-first with bounded lexical backfill when lifecycle rows exist; lexical fallback on cold start)
    - includes source episode refs / provenance back to the underlying episodic rows
    - now protects archive candidates when referenced observations still show recent pack selection
    - explicitly forbids canonical rewrite (`policy.canonical_rewrite=forbidden`)
  - `openclaw-mem optimize review --json`
    - now scans recent `pack_lifecycle_shadow_log` rows alongside `observations`
    - emits `signals.recent_use` and protects old rows from naive stale recommendations when they still show recent pack selection
  - `openclaw-mem optimize policy-loop --json`
    - combines repeated recall-miss pressure, writeback linkage readiness, and lifecycle-shadow evidence
    - writeback linkage readiness is scoped to `memory_store` rows from `memory_backend=openclaw-mem-engine` (legacy/non-target backends are excluded from the denominator)
    - emits sunrise Stage B/C gate status (`ready|hold`) with explicit threshold/reason receipts
    - remains strict zero-write (`policy.writes_performed=0`, `memory_mutation=none`)
- bounded recommendation budgets stay in place (`--top`, scoped miss groups)

### v0.3 — bounded low-risk apply (**shipped, governor-gated**)
- shipped read/write bridge:
  - `openclaw-mem optimize evolution-review --json`
  - `openclaw-mem optimize governor-review --approve-stale --json`
  - `openclaw-mem optimize assist-apply [--dry-run] --json`
- current apply whitelist stays intentionally narrow:
  - `/lifecycle/stale_candidate`
  - `/lifecycle/stale_reason_code`
  - bounded `/optimization/assist` receipt metadata
- before/after + rollback receipts are mandatory on every run
- cap violations still abort before write
- auto mode remains explicitly forbidden; unattended use must still route through an approved governor packet

## Acceptance checks
### 1-day check
- spec clearly separates observe/propose/verify/apply
- no ambiguity that source of truth remains human-auditable
- at least 3 concrete proposal types are defined
- rollback is obvious

### v0 functional check
- proposals can be generated without mutating stored memories
- proposal records are inspectable and bounded
- disabling the loop leaves current memory behavior unchanged

## Metrics to watch
- relevant recall rate
- false-positive recall complaints
- repeated-miss rate
- operator-approved proposal precision
- stale-memory suppression wins

## Risks
- self-reinforcing bad signals
- overfitting to one user/session style
- hidden mutations that operators can’t explain
- proposal noise flood

## Mitigations
- recommendation-first
- explicit receipts and rollback
- bounded proposal budgets
- aggregate evidence thresholds
- scope-aware proposals

## Recommendation
Yes — this logic is a strong fit for `openclaw-mem`, especially the **actual runtime** side.
But the correct first move is **self-optimizing memory as a recommendation engine**, not a self-editing memory brain.

That still gives the sexy part:
- the memory layer improves from real use
- but remains testable, rollbackable, and traceable
