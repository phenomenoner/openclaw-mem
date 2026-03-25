# Release-surface consistency note

Date: 2026-03-25  
Status: release-note and install-language consistency receipt

Purpose: keep the release-facing surfaces saying one coherent story without widening into broad website or GTM asset work.

Scope note: maintainer-facing launch guidance in a public repo. This file governs public wording, but is not itself end-user product documentation.

## Public release story baseline

Keep external messaging in this natural sequence:

1. **Problem framing:** long-running agents should not quietly import stale/untrusted/hostile context.
2. **Product approach:** trust-aware context packing with explicit trust tiers and receipts.
3. **Proof:** same query + same DB + trust-policy toggle changes selection with inspectable receipts.
4. **Adoption path:** sidecar-first install path, optional mem-engine promotion.

Boundary lock:
- main-only governance docs remain launch truth source.
- KOL/GTM is linked but separate (no control-lane merge).
- graph/reference/knowledge-graph is a flagship feature family, not a universal-schema claim.
- For publicly released materials, internal narrative and external narrative must remain clearly separated; do not publish internal framing formulas or backstage positioning language as outward-facing copy.

## Release-note surface (ready-to-paste)

### Short title line

**Trust-aware context packing for OpenClaw: smaller prompt packs, explicit trust tiers, and receipts.**

### Opening paragraph

`openclaw-mem` focuses on trust-aware context packing, not generic memory storage. Long-running agents do not only forget — they also admit stale, weak, or hostile context into future prompts. This release keeps the query plane as default, demonstrates the core behavior through a reproducible proof, and keeps rollout practical with a sidecar-first install path plus optional mem-engine promotion.

Final release-note body source:
- `docs/launch/release-note-body-v0-final.md`

### Proof links block

- Canonical proof: `docs/showcase/trust-aware-context-pack-proof.md`
- Metrics artifact: `docs/showcase/artifacts/trust-aware-context-pack.metrics.json`
- Companion demo: `docs/showcase/inside-out-demo.md`

## Hero + onboarding copy sync

Use the same outward-facing getting-started sequence across README, docs home, and install-page shortcut:

1. **Prove it locally (5 minutes)**
2. **Run sidecar on existing OpenClaw (default production path)**
3. **Promote to optional mem engine when needed**

This keeps “proof-first” and “sidecar-first” visible before deeper install detail.

## Consistency checklist receipts

- [x] README hero/onboarding wording tightened to include the shared getting-started sequence.
- [x] `docs/index.md` hero/onboarding wording aligned to the same sequence.
- [x] `docs/install-modes.md` quick-start decision guide updated to the same external-facing onboarding language.
- [x] Changelog unreleased docs note added for this release-surface sync pass.
- [x] Adjacent launch docs updated to point at this proof pack and keep checklist coherence.

## Release-candidate closure receipt

- [x] Release-note body finalized as a dedicated source doc (`docs/launch/release-note-body-v0-final.md`).
- [x] Proof-first relaunch checklist executed and marked with concrete receipt pointers.
- [x] Release-cut readiness gate status recorded in playbook truth surfaces.

## Out-of-scope guard (enforced)

- No live cron/job provisioning.
- No broad website implementation/build-out.
- No full GTM asset pack.
- No control-lane merge across relaunch and KOL/GTM.
