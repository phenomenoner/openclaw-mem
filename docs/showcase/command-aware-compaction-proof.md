# Command-aware compaction proof

This is the smallest public-safe proof for the command-aware compaction lane.

It demonstrates four things together:
- a compacted command view can be stored as an Observe-side receipt
- the receipt keeps a deterministic pointer back to raw evidence
- `pack` can prefer the compact text for bounded injection
- family metadata can shape advisory policy hints without mutating retrieval ranking

## Files

- [Compaction receipt](artifacts/command-aware-compaction.receipt.json)
- [Rehydrate receipt](artifacts/command-aware-compaction.rehydrate.json)
- [Pack output](artifacts/command-aware-compaction.pack.json)
- [Metrics summary](artifacts/command-aware-compaction.metrics.json)

## Scenario

Synthetic example:
- raw command output is a tiny git diff
- compact output is `M app.py (+1 -1)`
- `artifact compact-receipt` binds the two
- `artifact rehydrate` proves bounded raw recovery
- `pack` selects the receipt and emits both `compaction_sideband` and `compaction_policy_hints`

The showcase now also includes a second synthetic proof for `test_failures`:
- raw `pytest -q` failure output
- compact triage summary
- receipt + rehydrate + pack + metrics artifacts under `docs/showcase/artifacts/test-failures-compaction.*`

## What the proof shows

### 1. Observe keeps both sides

The receipt records:
- `family: git_diff`
- compact text
- raw artifact handle
- raw bytes / kind

This means compaction is additive. It does not replace the raw evidence lane.

### 2. Raw recovery stays deterministic

The rehydrate receipt shows bounded recovery from the raw artifact handle referenced by the compaction receipt.

That keeps the product honest: compact is for usability, raw is still available for exact claims.

### 3. Pack prefers compact text, not compact truth

The pack output uses the compact text for `bundle_text`:

```text
- [obs:1] M app.py (+1 -1)
```

But it also preserves:
- `compaction_sideband.selected[].rawArtifactHandle`
- `compaction_sideband.raw_rehydrate_hint`
- `trace.extensions.compaction_sideband`

### 4. Family hints stay advisory-only

The same pack output emits:
- `compaction_policy_hints.mode = advisory_only`
- `preferred_families = ["git_diff"]`
- one guidance line telling the operator to rehydrate raw diff before exact line-level claims

This is the key product boundary.

Family metadata can improve human/operator behavior now, without becoming ranking truth or write-path logic.

The `test_failures` proof shows the same boundary with a different operator posture:
- compact first for triage speed
- raw second for exact stack traces and assertions

## Why this matters

This lane upgrades `openclaw-mem` in the right direction:
- smaller bounded prompt bundles
- better explainability for compacted command output
- safer review posture because raw evidence is still reachable

It also keeps the architecture clean:
- no new canonical-memory layer
- no new storage tables
- no silent automatic rehydrate inside pack

## Recommended operator talk track

- compact first for orientation
- raw second for exactness
- treat family hints as policy cards, not as ground truth

If you want the broader pack story first, start with the [trust-aware context pack proof](trust-aware-context-pack-proof.md).
