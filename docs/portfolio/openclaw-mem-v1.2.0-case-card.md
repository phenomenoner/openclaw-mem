# Case card — openclaw-mem v1.2.0

## What it is

**openclaw-mem** is a local-first memory layer for OpenClaw focused on **trust-aware context packing**: generating small, cited prompt packs while keeping trust tiers and provenance explicit.

## The problem

In long-running agent systems, failure often isn’t “storage.” It’s **admission**:
- stale notes keep getting injected because they still match the query
- untrusted or hostile content retrieves well and quietly pollutes future prompts
- prompt packs bloat into hard-to-debug context dumps
- operators lose the ability to answer “why did this enter context?”

## The approach (what makes it notable)

- **Proof-first:** behavior is demonstrated via a reproducible synthetic fixture and inspectable receipts.
- **Trust tiers + receipts:** selection is not a black box—packs can include citations and traceable inclusion/exclusion reasons.
- **Rollbackable adoption:** sidecar-first by default; promote to an optional engine only when the extra capability is earned.

## What shipped in v1.2.0 (high-signal)

- Deterministic local recall loop: `search → timeline → get`.
- Trust-aware packing surfaces with trace receipts (`pack`, `--trace`, policy surfaces).
- Inspectable graph/provenance surfaces (topology refresh/query + drift checks).
- Recommendation-only “action plane” review queues (no silent writeback).
- Optional engine upgrades including a **Docs Memory cold lane** for ingest/search over repos/docs with scoped retrieval and receipts.

## Proof / links

- Canonical proof: `docs/showcase/trust-aware-context-pack-proof.md`
- Metrics artifact: `docs/showcase/artifacts/trust-aware-context-pack.metrics.json`
- Releases: https://github.com/phenomenoner/openclaw-mem/releases
