# Proof-first relaunch checklist

Purpose: one bounded operator checklist to verify relaunch readiness without expanding into GTM control or broad site rewrites.

## 1) Narrative lock (dream → concept → demo → how-to)

- [ ] README states the story path in this order.
- [ ] `docs/index.md` and `docs/about.md` mirror the same order.
- [ ] Launch copy docs (`trust-aware-context-pack-copy-pack.md`, `github-repo-surface-consistency.md`, `release-surface-proof-pack-v0.md`) use the same wedge wording.

## 1.5) Release-surface sync (headline / hero / CTA)

- [ ] Release-note opening paragraph follows the same story route and boundary posture.
- [ ] README + docs home hero copy both point at the same CTA ladder (proof → sidecar → engine).
- [ ] Install-path fast decision shortcut uses the same CTA wording/order.

## 2) Proof-first contract

- [ ] Canonical proof link is present and prominent: `docs/showcase/trust-aware-context-pack-proof.md`.
- [ ] Before/after metrics artifact is linked: `docs/showcase/artifacts/trust-aware-context-pack.metrics.json`.
- [ ] Copy avoids overclaims (no “solves memory forever”, no “automatic perfect blocking”).

## 3) Plane and boundary integrity

- [ ] Query plane is default.
- [ ] Action plane is optional, recommendation-first, and write-gated.
- [ ] KOL/GTM is explicitly linked-but-separate (no lane authority merge).
- [ ] Graph/reference/knowledge-graph is framed as a flagship feature family, not universal schema.

## 4) Install and rollback clarity

- [ ] Sidecar-first path remains explicit.
- [ ] Mem-engine promotion is optional and later.
- [ ] Rollback posture remains explicit in docs language.

## 5) WAL-ready closure items for a docs pass

- [ ] Lightweight consistency checks run (`git diff --check`, link/reference sanity).
- [ ] Topology check stated explicitly (topology changed or unchanged).
- [ ] Docs cold-lane ingest executed for changed operator-authored docs when applicable.
- [ ] Durable note appended to workspace memory log for the pass.
- [ ] Commit + push receipts recorded.

## Out of scope (keep bounded)

- No live cron/job provisioning.
- No giant copy-polish marathon.
- No broad website implementation sprawl unless already pre-scoped elsewhere.