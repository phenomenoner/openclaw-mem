# Temporal fact materialized view v0

Status: IMPLEMENTED v1.9.26 for explicit assertions, current/timeline/lint/pack/stale/route, and review-only extraction proposals.

Decision: build this lane as a source-linked materialized view over Store evidence, not as a new source of truth.

## Problem

Operators need a default way to ask:

- what is currently true about this subject?
- how did that truth change over time?
- which receipts, docs, or memory records support it?
- is the answer stale, contradicted, or missing source evidence?

The existing graph/query/synthesis surfaces can answer parts of this, but the default operator experience still feels like a support lane. This v0 promotes the experience without promoting graph data into hidden authority.

## Doctrine

Temporal facts are a compiled view:

```text
Store sources -> temporal fact view -> Pack output -> Observe receipts
```

Rules:

- Store remains the durable evidence owner.
- Pack remains the prompt/context assembly owner.
- Observe remains the receipt and audit owner.
- The temporal fact view is rebuildable from Store/Observe sources.
- A fact without a resolvable source is invalid.
- Stale facts may be shown as stale evidence, but must not be presented as current truth.

Non-goal wording:

- no "wiki as truth"
- no black-box graph memory
- no implicit prompt stuffing
- no graph DB requirement in v0
- no automatic LLM extraction in v0

## Smallest useful v0

V0 is single-subject truth resolution with explicit assertions only.

It must answer three questions:

1. Current truth: active facts for a subject, grouped by predicate.
2. Timeline: how those facts changed, including invalidation and supersession.
3. Evidence pack: facts plus source snippets and receipts in a ContextPack-compatible form.

V0 must not include multi-hop inference, automated extraction, confidence learning, or broad knowledge graph traversal.

## Data contract

Draft fact record:

```yaml
schema: openclaw-mem.graph.fact.v0
id: fact_<stable_id>
subject:
  ref: entity:<normalized-id>
  label: string
predicate: controlled_predicate_id
object:
  type: literal | entity_ref | json
  value: any
valid_from: iso8601
valid_to: iso8601 | null
status: active | superseded | invalidated | retracted | stale
confidence_tier: source_capped | corroborated | operator_asserted | low
source_refs:
  - kind: receipt | doc | memory | daily_log | episodic
    ref: string
    locator: string | null
assertion_ref:
  kind: receipt
  ref: string
supersedes: [fact_id]
superseded_by: [fact_id]
created_at: iso8601
asserted_by: operator | tool | import
```

Core invariants:

- `source_refs` has at least one resolvable source.
- `assertion_ref` records the assertion act separately from evidence.
- `valid_from <= valid_to` when `valid_to` is present.
- open intervals use `valid_to = null`.
- each single-valued `(subject, predicate)` has at most one current active fact.
- multi-valued predicates must be declared in the predicate registry.
- unknown predicates fail lint.
- confidence cannot exceed the cap implied by the strongest source tier.
- stable ids survive cache rebuilds from the same assertion/evidence tuple.

## Predicate registry

V0 needs a small controlled vocabulary, not free-form predicates.

Initial classes:

- `owns`
- `uses`
- `depends_on`
- `replaces`
- `status`
- `configured_as`
- `decision`
- `source_of_truth`
- `retired_by`

Each predicate declares:

- cardinality: single or multi
- object type
- allowed aliases
- conflict behavior
- source tier floor, if any

## CLI surface

Shipped namespace:

```bash
openclaw-mem graph fact assert \
  --subject entity:openclaw-mem \
  --predicate source_of_truth \
  --object "Store records" \
  --valid-from 2026-06-03T00:00:00Z \
  --source-ref memory:2026-06-03.md#openclaw-mem-kg-facts \
  --assertion-ref receipt:.state/openclaw-mem-kg-facts-v0/...

openclaw-mem graph fact current --subject entity:openclaw-mem --json
openclaw-mem graph fact timeline --subject entity:openclaw-mem --predicate source_of_truth --json
openclaw-mem graph fact pack --subject entity:openclaw-mem --budget-tokens 1200 --json
openclaw-mem graph fact lint --json
openclaw-mem graph fact assert ... --supersedes fact_...
openclaw-mem graph fact invalidate --fact-id fact_... --source-ref ...
openclaw-mem graph fact stale --json
openclaw-mem graph fact route "current truth for entity:openclaw-mem" --json
openclaw-mem graph fact propose --text "entity:openclaw-mem status active" --source-ref doc:source.md
openclaw-mem graph fact measure-extraction --corpus corpus.jsonl --golden golden.jsonl
openclaw-mem graph fact rebuild --file facts.jsonl --json
```

`graph fact pack` should emit a ContextPack-compatible object plus a trace showing included facts, excluded facts, source resolution, freshness, and budget decisions.

## Reuse map

| Need | Existing surface to reuse |
| --- | --- |
| View namespace | `graph` CLI family |
| Source snippets | docs cold lane and episodic search |
| Pack output | `ContextPack` schema and `pack --trace` conventions |
| Staleness | `graph synth stale` / refresh lifecycle |
| Lint | existing deterministic `graph lint` style |
| Audit | Observe receipts / artifact refs |
| Visualization | symbolic canvas, optional only |

## Implementation slices

1. Spec + predicate registry.
2. Storage/view schema and deterministic lint.
3. `assert`, `current`, and `timeline` CLI commands with explicit assertions only.
4. `pack` integration that emits ContextPack-compatible output and trace receipts.
5. Staleness/rebuild proof: drop derived cache and rebuild the same current-truth set from sources.
6. Optional default operator hook: route "current truth / timeline / evidence" questions to this view before broader graph/query surfaces.

Detailed phase map and backlog: `docs/specs/temporal-fact-materialized-view-dev-phases-v0.md`.

## Acceptance smokes

1. Assert with a valid source: stored, receipt emitted, `current` shows it.
2. Assert with a dangling source: rejected; if injected manually, `lint` fails.
3. Overlapping contradiction without supersession: `lint` fails.
4. Supersession: prior fact gets `valid_to`, status becomes `superseded`, and `current` shows only the new fact.
5. Invalidation: timeline shows the invalidation event and current truth omits the invalidated fact.
6. Source mutation: stale check flags dependent facts.
7. Confidence over source-tier cap: `lint` fails.
8. `fact pack` is deterministic, budget-bounded, and cites every included fact.
9. Rebuild survival: dropping the derived cache and rebuilding produces the same stable ids and current-truth set.

## Rollback

V0 is additive and derived. Rollback is:

- disable the `graph fact` CLI namespace or operator route;
- keep source Store/Observe records untouched;
- delete/rebuild the derived fact view if needed.

No OpenClaw Gateway config, cron topology, or live memory backend change is required for the planning slice.
