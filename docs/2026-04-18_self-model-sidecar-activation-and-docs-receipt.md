# self-model side-car activation and docs receipt

Date: 2026-04-18
Status: shipped locally, verifier-backed
Topology: unchanged

## Change
- updated public-facing docs to expose the governed continuity side-car as a derived, rebuildable lane
- updated the dedicated ops skill so copy-paste commands match the supported `uv run --python 3.13 -- python -m openclaw_mem ...` entrypoint
- enabled the live continuity control plane on this host at a 300s cadence
- generated the first persisted snapshot, autorun receipt, and public-safe summary on the real install

## Why now
PR #71 landed the control-plane v1 surface. The honest next step was to make the operator-facing docs and skill truthful, then activate the real lane instead of leaving the capability half-shipped.

## Success criteria
- public docs describe continuity as derived, governed, and not memory-of-record
- activation guidance includes what enable actually does, where artifacts land, and how to roll back
- dedicated ops skill matches the documented command shape
- live install reports `enabled: true` and produces a persisted snapshot + autorun receipt

## Rollback
- docs/skill: revert this commit
- live continuity lane: `uv run --python 3.13 -- python -m openclaw_mem continuity disable --json`
- local residue stays under `~/.openclaw/memory/openclaw-mem/self-model-sidecar/`

## Receipts
### Docs / skill updated
- `README.md`
- `docs/about.md`
- `docs/install-modes.md`
- `docs/deployment.md`
- `skills/self-model-sidecar.ops.md`

### Second-brain review
- `/root/.openclaw/workspace/.state/decision-council/claude_public_docs_continuity_review.md`
- `/root/.openclaw/workspace/.state/decision-council/claude_public_docs_continuity_review_pass2.md`
- `/root/.openclaw/workspace/.state/decision-council/claude_public_docs_continuity_review_final.md`

### Live activation
- control receipt: `/root/.openclaw/memory/openclaw-mem/self-model-sidecar/control-history/20260418T133318.211456_0000__1776519198211__enable.json`
- status run dir: `/root/.openclaw/memory/openclaw-mem/self-model-sidecar`
- first persisted snapshot: `/root/.openclaw/memory/openclaw-mem/self-model-sidecar/snapshots/sms:v0:98bf8da6f3696d3e.json`
- latest snapshot pointer: `/root/.openclaw/memory/openclaw-mem/self-model-sidecar/snapshots/latest.json`
- first autorun receipt: `/root/.openclaw/memory/openclaw-mem/self-model-sidecar/autorun/run-1776519203658-1.json`

### Verification excerpts
- `continuity status` reports `enabled: true`, `cadence_seconds: 300`, `latest_pointer_present: true`
- `continuity public-summary` returns a bounded public-safe summary and warns when fragile claims are withheld
- `continuity release-history` is empty, which is expected before any weaken / rebind / retire action
