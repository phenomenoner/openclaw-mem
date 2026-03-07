# Auto-recall v1: retention / activation split + quota selection

## Status
- Version: v1 draft
- State: approved direction for implementation
- Scope: `openclaw-mem-engine` autoRecall selection policy + receipts
- Implementation note (2026-03-07): phase-1 hotfix landed behind `autoRecall.selectionMode=tier_quota_v1`; default remains `tier_first_v1` for rollback-first safety.

## Problem

Today `autoRecall` effectively treats importance as both:
1. **retention priority** — what should stay in memory long-term
2. **activation priority** — what should be injected into the next prompt

That coupling breaks down once the `must_remember` pool grows.

Current behavior is effectively:
- search `must_remember` first
- fill recall budget from `must_remember`
- only consult `nice_to_have` if must results are insufficient

Failure mode:
- a large stable `must_remember` set turns auto-recall into a near-static prefix
- the same durable items win repeatedly
- conversation-relevant but lower-importance memories are suppressed
- the practical value of auto-recall collapses toward a hand-written `MEMORY.md`

## Decision

### 1) Split **retention** from **activation**

- `importance` answers: **should we keep this memory?**
- `autoRecall` answers: **should we inject this memory for this turn?**

`must_remember` therefore means:
- harder to archive / easier to preserve
- stronger prior during selection
- **not** an unconditional right to occupy hot recall slots every turn

### 2) Two recall lanes

#### A. Backbone lane (stable, pinned)
Use the existing Working Set as the backbone lane.

Purpose:
- carry long-lived constraints, preferences, recent durable decisions, and current goal state
- avoid forcing these items to re-win normal recall on every turn

Rules:
- injected first as a pinned slot when `workingSet.enabled=true`
- synthesized deterministically from existing captured signal
- may persist as `working_set:<scope>`
- normal hot recall should avoid duplicating backbone content when possible

#### B. Hot recall lane (dynamic, turn-specific)
This lane answers the per-turn relevance question.

Purpose:
- surface memories that are useful **now**
- ensure `nice_to_have` / recent / exact-match memories still have room
- prevent durable must-items from monopolizing injection budget

## Selection policy: `tier_quota_v1`

Replace "must fills first" with quota-based mixing.

### Default shape
For a typical `maxItems=6` auto-recall budget:
- `1` pinned slot: Working Set / backbone lane
- `must`: up to `2`
- `nice`: at least `2` when available
- `unknown/recent wildcard`: up to `1`
- remaining slot(s): best available across tiers after quota satisfaction

### Semantics
- `mustMax` is a **cap**, not a target
- `niceMin` is a **floor** when relevant candidates exist
- wildcard slots preserve room for recent / uncategorized / edge-case but useful memories
- if a tier has insufficient candidates, unused budget spills to the next best candidates

### In-tier ranking
Each tier still uses deterministic hybrid ranking, e.g.:
- scope match
- fused lexical + vector relevance
- recency boost
- optional exact-match boost

## Repeat suppression

To avoid the same durable memories appearing every turn, add a repeat penalty.

### Rule
If a memory was injected recently, lower its hot-lane selection score unless one of these holds:
- it is an exact / very strong lexical hit for the current turn
- it is already intentionally pinned by Working Set
- it is tagged as a hard rule / always-pin item

### Suggested knobs
```yaml
autoRecall:
  repeatWindowTurns: 6
  repeatPenalty: 0.35
```

This is a ranking penalty, not a deletion rule.

## Scoring model (conceptual)

The exact formula can remain deterministic, but the model should be:

`final_score = relevance × scope_match × recency × importance_prior × novelty × repeat_penalty`

Where:
- `importance_prior` is a prior, not an absolute gate
- `novelty` favors items that have not been injected repeatedly
- `repeat_penalty` suppresses stale winners

## Receipt / explainability changes

Extend recall receipts so operators can see why fixed must-items were or were not injected.

Additions:
- `selectionMode`
- `quota` summary (`mustMax`, `niceMin`, `unknownMax`, `wildcardUsed`)
- `suppressedByRepeat` ids/count
- `pinnedByWorkingSet` ids/count
- `excludedAsBackboneDuplicate` ids/count

Existing fields (`whySummary`, `whyTheseIds`, `workingSet`) remain the base receipt surface.

## Config sketch

```yaml
autoRecall:
  selectionMode: tier_quota_v1
  maxItems: 6
  quotas:
    mustMax: 2
    niceMin: 2
    unknownMax: 1
  repeatWindowTurns: 6
  repeatPenalty: 0.35
  dedupeBackbone: true

workingSet:
  enabled: true
  persist: true
```

## Acceptance criteria

1. **Must saturation no longer suppresses nice recall**
   - even with a large must pool, relevant `nice_to_have` memories still appear in injected context

2. **Repeated must winners decay naturally**
   - without exact-hit evidence, the same must items do not dominate consecutive turns

3. **Backbone duplication is reduced**
   - if Working Set already carries a durable constraint, normal hot recall does not waste another slot on the same idea

4. **Hard rules still survive**
   - explicit always-pin / hard-constraint items remain protected

5. **Receipts explain the result in one screen**
   - operator can tell whether an item was pinned, quota-selected, or suppressed

## Rollout

### Phase 1 — selection policy only
- add `selectionMode=tier_quota_v1`
- keep existing storage / grading unchanged
- ship behind config flag

### Phase 2 — backbone dedupe
- integrate Working Set as explicit backbone lane
- suppress duplicate hot-lane injection of already-pinned content

### Phase 3 — receipt expansion
- add quota / repeat / backbone explainability fields
- validate on golden recall cases

## Rollback

One-line behavioral rollback:
- switch `autoRecall.selectionMode` back to current tier-first behavior

No storage migration is required.

## Non-goals

- changing importance grading thresholds in this change
- replacing Working Set synthesis logic
- adding LLM-based selection logic
- changing memory write-path semantics

## Related docs
- `docs/context-bloat-mitigation-rollout.md`
- `docs/mem-engine.md`
- `docs/openclaw-user-improvement-roadmap.md`
- `docs/specs/graphic-memory-auto-capture-auto-recall.md`
