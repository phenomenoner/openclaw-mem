# Release-surface proof pack (PASS 3)

Date: 2026-03-25  
Status: bounded docs/copy closure for relaunch serial queue PASS 3

Purpose: keep the release-facing surfaces saying one coherent story without widening into broad website or GTM asset work.

## Canonical release story spine

Use this order everywhere (dream → concept → use case/demo → how-to):

1. **Dream:** long-running agents should not quietly import stale/untrusted/hostile context.
2. **Concept:** trust-aware context packing with explicit trust tiers + receipts.
3. **Use case/demo:** same query + same DB + trust-policy toggle changes selection with inspectable receipts.
4. **How-to:** sidecar-first install path, optional mem-engine promotion.

Boundary lock:
- main-only governance docs remain launch truth source.
- KOL/GTM is linked but separate (no control-lane merge).
- graph/reference/knowledge-graph is a flagship feature family, not a universal-schema claim.

## Release-note surface (ready-to-paste)

### Short title line

**Trust-aware context packing for OpenClaw: smaller prompt packs, explicit trust tiers, and receipts.**

### Opening paragraph

`openclaw-mem` is positioned around trust-aware context packing, not generic memory storage. Long-running agents do not only forget — they also admit stale, weak, or hostile context into future prompts. This release keeps the query plane as default, demonstrates the wedge through a reproducible proof, and keeps rollout practical with a sidecar-first install path plus optional mem-engine promotion.

### Proof links block

- Canonical proof: `docs/showcase/trust-aware-context-pack-proof.md`
- Metrics artifact: `docs/showcase/artifacts/trust-aware-context-pack.metrics.json`
- Companion demo: `docs/showcase/inside-out-demo.md`

## Hero + CTA sync contract

Use the same operator CTA ladder across README, docs home, and install-page shortcut:

1. **Prove it locally (5 minutes)**
2. **Run sidecar on existing OpenClaw (default production path)**
3. **Promote to optional mem engine when needed**

This keeps “proof-first” and “sidecar-first” visible before deeper install detail.

## PASS 3 receipts (surface checklist)

- [x] README hero/CTA wording tightened to include the shared release CTA ladder.
- [x] `docs/index.md` hero/CTA wording aligned to the same ladder.
- [x] `docs/install-modes.md` fast-decision shortcut updated to the same CTA verbs/order.
- [x] Changelog unreleased docs note added for this release-surface sync pass.
- [x] Adjacent launch docs updated to point at this proof pack and keep checklist coherence.

## Out-of-scope guard (enforced)

- No live cron/job provisioning.
- No broad website implementation/build-out.
- No full GTM asset pack.
- No control-lane merge across relaunch and KOL/GTM.
