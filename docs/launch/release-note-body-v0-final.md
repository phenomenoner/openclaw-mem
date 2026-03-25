# Release-note body (v0 final)

Date: 2026-03-25  
Status: finalized for relaunch PASS 4 release-candidate closure

Scope note: maintainer-facing release-note draft in a public repo; publish only the body text intended for end users.

## Title line

**Trust-aware context packing for OpenClaw: smaller prompt packs, explicit trust tiers, and receipts.**

## Release-note body

`openclaw-mem` focuses on trust-aware context packing, not generic memory storage. Long-running agents do not only forget — they also admit stale, weak, or hostile context into future prompts. This release keeps the query plane as default, keeps the action plane optional and write-gated, and demonstrates the core behavior through a reproducible proof.

The operator path stays practical and rollbackable: prove the behavior locally first, run sidecar on existing OpenClaw as the default production path, then promote to the optional mem-engine only when hybrid recall and policy controls are clearly needed.

Publishing boundary for this draft:
- Keep the public note focused on product behavior, proof, and install guidance.
- Exclude internal campaign/governance language from the final published release text.

## Proof links block

- Canonical proof: `docs/showcase/trust-aware-context-pack-proof.md`
- Metrics artifact: `docs/showcase/artifacts/trust-aware-context-pack.metrics.json`
- Companion demo: `docs/showcase/inside-out-demo.md`

## Getting-started sequence (keep this order)

1. **Prove it locally (5 minutes)**
2. **Run sidecar on existing OpenClaw (default)**
3. **Promote to optional mem engine when needed**
