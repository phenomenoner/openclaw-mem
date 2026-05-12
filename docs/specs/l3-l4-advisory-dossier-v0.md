# L3/L4 Advisory Dossier v0 — blade map

Date: 2026-05-12
Status: implementation blade map
Owner: Lyria

## Goal

Turn high-risk governed apply candidates into operator-facing advisory dossiers that CK can approve or reject before any execution line starts.

## Boundary

- Repo: `openclaw-mem` only.
- Advisory-only: no mutation apply, no publish/tag/push/merge, no Gateway/plugin/cron/model routing changes.
- Does not make L3/L4 auto-applyable.
- Does not treat sending or rendering a dossier as approval.

## Inputs

- Existing mutation plan JSON (`openclaw-mem.mutation.plan.v0`).
- Existing `allowed-root` validation boundary.
- Optional metadata: title, why-now, recommended action, operator target, do-nothing cost.

## Outputs / artifacts

- New governed command: `openclaw-mem governed advisory-dossier`.
- Machine JSON receipt containing risk, affected surfaces, approval requirement, rollback/verifier skeleton, and exact blocked apply-review decision.
- Optional Markdown dossier report for CK-facing approval.
- Unit/CLI tests including L3/L4 blocked counterfactuals.
- Public docs note.

## Invariants

- `writes_performed=false` always means no target mutation/application was performed.
- Optional JSON/Markdown dossier files are reported under `artifact_outputs`, not treated as target writes.
- `apply_review.writes_performed=false` always.
- L3/L4 always remain execution-blocked in this slice.
- Approval status is `approval_required`, never `approved`.
- Topology/config impact: unchanged.

## Verifier plan

- Unit tests for L3 and L4 dossier payloads.
- CLI test for Markdown output and JSON fields.
- Counterfactual: L4 with `--ck-approved` still emits `approval_required` and blocked apply-review due to `l3_l4_not_auto_applyable`.
- Targeted pytest for governed release and CLI tests.
- CLI smoke creating a sample L4 dossier artifact.

## Rollback

Revert this branch/commit. No runtime topology rollback is required because no live component is enabled.
