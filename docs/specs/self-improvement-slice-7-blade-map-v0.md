# Self-improvement Slice 7 — blade map v0

Date: 2026-05-12
Status: implementation blade map

## Goal

Add governed apply review and release-hardening gates as receipt-producing checks.

## Boundary

- Repo: `openclaw-mem` only.
- Review-only: no mutation apply, publish, tag, cron, gateway, plugin, or OpenClaw core changes.
- L3/L4 remain blocked from auto-apply even if approval flags are recorded.

## Outputs

- `openclaw_mem/governed_release.py`
- `openclaw-mem governed apply-review`
- `openclaw-mem governed release-check`
- Unit and CLI tests
- Public docs and receipt
- Version/changelog update

## Verifier plan

- targeted pytest for governed review and CLI
- counterfactuals: L2 blocked without config gate, L2 allowed with gate, L3/L4 still blocked, version mismatch fails, public marker fails
- CLI smoke for apply-review and release-check
- MkDocs strict build
- Claude public-facing review before push
- local editable install smoke

## Rollback

Revert the Slice 7 commit or release from prior tag `v1.9.14`. No runtime topology rollback is required.
