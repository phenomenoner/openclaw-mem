# Compiled synthesis layer — wiki-maintainer pattern without the wiki dependency (2026-04-07)

This thought-link distills one useful pattern from a personal-knowledge-base / LLM-wiki gist into `openclaw-mem` language.

The value is **not** Obsidian, graph view, or a generic "LLM writes your wiki" pitch.
The durable design signal is simpler:

> retrieval should not be forced to rediscover the same cross-source synthesis every time.
> Some conclusions deserve to become a small, maintained, provenance-carrying compiled artifact.

## Source posture
- Source: Karpathy gist — `llm-wiki`
  - <https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f>
- Trust: **untrusted inspiration / field note**, not authority
- What we take: the **compiled synthesis layer** pattern only
- What we explicitly ignore: Obsidian/UI/tooling specifics

## Why it matters to openclaw-mem
`openclaw-mem` already has:
- capture (`graph capture-git`, `graph capture-md`)
- bounded retrieval (`graph index`, `graph preflight`, `graph pack`)
- topology/query surfaces with provenance

What it still lacks is a compact, reusable middle layer between:
- raw observations / captured refs
- one-off query-time reconstruction

That gap shows up as repeated work:
- asking the same cross-source question again
- having to reconstruct the same path / comparison / synthesis again
- no cheap way to tell whether a prior synthesis is now stale

## Design constraint we adopt
Treat Graphic Memory as capable of maintaining **compiled synthesis cards**:
- derived from bounded selected refs
- provenance-carrying
- stale-checkable
- fail-open when disabled

This is a better fit for `openclaw-mem` than a "write everything into a wiki" posture because it preserves:
- progressive disclosure
- auditable receipts
- layer separation (L1 vs docs vs topology vs graph artifacts)

## What we should add (high-ROI)
1. **Compiled synthesis cards**
   - not L1 durable memory by default
   - not topology truth
   - a portable derived artifact
2. **Staleness checks**
   - if source refs or contradiction candidates changed, the card should show `stale|review`
3. **Graph lint / maintenance**
   - orphan pressure
   - stale cards
   - missing provenance
   - repeated capture without a reusable synthesis layer

## What we should NOT add from this inspiration
- no UI dependency
- no graph DB detour
- no giant autonomous wiki-writing loop
- no automatic promotion of all captured material into long-lived summaries
- no collapse of docs/topology/memory/graph artifacts into one trust tier

## Concrete spec pointer
- Spec: `docs/specs/graphic-memory-compiled-synthesis-v0.md`

## Receipted conclusion
This inspiration is worth adopting only as:
- **compiled synthesis artifact**
- **stale/lint maintenance loop**
- **reuse before re-derivation**

Everything else is optional garnish.
