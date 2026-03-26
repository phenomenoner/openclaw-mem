# Spec — Dream-style consolidation review v0

## Status
- Stage: **install/enable slice reached on stable main** (2026-03-26)
- Scope: recommendation-only episodic maintenance review
- Delivery posture: **candidate generation only; no canonical rewrite**
- CLI: `openclaw-mem optimize consolidation-review`

## Why this exists
`openclaw-mem` already had the right philosophical stance:
- consolidation / dream-style maintenance is attractive
- but silent rewriting of canonical memory is too much authority for a black-box pass

The missing piece was an installable operator slice that makes the idea useful without making it dangerous.

This command is that slice.

## Decision
Adopt **candidate review** as the first shipped dream-style mechanism.

That means:
- scan `episodic_events`
- emit bounded, inspectable proposals
- keep source episode rows unchanged
- keep graph truth unchanged
- require explicit human/operator review before any later write path exists

## What the command emits
`openclaw-mem optimize consolidation-review --json`

Structured report kind:
- `openclaw-mem.optimize.consolidation-review.v0`

Candidate families:
1. **summary candidates**
   - clusters of related episodic rows within the same scope/session
   - draft summary text + shared tokens + source episode refs
2. **archive candidates**
   - low-signal episodic rows nearing their retention GC horizon
   - includes low-signal reasons and source episode refs
3. **link candidates**
   - cross-session lexical overlap inside the same scope
   - emits pairwise proposals with shared tokens and provenance refs

## Hard boundaries
- no mutation of `episodic_events`
- no mutation of `observations`
- no graph edge auto-write
- no canonical summary promotion
- no silent forgetting beyond existing explicit GC policy

JSON receipts make this explicit via:
- `policy.writes_performed = 0`
- `policy.memory_mutation = "none"`
- `policy.canonical_rewrite = "forbidden"`

## Why this is different from graph refresh
`graph topology-refresh` is deterministic rebuild of a derived query layer from repo-backed truth.

`optimize consolidation-review` is not a rebuild and not a truth source.
It is a **maintenance proposal lane** over episodic traces.

That distinction is load-bearing:
- graph refresh = deterministic derived plane
- consolidation review = probabilistic suggestion plane

## Acceptance checks
- command runs against local SQLite with no network dependency
- command remains strict zero-write under `PRAGMA query_only`
- output contains source episode refs for every emitted candidate
- disabling/ignoring the command leaves runtime behavior unchanged

## Future work (not in this slice)
- co-selection link proposals derived from pack/recall receipts rather than lexical overlap alone
- use-based decay scoring tied to successful task outcomes
- optional reviewed writeback lane for approved summary/archive/link actions
- integration into a higher-level maintenance command/cron wrapper

## Product framing
`openclaw-mem` does not dream by rewriting truth in the dark.
It runs a reviewable maintenance shift where compression, linking, and forgetting show up first as proposals with receipts.
