# Self-improvement Slice 6 — blade map v0

Date: 2026-05-12
Status: implementation blade map

## Goal

Implement a local staged mutation framework with reviewable `plan → stage → apply → rollback` receipts.

## Boundary

- Repo: `openclaw-mem` only.
- No OpenClaw core/runtime changes.
- Apply is limited to synthetic/local fixture files under `--allowed-root`.
- L3/L4/protected/manual-approval mutations are blocked.

## Outputs

- `openclaw_mem/mutation_framework.py`
- `openclaw-mem mutation plan|validate|stage|apply|rollback`
- Unit and CLI integration tests
- Public docs and receipt
- Version/changelog for release

## Verifier plan

- targeted pytest for mutation framework and CLI
- counterfactual tests for L3/L4/protected/path escape/failure rollback
- CLI smoke for plan/stage/apply/rollback
- MkDocs strict build
- Claude public-facing review before push
- local editable install smoke

## Rollback

Revert the Slice 6 commit or release from prior tag `v1.9.13`. No runtime topology rollback is required.
