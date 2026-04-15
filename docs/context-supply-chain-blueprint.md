# openclaw-mem v2 blueprint

Status: implementation plan aligned to the current shipped surface.
Audience: operators, contributors, and evaluators.

## Verdict

`openclaw-mem` should be built and explained as a **context supply chain**.

That means three primary responsibilities, in order:

1. **Store** what matters in a durable, inspectable way.
2. **Pack** what fits into a bounded, cited context bundle.
3. **Observe** what was included, excluded, offloaded, or changed.

This keeps the project focused on runtime usefulness instead of accumulating disconnected memory features.

## Whole-product promise

Given a task, query, or vague prompt, the system should reliably produce the **smallest useful context bundle** that is:

- relevant,
- bounded,
- cited,
- auditable,
- and rollback-friendly.

## Architecture

### Store

Primary shipped surfaces:

- JSONL capture
- SQLite ingest + recall
- optional `openclaw-mem-engine` slot backend
- importance and trust-aware retrieval inputs

Store owns durable records and retrieval candidates.
It does not own prompt assembly on its own.

### Pack

Primary shipped surfaces:

- `openclaw-mem pack`
- `openclaw-mem.context-pack.v1`
- `openclaw-mem.pack.trace.v1`

Pack owns the injection contract.
It should be the only place where retrieval candidates become a bounded prompt-ready bundle.

### Observe

Primary shipped surfaces:

- trace receipts
- artifact stash/fetch/peek
- artifact compaction sideband receipts
- local files and deterministic JSON outputs

Observe keeps the system explainable.
It proves what was selected, what was cut, where large raw payloads went, and when a compacted command view is standing beside raw evidence instead of replacing it.

Current Observe-side command-compaction contract:
- `artifact compact-receipt` binds compact output to a recoverable raw artifact
- `artifact rehydrate` recovers bounded raw evidence from a receipt or raw handle
- `pack` may emit `compaction_policy_hints` as advisory-only family guidance without mutating retrieval ranking or durable truth

## Product split

### Core

These should stay on the main line:

- sidecar capture + ingest
- SQLite recall and hybrid recall inputs
- `ContextPack` contract
- pack traces and receipts
- artifact offload for large/raw payloads
- optional mem-engine slot ownership

### Optional

These are valuable, but should not blur the main contract:

- conservative autoRecall / autoCapture
- docs cold lane
- episodic extraction
- topology query helpers

### Fold into core, not parallel kingdoms

These should enrich the main line rather than becoming separate products:

- graph-derived selection signals
- synthesis cards used as packable summaries
- context-budget sidecar handles

If they cannot improve Store, Pack, or Observe, they should not expand the surface area yet.

## Recommended implementation sequence

### Phase 1, freeze the pack contract

Goal: make the packer a stable public surface.

Ship:

- `openclaw-mem.context-pack.v1`
- exact JSON contract tests
- docs that explain the contract to external users

Success looks like: the bundle can be consumed by runtime code, tests, and ops tooling without reverse-engineering ad hoc keys.

### Phase 2, enforce one write path into engine-owned memory

Goal: avoid ownership blur when mem-engine is active.

Ship:

- single write path into mem-engine
- explicit read-only mode for watchdog lanes
- config/docs that reject shadow storage patterns

Success looks like: no ambiguity about which surface owns canonical durable memory.

### Phase 3, treat artifact offload as normal pack infrastructure

Goal: keep raw payloads off-prompt without losing debuggability.

Ship:

- first-class handle references in pack/observe flows where needed
- bounded fetch/peek ergonomics
- docs that show operators when to offload vs inline

Success looks like: large tool output stops bloating prompts while staying recoverable.

### Phase 4, fold graph into pack selection

Goal: graph improves packing quality instead of becoming a separate retrieval kingdom.

Ship:

- graph-derived ranking or coverage hints into pack
- graph-aware receipts
- strict fail-open posture when graph state is missing or stale

Success looks like: graph helps select or compress better context, but pack still works without it.

## Boundary rules

- **Store** owns durable facts and retrieval candidates.
- **Pack** owns bounded prompt assembly.
- **Observe** owns receipts, traces, and offloaded raw payload visibility.
- Graph, docs, and synthesis artifacts may feed Pack, but they do not get separate truth ownership.
- If mem-engine owns the OpenClaw slot, writes must go through that lane only.

## Verification plan

Minimum verifier set for the v2 line:

- unit/integration tests for `pack` JSON contract
- smoke command for `pack --trace`
- smoke command for `artifact stash/fetch/peek`
- docs review for external-reader clarity
- local install smoke for `openclaw-mem --help` and one pack invocation

## Rollback posture

- Contract additions should be additive where possible.
- Legacy top-level `bundle_text/items/citations` should remain available while downstream users migrate.
- Mem-engine remains optional and rollbackable through OpenClaw slot configuration.
- Graph-aware packing must fail open.

## Non-goals for this line

- turning graph into a separate database product first
- shipping speculative agent autonomy before pack quality is stable
- building a hosted memory control plane
- stuffing raw artifacts into durable memory for convenience
