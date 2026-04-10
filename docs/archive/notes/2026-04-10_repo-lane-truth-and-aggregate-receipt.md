# openclaw-mem repo-lane truth and aggregate receipt — 2026-04-10

## Verdict
The old framing `main vs dev delta = 247; formal semantic receipt still missing` is stale and should not be reused as the current operator read.
The real question on `2026-04-10` is **repo-lane truth**, not that historical delta value.

## Current lane truth
### `openclaw-mem` (`main`)
- current branch: `main`
- current head: `80c01a2`
- current top shape: public/docs tightening plus already-landed route-auto hotfix line
- represents: the active mainline public/release-facing repo surface

### `openclaw-mem-dev`
- current branch: `docs/graph-compiled-synthesis-20260407`
- current head: `6ce7500`
- current top shape: graph / synthesis expansion work
- represents: an active development lane with newer synthesis-related work not present on `main`

### `openclaw-mem-prod`
- current branch: detached/older release-facing state (head `39b0d13`)
- represents: an older production/reference checkout, not the same truth surface as current `main`

## What is true now
- The lane family is **not broken**, but it is **multi-truth by role**.
- `main`, `dev`, and `prod` are currently serving different operator purposes and are not expected to be commit-identical.
- Because of that, chasing an old single-number delta as the primary operator summary is misleading.

## What should replace the stale framing
Use this operator reading instead:
1. **source-of-truth question** — which lane is authoritative for the decision at hand?
2. **integration question** — is there a bounded dev -> main change that should be promoted?
3. **aggregate freshness question** — do our human-facing receipts still describe the current heads truthfully?

## Honest status
- There is no evidence here of a fresh product outage caused by repo divergence alone.
- There is evidence that older aggregate language about `delta 247` no longer matches the current lane picture.
- The needed follow-up is therefore a **fresh aggregate receipt / lane-restatement**, not a forced replay of the older numeric comparison story.

## Recommended operator replacement sentence
Replace the stale summary with:

> `openclaw-mem` currently has role-separated `main` / `dev` / `prod` lanes; the active operator need is fresh lane-truth/aggregate wording, not revival of the older `delta 247` semantic receipt.

## Smallest next slice
If further closure is needed, produce one bounded comparison packet:
- `main` head and purpose
- `dev` head and purpose
- whether a bounded dev -> main promotion candidate now exists
- whether any human-facing aggregate surface still speaks in the stale `delta 247` language

## Receipts
- `openclaw-mem@80c01a2`
- `openclaw-mem-dev@6ce7500`
- `openclaw-mem-prod@39b0d13`
