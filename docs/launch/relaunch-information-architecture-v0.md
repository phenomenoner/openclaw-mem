# Relaunch information architecture (v0)

Date: 2026-03-25
Status: active framing draft (structure-first)

This page locks the relaunch structure for `openclaw-mem` so README/docs/About all tell the same product story.

## Core story in one sentence
`openclaw-mem` is a trust-aware context packing layer for OpenClaw: prove value in the query plane first, then optionally expand into controlled action-plane workflows.

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

- `README.md`: product wedge + adoption paths + fast proof
- `docs/index.md`: docs navigation hub
- `docs/about.md`: product boundary and audience framing
- `docs/showcase/*`: proof and artifacts
- `docs/install-modes.md` / `docs/mem-engine.md`: install boundary and expansion path

## Boundary rules (hard)

- Do not collapse query plane and action plane language.
- Do not imply silent auto-writeback as default behavior.
- Keep sidecar-first posture explicit.
- Keep KOL/GTM as a linked-but-separate lane (this IA file is product framing only, not GTM execution control).

## Next increments (copy can improve later)

1. tighten home-page proof order (artifact first, adjectives second),
2. align quickstart snippets with latest pack policy flags,
3. sync launch copy pack and GitHub surface spec against this IA map.
