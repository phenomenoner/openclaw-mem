# TradeMemory inspirations — guarded adoption alignment (2026-03-17)

## Why this note exists

We reviewed the idea shape behind a trading-oriented memory product (`tradememory-protocol`) and asked a narrower question:

> Is there anything worth adopting for `openclaw-mem`, and if so, what is **actually new** versus what we already have or already planned?

This note locks the answer against current `openclaw-mem` design truth.

## Short answer

`openclaw-mem` already covers a surprising amount of the valuable substrate.
The best adoption posture is **guarded cherry-pick**, not worldview replacement.

### Already present or materially present
- hybrid retrieval direction (FTS/BM25 + vector + RRF)
- traceable candidate scoring / inclusion receipts
- provenance + trust-aware packing
- lifecycle / usage evidence (`last_used`-style direction via lifecycle shadow)
- episodic capture lane
- docs cold-lane / operator-doc recall
- recommendation-first self-optimizing loop

### Worth adopting as bounded deltas
1. **Counterexample / dissent quota** in final pack selection
2. **Explicit prospective / plan-shaped durable record kind**
3. Better **recall-balance semantics** for contradictory evidence, not just “top score wins”

### Not worth adopting as core doctrine
- trading-native cognitive framing
- Kelly/risk-sizing-from-memory ideas
- autonomous strategy evolution as a memory-core responsibility
- any affective/behavioral modulation layer in the memory hot path

## What we already have (important alignment)

This section exists so we do not re-label existing work as fresh invention.

### 1) Hybrid retrieval + auditable trace: already here

`openclaw-mem` already has the right retrieval spine:
- lexical anchors
- optional vector recall
- deterministic fusion (`RRF`)
- trace receipts with per-candidate score surfaces

That means the idea “memory retrieval should be multi-signal and explainable” is **not** a new import for us.
It is already core design truth.

Relevant docs:
- `docs/roadmap.md`
- `docs/specs/docs-memory-hybrid-search-v0.md`
- `README.md`

### 2) Trust/provenance policy surfaces: already beyond the imported idea

In several ways, `openclaw-mem` is already more governance-heavy than the trading reference:
- trust tiers
- provenance policy
- composed `policy_surface`
- lifecycle shadow logging
- fail-open receipts

So the right framing is not “we should learn that memory needs governance.”
The right framing is:
- we already believe that,
- and we already implemented meaningful pieces of it.

### 3) Episodic memory: already present

The trading product distinguishes experience-like memory very explicitly.
So do we, at least in foundation form:
- episodic event capture
- session/event timeline surfaces
- append-only event posture

What is **not** yet equally explicit is a matched durable split for:
- stable facts
- future plans / prospective triggers

### 4) Lifecycle-by-use: already directionally aligned

The trading reference emphasizes memory shaped by later outcomes and later use.
`openclaw-mem` already has the correct instinct here:
- reference-based decay direction
- `last_used_at` / usage evidence ideas
- lifecycle shadow receipts before mutation

So again, the import is **not** the lifecycle idea itself.
The import is a more opinionated selection/balance policy on top of it.

## The best actual adoption candidates

## 1) Counterexample / dissent quota

This is the strongest small adoption.

### Problem
Pure top-score retrieval can become a polite confirmation machine:
- it returns the most similar rows,
- often the most frequently reinforced rows,
- and can hide the nearest contradiction.

### Proposed `openclaw-mem` adaptation
When a pack run detects a meaningful contradiction set, reserve a tiny explicit slot for:
- one counterexample,
- one dissenting policy row,
- or one “why this may be wrong” record.

Possible names:
- `dissent_quota`
- `counterexample_quota`
- `contradiction_reserve`

Good first posture:
- **off by default or trace-only first**
- no magical contradiction inference required in v0
- start from cheap signals:
  - opposing dispositions / labels
  - conflict markers in structured metadata
  - explicit “hold / reject / risk / caveat” records

Why this fits `openclaw-mem`:
- improves answer hygiene without requiring a new substrate
- fits our evidence-first doctrine
- complements trust/provenance rather than replacing it

## 2) Explicit prospective / plan memory kind

This is the second strongest adoption.

### Current state
We already have:
- episodic/event-ish capture
- stable memory categories like fact/preference/decision
- learning/proposal surfaces in docs and ops flow

What is still fuzzy is a first-class durable shape for:
- “when X happens, do Y”
- “review this under trigger Z”
- “this plan expires after condition/time T”

### Proposed adaptation
Add a future durable kind such as:
- `plan`
- `prospective`
- or `operator_intent`

With explicit fields like:
- trigger
- expiry / stale-after
- status (`pending|active|consumed|expired|cancelled`)
- source refs / justification
- scope

Why this fits:
- it tightens the line between what happened vs what should happen next
- it prevents plans from masquerading as facts
- it gives pack a cleaner way to include forward-looking state

## 3) Recall-balance semantics

This is the subtle one.

The trading reference implicitly treats memory as a balance problem:
- positive vs negative outcomes
- reinforced habit vs warning example
- successful pattern vs recent failure

For `openclaw-mem`, the generalized version is:
- not “winner vs loser trades”
- but **supporting evidence vs conflicting evidence**

That means future pack policy may want to reason over:
- agreement
- conflict
- recency
- trust
- importance
- diversity

We already expose parts of this through trace and policy surfaces.
The adoption opportunity is to make the **selection policy** more explicit, not just the receipts.

## What we should not import

### 1) Trading-native cognition framing

Useful for their product story.
Not useful as `openclaw-mem` core doctrine.

We are building:
- a local-first governed memory layer,
- not a trader-psychology operating system.

### 2) Risk sizing / Kelly from memory

This is product-specific and unsafe as a general memory-core direction.
It belongs, if anywhere, in domain applications above the memory layer.

### 3) Autonomous strategy evolution

Interesting product-adjacent idea, but it belongs in:
- research/incubation systems,
- not in the memory core.

For us this is the same boundary rule used elsewhere:
- memory may support proposals,
- memory should not silently become autonomous policy authority.

## Practical conclusion

If we compress this into one sentence:

> `openclaw-mem` already has most of the right substrate; the best cherry-picks are **counterexample-aware pack selection** and **first-class prospective/plan memory**, not a new grand theory of memory.

## Suggested next bounded slices

### Slice A — small and high-value
- add a design note / backlog item for `counterexample_quota` in pack selection
- trace first, then optional bounded activation

### Slice B — schema hardening
- define a prospective/plan record kind contract before implementation
- keep it docs/spec-first; do not silently overload `decision` or `task`

### Slice C — later only if needed
- richer contradiction-set ranking / balance heuristics
- only after we have real pack pain showing current selection is too one-sided

## Topology statement

- **Design truth clarified**: yes
- **Runtime topology changed**: no
- **Authority boundary changed**: no
- **Ops posture changed**: no

This is a guarded-adoption alignment note, not a product-direction rewrite.

## Related docs

- `docs/architecture.md`
- `docs/roadmap.md`
- `docs/specs/docs-memory-hybrid-search-v0.md`
- `docs/specs/context-budget-sidecar-v0.md`
- `docs/specs/self-optimizing-memory-loop-v0.md`
- `docs/reality-check.md`
