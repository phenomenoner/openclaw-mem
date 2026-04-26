# 櫻花刀舞 non-stop blade map — openclaw-mem backlog

Status: **ACTIVE / LOCAL ONLY**  
Date: 2026-04-26  
Authority: CK requested non-stop development for backlog items; do not push remote without explicit later approval.

## Target

Complete the selected `openclaw-mem` backlog locally, pass tests, merge to local `main`, install/enable locally, and update docs/skills. If restart is required, stop and ask CK.

## Queue

### Blade 0 — Runtime / routing preflight

- Confirm local repo state.
- Confirm Minion health.
- Establish QA Minion code-review lane for every implementation phase.
- Preserve local-only posture.

Acceptance:
- Minion health receipt captured.
- If durable Minion is unavailable, use inline/PGLite Minion-compatible review receipt and state that limitation.

### Blade 1 — #65 responsive episodic extraction

Implement `episodes extract-sessions --follow`.

Acceptance:
- One-shot behavior unchanged.
- Follow mode has bounded test hook (`--max-duration-seconds` or equivalent).
- JSON receipt reports iterations, scanned/written/skipped counts, duration, and stop reason.
- Tests cover one-shot parity and follow no-op/new-event behavior.
- QA Minion code review completed before integration.

### Blade 2 — #61 dataset snapshots + tags

Implement mem-engine dataset snapshot/tag safety net.

Acceptance:
- Snapshot create/list/restore or equivalent CLI/API exists.
- Restore is explicit and non-destructive by default.
- Receipts include dataset source, snapshot id/tag, counts, target.
- Tests prove snapshot -> mutate -> restore behavior.
- QA Minion code review completed before integration.

### Blade 3 — #67 WorkingSet multipass A/B isolated eval

Implement the internal multipass A/B eval harness described in `docs/specs/workingset-multipass-ab-eval-plan-v0.md`.

Acceptance:
- Isolated subject/driver/judge architecture or deterministic scaffolding exists.
- Supports A `workingSet=false` and B `workingSet=true` with same prompt sequence/model config.
- Captures repeated injection / dedupe / visible context telemetry.
- Produces run bundle (`RUN_META.json`, `CASE_MATRIX.md`, transcripts, telemetry, judge/summary where applicable).
- Tests cover deterministic bundle generation / telemetry fields.
- QA Minion code review completed before integration.

### Blade 4 — Docs / skills / roadmap / release hygiene

- Update docs and related skill/operator references.
- Preserve internal-only labeling where appropriate.
- Ensure public-facing docs do not overpromise internal eval plans.

Acceptance:
- Roadmap/spec links valid.
- MkDocs strict build passes.
- Relevant operator skill/docs updated if routing changed.

### Blade 5 — Full verification / local install enable / local main merge

- Run targeted tests, then broad test suite as practical.
- Merge implementation to local `main`.
- Install/enable locally.
- Stop and ask CK if restart is required.

Acceptance:
- Full verification receipt.
- Local install/enable receipt.
- Local git state reported.
- No remote push unless explicitly approved.

## Stop conditions

- Restart required.
- External push/publish/release needed.
- Auth/permission wall.
- Same root-cause failure twice.
- Minion QA lane cannot produce review receipts for a phase.
