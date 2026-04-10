# openclaw-mem bounded lane-comparison packet — 2026-04-10

## Verdict
The useful comparison question tonight is **not** “what is the old numeric main-vs-dev delta?”
The useful comparison question is:

> which lane is authoritative for the next decision, and is there a bounded promotion candidate from `dev` into `main` worth opening?

## Lane roles
### `main`
- head: `7c75a9b`
- role: active public/mainline documentation and already-landed route-auto line
- use when: operator or public truth must point at the current main branch surface

### `dev`
- head: `6ce7500`
- branch label: `docs/graph-compiled-synthesis-20260407`
- role: active synthesis/graph expansion lane
- use when: reviewing newer experimental or expansion work that has not yet been restated as mainline truth

### `prod`
- head: `39b0d13`
- role: older release/reference checkout
- use when: historical production/reference behavior matters

## What this packet retires
Do not summarize the current situation as:
- “main vs dev delta 247”
- “formal semantic receipt still missing”

That wording describes an older comparison moment, not the current operator need.

## Decision-relevant comparison grid
### If the question is public/mainline truth
Use `main`.

### If the question is whether new graph/synthesis work should move forward
Inspect `dev` and ask whether there is a bounded promotion candidate, with explicit scope and verifier.

### If the question is old release/reference behavior
Use `prod`, but do not confuse it with current mainline source of truth.

## Honest current read
- the family is role-separated, not broken
- the next useful operator artifact is a bounded **promotion candidate packet**, not a stale numeric restatement
- until such a packet exists, the truthful summary is lane-role separation, not release-train urgency

## Smallest next bounded cut
If CK wants this line pushed further, the next packet should answer only four questions:
1. what exact `dev` scope is proposed for promotion?
2. what verifier proves it is worthy of `main`?
3. what docs/public-surface changes would promotion force?
4. what stays intentionally out of scope?

## Receipts
- `openclaw-mem@7c75a9b`
- `openclaw-mem-dev@6ce7500`
- `openclaw-mem-prod@39b0d13`
- `docs/archive/notes/2026-04-10_repo-lane-truth-and-aggregate-receipt.md`
