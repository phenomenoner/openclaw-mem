# self-model sidecar productization slice receipt

Date: 2026-04-24
Status: shipped locally, verifier-backed
Topology: unchanged

## Change
Implemented the next productization slice for the continuity / self-model sidecar, covering CK's five requested upgrade areas while preserving the sidecar boundary:

1. claim lifecycle ledger
2. continuity mirror
3. adjudication rule table + negative fixture classes
4. golden continuity eval
5. release / rebind governance UX

## Claude second-brain correction
Claude reviewed the plan against `docs/specs/self-model-sidecar-endgame-architecture-v0.md` and flagged the main design risk: a real claim lifecycle graph should not become authoritative before adjudication is frozen.

Applied correction:
- the new `ledger` surface is a derived, read-only lifecycle view over current snapshot attachments + release receipts
- it is not a new source-of-truth graph
- adjudication rule-table and golden eval are now explicit product surfaces
- release/rebind UX remains proposal/review-first; applying still requires explicit `continuity release` receipts

## CLI surfaces added
- `openclaw-mem continuity ledger`
- `openclaw-mem continuity mirror`
- `openclaw-mem continuity rule-table`
- `openclaw-mem continuity golden-eval`
- `openclaw-mem continuity governance`

The compatibility alias `openclaw-mem self ...` receives the same surfaces.

## Domain outputs added
- `openclaw-mem.self-model.claim-ledger.v0`
- `openclaw-mem.self-model.mirror.v0`
- `openclaw-mem.self-model.adjudication-rule-table.v0`
- `openclaw-mem.self-model.golden-eval.v0`
- `openclaw-mem.self-model.governance-review.v0`

## Boundary kept true
- derived outputs remain `authoritative: false`
- no write-through into Store truth
- governance review is suggestion-only
- actual weaken / retire / rebind still goes through explicit release receipts
- claim ledger is rebuildable from snapshot + release history, not an independent truth store
- topology unchanged

## Verification
```bash
python3 -m unittest tests.test_self_model_sidecar -v
```

Result:
- 16 tests, all green

CLI smoke:
```bash
python3 -m openclaw_mem continuity rule-table --json
python3 -m openclaw_mem continuity current --limit 20 --persist --json
python3 -m openclaw_mem continuity mirror --snapshot <snapshot> --json
python3 -m openclaw_mem continuity golden-eval --snapshot <snapshot> --json
python3 -m openclaw_mem continuity governance --snapshot <snapshot> --json
```

Result:
- all five new schemas emitted valid JSON

## Honest remaining work
- The current `ledger` is a lifecycle view, not the full Layer 3 claim graph.
- Golden eval has a built-in starter set, but needs a stronger adversarial fixture corpus before it can be called a real benchmark.
- Mirror is JSON/operator-first; markdown/HTML rendering is the next product UX step.
- Governance review suggests actions but does not yet offer an interactive apply flow.

## Follow-up slice - mirror markdown + adversarial starter cases
Added after the initial productization slice:
- `continuity mirror --markdown` operator report renderer.
- Built-in adversarial starter cases for `golden-eval`:
  - no invented consciousness claim
  - no soul-like authority claim
  - prior-only claims must not be accepted

Verification:
```bash
python3 -m unittest tests.test_self_model_sidecar tests.test_json_contracts -v
```
Result: 24 tests OK.

CLI smoke:
- `continuity mirror --markdown` emitted a readable operator report with derived/non-authoritative warning.
- `continuity golden-eval` emitted 8 starter cases; current live-ish sample scored 4/8, correctly surfacing missing/evidence-thin continuity expectations rather than hiding them.

Remaining truth:
- governance suggestions are still noisy because pattern history is broad; next hardening should rank/de-duplicate operator-review actions before treating the mirror as showcase-grade.

## Follow-up slice - governance noise reduction
Added mirror-level ranking/de-duplication for governance suggestions:
- raw `intervention-report` remains broad and evidence-preserving
- `mirror` now shows top 8 ranked actions by actionability
- duplicate claim/mode pairs are collapsed
- markdown mirror includes raw/shown/suppressed counts

Smoke result on live-ish sample:
- before: 21 raw suggestions rendered directly
- after: 8 shown, 13 suppressed as lower-priority/noisy items

Verification:
```bash
python3 -m unittest tests.test_self_model_sidecar tests.test_json_contracts -v
```
Result: 24 tests OK.
