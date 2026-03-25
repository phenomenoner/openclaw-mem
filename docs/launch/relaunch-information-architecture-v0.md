# Relaunch information architecture (v0)

Date: 2026-03-25
Status: active framing draft (narrative-lock pass)

This page locks the relaunch structure for `openclaw-mem` so README / docs index / About / launch surfaces tell one consistent product story.

## Core story in one sentence
`openclaw-mem` is a trust-aware context packing layer for OpenClaw: prove value in the query plane first, then optionally expand into controlled action-plane workflows.

## Narrative route (public order)

1. **Dream**
   - long-running agents should not quietly import stale, untrusted, or hostile context
   - memory behavior should stay inspectable under pressure

2. **Concept**
   - trust-aware context packing (smaller packs, visible trust tiers, receipts)
   - query plane first, action plane optional and write-gated

3. **Use case / demo**
   - canonical synthetic before/after proof (`trust-aware-context-pack-proof`)
   - same query + same DB + trust policy toggle ⇒ different selection with explicit receipts
   - graph/reference/knowledge-graph appears as a **flagship feature family** (provenance/trust surface), not a universal schema claim

4. **How-to / technical details**
   - sidecar-first adoption path
   - optional mem-engine promotion
   - rollback-first operator posture

## Message hierarchy (top to deep)

1. **Wedge (hero claim)**
   - smaller, cited context packs
   - trust-aware selection
   - inspectable receipts

2. **Two-plane contract**
   - Query plane (default): recall + context packing + citations/trace
   - Action plane (optional): recommendation-first maintenance queues, write-gated

3. **Adoption ladder**
   - local proof
   - sidecar on existing OpenClaw install
   - optional mem-engine promotion

4. **Operator trust surface**
   - policy surfaces (`policy_surface`, lifecycle shadow, trust/provenance receipts)
   - rollback-first posture

## Canonical page roles

- `README.md`: wedge + adoption paths + fast proof + story path
- `docs/index.md`: docs navigation hub using dream→concept→demo→how-to order
- `docs/about.md`: product boundary and audience framing
- `docs/showcase/*`: proof and artifacts
- `docs/install-modes.md` / `docs/mem-engine.md`: install boundary and expansion path
- `docs/launch/proof-first-relaunch-checklist.md`: operator release-readiness lock list
- `docs/launch/release-surface-proof-pack-v0.md`: release-note + hero + install CTA sync proof card

## Boundary rules (hard)

- Do not collapse query-plane and action-plane language.
- Do not imply silent auto-writeback as default behavior.
- Keep sidecar-first posture explicit.
- Keep KOL/GTM as a linked-but-separate lane (product framing only; no campaign control merge).
- Keep graph/reference/knowledge-graph framed as a flagship feature family, not a totalizing schema claim.
- Keep launch copy sourced from `main` repo truth only (no branch-lane ambiguity in public messaging).

## Next increments (copy can improve later)

1. tighten quickstart snippets and proof commands against latest flags,
2. keep release-note snippets synchronized as new feature families land,
3. keep GitHub/About/social copy synchronized through the checklist.
