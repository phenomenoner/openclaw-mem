# Temporal fact materialized view dev phases v0

Status: active planning backlog.

This map turns `temporal-fact-materialized-view-v0.md` into a staged engineering line. It is intentionally phase-gated: no live memory backend, Gateway, or cron topology changes are part of this plan.

## North star

Make "what is currently true about X, how did it change, and what receipts support it?" a default operator experience in `openclaw-mem`.

The implementation must preserve the ownership contract:

```text
Store sources -> temporal fact materialized view -> Pack output -> Observe receipts
```

The fact view is derived and rebuildable. It is not a new memory source of truth.

## Phase 0 — Contract freeze

Goal: make the first implementation non-creative.

Deliverables:

- final schema for `openclaw-mem.graph.fact.v0`
- predicate registry schema
- source-ref resolver contract
- interval semantics for `valid_from` / `valid_to`
- stable-id algorithm
- fixture set covering happy path, stale source, dangling source, conflict, supersede, invalidate, rebuild

Verifier:

- schema fixtures validate deterministically
- conflict fixture expectations are explicit
- source resolver returns typed success/failure reasons

Exit gate:

- no CLI command is added until Phase 0 fixtures exist.

## Phase 1 — Deterministic core module

Goal: implement the view kernel without operator UX.

Deliverables:

- `openclaw_mem/graph/facts.py` or equivalent core module
- SQLite/file-backed derived-view storage
- explicit source resolver hooks
- deterministic lint engine
- rebuild-from-fixtures function
- unit tests for interval and predicate rules

Verifier:

- `pytest` targeted fact-core suite
- rebuild survival: drop derived cache, rebuild same stable ids/current truth
- no live OpenClaw memory backend read/write

Exit gate:

- lint can distinguish valid, stale, dangling, and contradictory facts from fixtures.

## Phase 2 — Operator CLI v0

Goal: expose explicit assertion and read surfaces.

Deliverables:

- `openclaw-mem graph fact assert`
- `openclaw-mem graph fact current`
- `openclaw-mem graph fact timeline`
- `openclaw-mem graph fact lint`
- JSON receipts for all mutating commands
- text summaries suitable for operator debug

Verifier:

- CLI smoke for assert/current/timeline/lint
- bad source assertion rejected with bounded error JSON
- overlapping contradiction fails lint until superseded or invalidated

Exit gate:

- operators can manually create and inspect a single-subject timeline with receipts.

## Phase 3 — Pack integration

Goal: make temporal facts useful inside the existing Pack contract.

Deliverables:

- `openclaw-mem graph fact pack`
- ContextPack-compatible fact items
- pack trace fields for source resolution, freshness, staleness, and budget decisions
- source snippet adapter for docs/episodic/store records
- stale facts excluded from current-truth pack unless explicitly requested

Verifier:

- byte-stable pack output for fixed fixtures
- every included fact has a resolvable source and assertion receipt
- budget cap excludes lowest-priority facts with trace reason
- stale fact pack marks or excludes stale facts according to mode

Exit gate:

- `graph fact pack` can answer one current-truth question with citations and trace.

## Phase 4 — Staleness + synth reuse

Goal: reuse existing graph synth/stale concepts without creating a parallel graph subsystem.

Deliverables:

- stale-source detection mapped into fact status
- optional relation to existing `graph synth stale` / refresh lifecycle
- refresh/supersede guidance, but no automatic extraction
- docs showing how facts, synthesis cards, and Pack interact

Verifier:

- mutate a source fixture and require dependent fact stale receipt
- refresh/supersede path clears stale status only with a new assertion receipt
- graph synth card preference still stays Pack-owned

Exit gate:

- stale fact cannot masquerade as current truth.

## Phase 5 — Default operator route

Goal: make the feature feel like a default experience without turning it into hidden prompt stuffing.

Deliverables:

- route/helper for "current truth / timeline / evidence" style queries
- one docs demo using synthetic fixtures
- docs positioning in advanced labs or operator path
- telemetry/receipt field that says when the fact view was used

Verifier:

- route returns fact pack for a known subject
- unknown subject falls back cleanly to existing search/pack guidance
- no automatic injection into prompts without a visible ContextPack receipt

Exit gate:

- operator can see when the fact view was used and why.

## Phase 6 — Extraction assist pilot

Goal: test extraction only after the explicit assertion path is stable.

Deliverables:

- review-only extraction proposal command
- proposed facts require source refs and confidence caps
- no auto-apply by default
- precision/recall measurement on a small fixture corpus

Verifier:

- malformed or source-less proposed fact is rejected
- proposal output is review-only (`writes_performed=false`)
- measured precision threshold is met before any apply workflow is considered

Exit gate:

- CK/operator decision before any extraction apply lane.

## Backlog

| ID | Phase | Status | Work item | Acceptance |
| --- | --- | --- | --- | --- |
| TFMV-P0-001 | 0 | ready | Freeze fact schema and source/assertion split | schema doc and fixtures cover source refs vs assertion refs |
| TFMV-P0-002 | 0 | ready | Define predicate registry v0 | unknown predicate fixture fails lint |
| TFMV-P0-003 | 0 | ready | Define interval semantics | open interval, overlap, supersede, invalidate fixtures pass |
| TFMV-P0-004 | 0 | ready | Define stable-id algorithm | rebuild fixture produces same ids |
| TFMV-P1-001 | 1 | next | Implement fact core dataclasses/parser | fixture load validates and rejects malformed records |
| TFMV-P1-002 | 1 | next | Implement source resolver interface | valid/dangling source results are typed and test-covered |
| TFMV-P1-003 | 1 | next | Implement lint rules | dangling, unknown predicate, interval conflict, over-cap confidence detected |
| TFMV-P1-004 | 1 | next | Implement derived store/rebuild | drop/rebuild preserves stable ids/current set |
| TFMV-P2-001 | 2 | queued | Add `graph fact assert` | valid source assertion writes fact + receipt |
| TFMV-P2-002 | 2 | queued | Add `graph fact current` | current truth omits superseded/invalidated facts |
| TFMV-P2-003 | 2 | queued | Add `graph fact timeline` | chronological timeline includes supersede/invalidate events |
| TFMV-P2-004 | 2 | queued | Add `graph fact lint` CLI | CLI exits nonzero on unresolved conflicts |
| TFMV-P3-001 | 3 | queued | Add `graph fact pack` | ContextPack-compatible JSON cites every included fact |
| TFMV-P3-002 | 3 | queued | Add pack trace integration | trace records include/exclude/freshness/source reasons |
| TFMV-P3-003 | 3 | queued | Add budget behavior tests | deterministic exclusion order under fixed budget |
| TFMV-P4-001 | 4 | queued | Wire stale-source detection | changed source marks dependent fact stale |
| TFMV-P4-002 | 4 | queued | Document graph synth reuse boundary | docs make facts a view, not synth-card replacement |
| TFMV-P5-001 | 5 | queued | Add operator query helper/route | known-subject route returns fact pack receipt |
| TFMV-P5-002 | 5 | queued | Add synthetic demo | docs demo proves current/timeline/evidence loop |
| TFMV-P6-001 | 6 | deferred | Add extraction proposal command | proposal is review-only and writes nothing |
| TFMV-P6-002 | 6 | deferred | Measure extraction precision | no apply lane before measured acceptance |

## Risk ledger

| Risk | Phase pressure | Control |
| --- | --- | --- |
| Fact view becomes hidden truth owner | all phases | source-required, rebuildable view, Pack-visible receipts |
| Predicate sprawl kills lint value | 0-2 | controlled predicate registry |
| Interval bugs produce false current truth | 0-2 | hard fixture suite before CLI |
| Stale facts look current | 3-4 | source freshness checks and stale exclusion by default |
| Extraction hallucination pollutes facts | 6 | review-only proposals, no auto-apply |
| Scope expands into graph DB migration | all phases | SQLite/file-backed derived view only |

## Commit and release posture

- Phase 0-3 can be local commits without release until the CLI surface is coherent.
- Phase 2 introduces user-facing CLI names; after that, changelog and docs examples must stay aligned.
- Phase 5 is the first candidate for public positioning as a default operator experience.
- Phase 6 requires a separate CK/operator approval gate before any apply path.

## Topology impact

Unchanged for this planning map. No Gateway, cron, memory slot, or retrieval backend change.
