# Post-Sakura follow-up queue — capsule restore line

Date: 2026-03-30
Scope: work intentionally left outside the bounded Sakura restore slice.

## 1) Live-target apply governance policy (sprint/mandate)
- Define explicit authority + approvals for any live target restore semantics.
- Require operator confirmation surfaces (who/why/when) and policy receipts.
- Add policy tests for deny-by-default behavior in unattended lanes.

## 2) Cross-store migration contract (slow-cook)
- Design canonical mapping/versioned adapters for schema drift between stores.
- Add deterministic migration-plan dry-run with row-level impact receipts.
- Include rollback semantics per migration class before enabling apply.

## 3) Merge/overwrite semantics (slow-cook)
- Define conflict-resolution policy families (append/replace/merge-by-key).
- Add explicit, testable non-default flags and deny ambiguous merges.
- Gate each mode behind separate verifier suites and risk labels.

## 4) Artifact confidentiality lane (slow-cook)
- Add encryption/signing design for canonical artifacts + key management model.
- Keep this out of default restore path until operator UX + key rotation is proven.

## 5) Recovery drill operations cadence (sprint)
- Standardize periodic isolated replay drills (schedule + success SLO + expiry criteria).
- Capture drill receipts in operator runbook artifacts for audit continuity.
- Add stale-drill alerting if cadence misses threshold.

## 6) Long-horizon operator workflow pack (mandate)
- End-to-end workflow docs for export → transfer → isolated restore → verify → rollback drill.
- Include escalation/incident paths and explicit stop conditions.
- Add CI smoke harness that replays canonical fixtures in disposable targets.
