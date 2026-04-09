# Thought-link — graphify-style discovery absorbed into route-auto synthesis propagation

Date: 2026-04-10

## Source cue
External inspiration: `graphify` (multimodal corpus -> discovery graph / report / export stack).

## What we took
- discovery value should be translated into a bounded **product surface**, not left as an isolated graph demo
- confidence / coverage language matters
- token-compression value is strongest when it reaches the default operator entrypoint

## What we refused
- graph-as-truth inversion
- raw semantic graph becoming the canonical memory store
- multimodal ingestion becoming the mainline shipping slice

## How it landed in openclaw-mem
Instead of cloning graphify's whole stack, we absorbed the idea into a smaller whole-product slice:
- `route auto` now carries synthesis-aware coverage receipts (`preferredCardRefs` / `coveredRawRefs`)
- `openclaw-mem-engine` can mirror that same hint into live turns through `autoRecall.routeAuto`
- raw refs stay visible and auditable
- the lane remains fail-open and recommendation-only

## Why this is the right absorption cut
This pushes compiled synthesis into the **default routing surface** without changing durable-memory truth or widening the product into a new graph platform.
