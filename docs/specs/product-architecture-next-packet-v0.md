# Product / architecture next packet v0

Status: **PLANNING**  
Date: 2026-04-26  
Scope: `openclaw-mem` product planning + senior architecture sequencing.

This packet turns the current open-issue / roadmap surface into a small execution sequence. It is planning only. It does not change live OpenClaw config, memory slots, cron jobs, or package releases.

## Verdict

The next best move is not another broad architecture expansion. The product is already strong on advanced surfaces. The next slices should make the operator loop feel faster, safer, and easier to ship:

1. responsive episodic extraction (`--follow`)
2. dataset snapshot safety net
3. smaller / more selective WorkingSet before another A/B
4. release/install hygiene as a supporting lane

Graph/topology and compiled synthesis remain valuable, but they should stay behind governance gates and should not displace the three product-facing gaps above.

## Strategic sequence

### Slice 1 — responsive episodic extraction

Issue: `#65 episodes extract-sessions: add --follow (responsive extract)`

Why first:
- Directly improves the demo/operator feel: capture can react without waiting for cron cadence.
- Low architectural risk if implemented as an additive loop around existing extraction.
- Gives better receipts for memory freshness without promoting heavier autonomy.

Acceptance criteria:
- `episodes extract-sessions --follow` exists with bounded polling / idle behavior.
- Existing one-shot extraction behavior is unchanged when `--follow` is absent.
- JSON receipt reports iterations, sessions scanned, events written/skipped, duration, and stop reason.
- Follow mode has a clear stop mechanism / max duration option for tests and scripts.
- Tests cover one-shot parity, follow-loop no-op, and follow-loop new-session detection.

Guardrails:
- Do not require daemonization in the first slice.
- Do not couple this to live cron changes.
- Do not widen capture policy beyond the current sanitation / allowlist rules.

### Slice 2 — mem-engine dataset snapshot safety net

Issue: `#61 Mem Engine dataset snapshots + tags`

Why second:
- It is the safety belt before stronger rollout and larger automated write paths.
- Slot-level rollback exists, but dataset-level rollback is still the operator-facing recovery primitive people expect.

Acceptance criteria:
- Snapshot command creates immutable dataset snapshot metadata with tag support.
- Restore path is explicit and non-destructive by default.
- Receipts include source dataset id/path, snapshot id/tag, counts, and restore target.
- Tests prove snapshot -> mutate -> restore can recover expected records.

Guardrails:
- No silent overwrite of the active dataset.
- Keep snapshot storage local-first and inspectable.
- Do not make snapshots a prerequisite for simple sidecar use.

### Slice 3 — WorkingSet selectivity before re-running A/B

Issue: `#67 workingSet A/B: no observed quality lift yet; consistent context-pressure cost`
Internal eval plan: [WorkingSet multipass A/B eval plan v0 →](workingset-multipass-ab-eval-plan-v0.md)

Why third:
- Current evidence says WorkingSet adds context pressure without visible quality lift.
- The right response is not deletion; it is making the feature smaller, more selective, and easier to turn off.

Acceptance criteria:
- WorkingSet remains disabled or conservative by default unless a stronger win case is demonstrated.
- Candidate selection is capped by tighter relevance / freshness / task-fit gates.
- Receipts expose why each WorkingSet item was included and what was excluded by budget.
- Re-run A/B only after the backbone is materially smaller and the multipass eval can measure repeated-context buildup across turns.

Guardrails:
- Do not let WorkingSet become a second memory owner.
- Preserve Store / Pack / Observe split: Store owns durable records, Pack owns bounded assembly, Observe owns receipts.
- Do not judge WorkingSet on single-turn quality alone; multi-turn dedupe / compression / topic-switch behavior is part of the feature boundary.

### Supporting lane — release / install hygiene

Why support, not mainline:
- Reproducibility is important, but it does not beat the product gates above.
- Treat release hygiene as a closure requirement for shippable slices.

Checklist:
- Keep versions aligned across Python package and plugin manifests.
- Update `CHANGELOG.md` when cutting a release.
- If dependency resolution changes, update and commit `uv.lock`.
- Validate locked sync for runtime and docs extras before tagging.

## Explicit deferrals

### Defer broad topology automation

Keep topology auto-extract valuable but bounded:
- Good next shape: deterministic seed generation + diff receipts.
- Not next: making auto topology overwrite curated truth or become a competing source of truth.

### Defer stronger compiled synthesis apply

Compiled synthesis is useful as a recommendation/apply assist, but it should remain review-gated until:
- provenance coverage is complete enough to explain why a card is safe to apply
- rollback path is obvious
- tests prove it cannot silently erase operator-authored nuance

### Defer broad readonly-lane productization from this repo

Read-only enforcement is an OpenClaw ops/runtime concern. `openclaw-mem` can emit receipts and avoid writes, but OS/tool policy enforcement belongs in OpenClaw/operator infrastructure.

## Architecture invariants

- Sidecar-first. Optional memory slot ownership must remain reversible.
- Local-first data and receipts.
- Fail-open reads; no memory helper should break the agent loop.
- Non-destructive writes; never overwrite operator-authored fields silently.
- Store / Pack / Observe split remains canonical.
- Graph/topology caches are derived and rebuildable, not primary truth.
- Every automation path has receipts that an operator can grep, diff, and roll back.

## High-confidence next implementation packet

Title: `episodes extract-sessions --follow` bounded follow mode

Worker contract:
1. Inspect current `episodes extract-sessions` command implementation and tests.
2. Add `--follow`, `--interval-seconds`, and `--max-duration-seconds` or equivalent bounded test hook.
3. Preserve one-shot default behavior exactly.
4. Emit structured JSON receipt for follow mode.
5. Add tests for:
   - one-shot parity
   - no-op follow loop exits via max duration
   - follow sees a newly available session/event without duplicate writes
6. Update CLI docs / README command examples if the command is user-facing there.

Verifier:
- targeted unit tests for episodes extraction
- `uv run pytest` for the affected test module(s)
- docs build only if docs navigation or rendered examples change

Rollback:
- revert the follow-mode patch; existing one-shot extraction remains the stable path.
