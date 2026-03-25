# Proof-first relaunch checklist

Purpose: one bounded operator checklist to verify relaunch readiness without expanding into GTM control or broad site rewrites.

Scope note: maintainer-facing release checklist in a public repo (governance artifact, not outward product copy).

Date executed: 2026-03-25 (PASS 4 release-candidate closure)

## 1) Public surface consistency

- [x] README presents a natural external product narrative without internal framework labels.
- [x] `docs/index.md` and `docs/about.md` mirror the same external-facing language and order.
- [x] Launch copy docs (`trust-aware-context-pack-copy-pack.md`, `github-repo-surface-consistency.md`, `release-surface-proof-pack-v0.md`) use the same core product wording.
- [x] Public copy does not expose internal framing formulas or backstage positioning labels.

Receipt:
- `README.md`, `docs/index.md`, `docs/about.md`, `docs/launch/trust-aware-context-pack-copy-pack.md`, `docs/launch/github-repo-surface-consistency.md`, `docs/launch/release-surface-proof-pack-v0.md`

## 1.5) Release-surface sync (headline / hero / onboarding)

- [x] Release-note opening paragraph follows the same story route and boundary posture.
- [x] README + docs home hero copy both use the same natural getting-started wording (local proof, sidecar default, optional engine).
- [x] Install-path quick-start decision guide uses the same outward-facing onboarding wording/order.

Receipt:
- `docs/launch/release-note-body-v0-final.md`, `README.md`, `docs/index.md`, `docs/install-modes.md`

## 2) Proof-first contract

- [x] Canonical proof link is present and prominent: `docs/showcase/trust-aware-context-pack-proof.md`.
- [x] Before/after metrics artifact is linked: `docs/showcase/artifacts/trust-aware-context-pack.metrics.json`.
- [x] Copy avoids overclaims (no “solves memory forever”, no “automatic perfect blocking”).

Receipt:
- `docs/launch/release-note-body-v0-final.md`, `docs/launch/trust-aware-context-pack-copy-pack.md`, `docs/showcase/trust-aware-context-pack-proof.md`

## 3) Plane and boundary integrity

- [x] Query plane is default.
- [x] Action plane is optional, recommendation-first, and write-gated.
- [x] KOL/GTM is explicitly linked-but-separate (no lane authority merge).
- [x] Graph/reference/knowledge-graph is framed as a flagship feature family, not universal schema.

Receipt:
- `README.md`, `docs/index.md`, `docs/about.md`, `docs/launch/release-note-body-v0-final.md`

## 4) Install and rollback clarity

- [x] Sidecar-first path remains explicit.
- [x] Mem-engine promotion is optional and later.
- [x] Rollback posture remains explicit in docs language.

Receipt:
- `README.md`, `docs/install-modes.md`, `docs/about.md`, `docs/launch/release-note-body-v0-final.md`

## 5) WAL-ready closure items for a docs pass

- [x] Lightweight consistency checks run (`git diff --check`, link/reference sanity).
- [x] Topology check stated explicitly (topology changed or unchanged).
- [x] Docs cold-lane ingest executed for changed operator-authored docs when applicable.
- [x] Durable note appended to workspace memory log for the pass.
- [x] Commit + push receipts recorded.

Receipts:
- Playbook repo carries the PASS 4 release-candidate closure receipt and sprint-truth update under the `projects/openclaw-mem/ops/releases/` and `projects/openclaw-mem/ops/sprints/` control surfaces.

## Out of scope (keep bounded)

- No live cron/job provisioning.
- No giant copy-polish marathon.
- No broad website implementation sprawl unless already pre-scoped elsewhere.
