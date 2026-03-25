# Relaunch information architecture (v0)

Date: 2026-03-25
Status: active framing draft

This page locks the relaunch structure for `openclaw-mem` so README / docs index / About / launch surfaces tell one consistent product story.

Scope note: maintainer-facing launch guidance in a public repo. It defines how external docs should read, but is not itself end-user product documentation.

## Core story in one sentence
`openclaw-mem` is a trust-aware context packing layer for OpenClaw: prove value in the query plane first, then optionally expand into controlled action-plane workflows.

## Public messaging route

1. **Problem framing**
   - long-running agents should not quietly import stale, untrusted, or hostile context
   - memory behavior should stay inspectable under pressure

2. **Product approach**
   - trust-aware context packing (smaller packs, visible trust tiers, receipts)
   - query plane first, action plane optional and write-gated

3. **Proof surface**
   - canonical synthetic before/after proof (`trust-aware-context-pack-proof`)
   - same query + same DB + trust policy toggle ⇒ different selection with explicit receipts
   - graph/reference/knowledge-graph appears as a **flagship feature family** (provenance/trust surface), not a universal schema claim

4. **Adoption and operations**
   - sidecar-first adoption path
   - optional mem-engine promotion
   - rollback-first operator posture

## External page emphasis

1. **Core value statement**
   - smaller, cited context packs
   - trust-aware selection
   - inspectable receipts

2. **How it behaves**
   - Query plane (default): recall + context packing + citations/trace
   - Action plane (optional): recommendation-first maintenance queues, write-gated

3. **How to adopt it**
   - local proof
   - sidecar on existing OpenClaw install
   - optional mem-engine promotion

4. **Operator confidence signals**
   - policy surfaces (`policy_surface`, lifecycle shadow, trust/provenance receipts)
   - rollback-first posture

## Page map

- `README.md`: core product message + adoption paths + fast proof + clear product overview
- `docs/index.md`: docs navigation hub using the same public-facing problem→proof→adoption story flow
- `docs/about.md`: product boundary and audience framing
- `docs/showcase/*`: proof and artifacts
- `docs/install-modes.md` / `docs/mem-engine.md`: install boundary and expansion path
- `docs/launch/proof-first-relaunch-checklist.md`: operator release-readiness lock list
- `docs/launch/release-surface-proof-pack-v0.md`: release-note + hero + install-language consistency note

## Boundary rules (hard)

- Do not collapse query-plane and action-plane language.
- Do not imply silent auto-writeback as default behavior.
- Keep sidecar-first posture explicit.
- Keep KOL/GTM as a linked-but-separate lane (product framing only; no campaign control merge).
- Keep graph/reference/knowledge-graph framed as a flagship feature family, not a totalizing schema claim.
- Keep launch copy sourced from `main` repo truth only (no branch-lane ambiguity in public messaging).
- For publicly released materials, internal narrative and external narrative must remain clearly separated; do not publish internal framing formulas or backstage positioning language as outward-facing copy.

## Next increments (copy can improve later)

1. tighten quickstart snippets and proof commands against latest flags,
2. keep release-note snippets synchronized as new feature families land,
3. keep GitHub/About/social copy synchronized through the checklist.
