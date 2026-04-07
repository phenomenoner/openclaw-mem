# Spec — Graphic Memory compiled synthesis layer v0

## Status
- Stage: **partial implementation shipped**
- Shipped v0.1 slice: `graph synth compile`, `graph synth stale`, deterministic `graph lint`, optional Markdown materialization, graph-preflight preference for fresh synthesis cards, graph-pack preference for fresh synthesis cards, deterministic review/contradiction-keyword signals in stale/lint
- Scope: `openclaw-mem` Graphic Memory surfaces only
- Recommendation: **add as a derived layer inside `openclaw-mem`**
- Delivery posture: **provenance-first, fail-open, no graph DB, no UI dependency**

## Why this exists
`openclaw-mem` already has meaningful graph-adjacent value:
- topology L3 (`docs/specs/topology-knowledge-v0.md`)
- graph query plane over structured topology (`docs/specs/graphic-memory-query-plane-v0.md`)
- Graphic Memory retrieval helpers (`graph index` / `graph pack` / `graph preflight`)
- capture surfaces (`graph capture-git` / `graph capture-md`)

Those surfaces help the system **find** relevant nodes, paths, and adjacent observations.
What they do **not** yet do is maintain a persistent, bounded, derived synthesis artifact that compounds over time.

This spec defines that missing layer.

## Problem statement
Today, Graphic Memory is still strongest at:
- candidate retrieval
- bounded packing
- structural navigation
- provenance / fail-open query behavior

It is weak at:
- preserving cross-source synthesis as a durable artifact
- marking when a prior synthesis is now stale
- health-checking graph quality beyond one-off query results
- reusing a prior high-value analysis without reconstructing it from scratch

The desired shift is:

> from **query helper** → to **compiled synthesis layer**

## Existing assets we should NOT duplicate

### 1) Topology L3 remains separate
- Topology knowledge answers: *what exists, how it connects, what breaks if it changes?*
- Source: `docs/specs/topology-knowledge-v0.md`
- This spec does **not** replace topology truth or runtime drift checks.

### 2) Query plane remains the navigation layer
- Upstream/downstream/writers/filter/lineage/provenance/refresh receipts already belong to the query plane.
- Source: `docs/specs/graphic-memory-query-plane-v0.md`
- This spec does **not** create a second query-plane abstraction.

### 3) `graph index` / `graph pack` / `graph preflight` remain retrieval helpers
- Those commands are for bounded recall and pack construction.
- They should become inputs to compiled synthesis, not be reimplemented under a new name.

### 4) Auto-capture remains capture, not synthesis
- `graph capture-git` and `graph capture-md` expand the observation pool.
- They should not auto-promote every captured item into a synthetic graph conclusion.

### 5) GraphRAG-lite stays broader than this slice
- `docs/specs/graphic-memory-graphrag-lite-prd.md` covers associative retrieval, path justification, and future neighborhood expansion.
- This spec only adds the missing **compiled synthesis artifact + staleness/lint loop**.

## Decision
Add an optional **compiled synthesis layer** to Graphic Memory.

The compiled synthesis layer is:
- derived from existing captured / selected refs
- stored as a portable artifact (Markdown and/or JSON receipt)
- provenance-carrying
- stale-checkable
- safe to ignore when disabled

The compiled synthesis layer is **not**:
- a new source of truth for topology
- a graph database
- an always-on autonomous wiki writer
- a mandatory LLM path

## Core primitives

### 1) Synthesis card
A bounded derived artifact representing a durable conclusion over a selected set of refs.

Suggested minimum fields:
- `card_id`
- `title`
- `scope`
- `kind = synthesis_card`
- `source_refs[]`
- `supporting_refs[]`
- `counter_refs[]` (optional)
- `summary`
- `why_it_matters`
- `compiled_at`
- `source_digest`
- `trust_tier`
- `status = fresh|stale|needs_review`

Design intent:
- small enough to pack
- explicit enough to audit
- separate from L1 durable memory by default

### 2) Synthesis edges
Minimal edge semantics for this layer:
- `derived_from`
- `supports`
- `contradicts` (optional in v0, but reserve the lane)
- `superseded_by` (for card lifecycle)

Do **not** explode the type system up front.

### 3) Source digest
Each card carries a deterministic digest over the selected refs / receipt ids / provenance group.
This enables cheap stale detection when the supporting set changes.

## Minimal command surface

### `graph synth compile`
Build a bounded synthesis card from selected refs.

Input options can reuse existing graph helpers:
- explicit `--record-ref ...`
- `--from-preflight <json>`
- `--from-query <query> --scope <scope>` (internally runs the existing preflight/index path first)

Output:
- synthesis card JSON receipt
- optional Markdown materialization

Default posture:
- safe mode
- bounded output
- provenance-first
- no raw long-body excerpts by default

### `graph synth stale`
Check whether a synthesis card is stale.

Signals:
- source digest mismatch
- newer supporting refs added within scope
- newer contradictory refs exist

Output:
- `fresh | stale | review`
- reason list
- minimal provenance summary

### `graph lint`
Health-check the graph/cardiography layer.

Initial v0 checks:
- orphan captured nodes with repeated retrieval but no synthesis card
- synthesis cards with missing or empty provenance
- stale synthesis cards
- suspicious hub growth / low-signal capture bursts
- contradictory candidate refs in the same scope without a synthesis card update

## A-fast / A-deep split

### A-fast — ship reusable value without new substrate
1. Define synthesis card schema + receipts
2. Add `graph synth compile` for explicit selected refs
3. Add `graph synth stale`
4. Add `graph lint` with only deterministic checks

Acceptance:
- a user can compile a bounded synthesis card from current refs
- stale detection works without LLMs
- failures never break `graph preflight` / `pack`

### A-deep — strengthen lifecycle and maintenance
1. Candidate-card suggestion from repeated preflight/query patterns
2. Digest-aware incremental refresh suggestions
3. Contradiction/support bucketing
4. Optional pack integration: prefer fresh synthesis cards before replaying many raw refs

Acceptance:
- the system can suggest when a card should be updated
- pack can consume cards as a compact abstraction when available
- raw ref fallback always remains available

## Recommended rollout

### v0.1
- Spec + receipt contract
- `graph synth compile`
- `graph synth stale`
- `graph lint` (deterministic only)

### v0.2
- optional Markdown materialization/export
- candidate-card suggestions from repeated query/preflight patterns
- pack preference for fresh cards before raw expansion

### v1
- contradiction-aware refresh suggestions
- optional assistant-authored card drafts behind an explicit flag
- richer health metrics for card coverage / staleness / orphan pressure

## Boundaries / non-goals
- no graph DB requirement
- no UI / Obsidian dependency
- no auto-writing dozens of pages from every capture event
- no L1 durable-memory promotion by default
- no collapse of L1 / L2 / L3 / Graphic Memory into one storage class

## Why this is incrementally implementable
Because it reuses what already exists:
- capture expands the candidate pool
- index/preflight selects bounded refs
- pack already knows how to build bounded bundles
- query/provenance already normalize explanation surfaces

This spec only adds the missing durable middle layer:
**selected refs → compiled synthesis card → stale/lint loop**

## Rollback
- disable `graph synth*` and `graph lint`
- keep capture/query/preflight/pack unchanged
- keep topology truth unchanged
- keep baseline pack / memory flows fail-open

## Acceptance check for this spec
A reader should be able to answer:
1. what problem this solves that query/preflight do not
2. why it does not replace topology L3
3. what the first three commands are
4. why no graph DB or UI work is needed to ship v0.1
