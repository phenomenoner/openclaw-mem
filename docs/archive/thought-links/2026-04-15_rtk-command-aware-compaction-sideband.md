# 2026-04-15 — RTK / command-aware compaction sideband

Status: adopted as a **thought-link + minimal Observe slice**, not as a silent shell-rewrite dependency.

## External reference
- RTK: <https://github.com/rtk-ai/rtk>

## Verdict
RTK proved the operator value of **command-aware output compaction** for AI coding workflows.

We are **not** adopting its strongest magic move, which is silent command rewriting via shell hooks, as a new truth surface inside `openclaw-mem`.

We **are** adopting the underlying pattern:
- compact noisy command output,
- keep raw evidence recoverable,
- make provenance explicit,
- and record the compact view as a **sideband receipt**, not as canonical memory.

## What we take
- command-family-specific compaction is high-ROI
- raw output should be offloaded, not shoved into prompt budget
- compacted evidence should be paired with explicit provenance
- operators need a deterministic recovery path back to raw evidence

## What we refuse
- shell hook magic as the only integration contract
- silent mutation of command truth
- summaries replacing raw evidence as the canonical operator surface
- lossy compression without a receipt that points back to the raw artifact

## Minimal absorption slice
Land a small Observe-layer contract:
- `openclaw-mem artifact compact-receipt`
- stores or references the raw artifact
- records the original command plus optional rewritten/compactor command
- emits a stable sideband JSON receipt with compact text and raw-artifact provenance

This keeps Store/Pack/Observe clean:
- **Store** still owns durable records
- **Pack** can later consume compact receipts deliberately
- **Observe** proves what was compacted and how to recover raw

## Why this is the right first cut
It advances the real gate without over-committing to a runtime hook architecture:
- local install of RTK can happen immediately for operator use
- `openclaw-mem` gets an explicit receipt contract now
- future Pack integration can consume this contract without needing shell magic

## Follow-up candidates
- pack-side preference for compact receipts when raw artifact exists and provenance is intact
- per-command compaction families (`git diff`, test failures, long logs)
- raw rehydrate affordances in pack traces / operator surfaces
