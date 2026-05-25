# Qdrant Edge Optional Backend v1.9.22 Release Review — 2026-05-26

Status: **pre-push review candidate**  
Topology impact: **unchanged** — this release adds disabled-by-default optional backend wiring and docs; it does not mutate live OpenClaw config, restart Gateway, expose ports, or enable Qdrant Edge as default.

## Scope

This release packages the previously local Qdrant Edge / retrieval-backend implementation slice that was present in the workspace but missing from `origin/main`.

## Added

- Disabled-by-default `retrievalBackend` config schema in `openclaw-mem-engine`.
- Retrieval backend planning boundary with LanceDB default and Qdrant Edge opt-in.
- Runtime retrieval router with Qdrant Edge fallback to LanceDB.
- Bounded Qdrant Edge subprocess adapter and query bridge.
- Public-facing specs/runbooks for optional backend design, lifecycle gates, no-restart wiring, and live-activation procedure.

## Public-facing safety posture

- LanceDB remains default.
- Qdrant Edge is an optional read-index/cache, not canonical storage.
- Canonical writes remain outside Qdrant Edge.
- Live activation still requires explicit config patch + restart/readback gate.
- Public docs were scanned/sanitized for local absolute operator paths and secrets; status snapshot paths are placeholder-normalized.

## Verifier

Artifacts:

- `docs/receipts/artifacts/qdrant-edge-v1.9.22-node-test-2026-05-26.tap`
- `docs/receipts/artifacts/qdrant-edge-v1.9.22-node-test-2026-05-26.err`
- `docs/receipts/artifacts/qdrant-edge-v1.9.22-status-2026-05-26.json` (sanitized public path snapshot)

Results:

- Node tests: 21 pass / 0 fail.
- `openclaw_mem` version readback: `1.9.22`.
- No live config mutation performed.

## Tag recommendation

Recommended tag after pre-push review passes:

- `v1.9.22`

## Rollback

- Revert the release commit before push, or reset `main` before tag if review fails.
- If already pushed, revert the commit and publish a follow-up patch tag; do not force-push public history unless explicitly approved.
