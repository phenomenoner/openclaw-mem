# Governed optimize assist lane

This is the bounded maintenance lane for `openclaw-mem` observation hygiene.

It is intentionally narrow:
- scout low-risk candidates
- require explicit judgment
- apply only whitelisted low-risk observation updates
- emit before/after + rollback receipts every run

## What it does

The lane runs this packet chain:

1. `openclaw-mem optimize evolution-review`
2. `openclaw-mem optimize governor-review`
3. `openclaw-mem optimize assist-apply`

The shipped write whitelist is currently limited to:
- `detail_json.lifecycle.stale_candidate`
- `detail_json.lifecycle.stale_reason_code`
- `detail_json.importance.score`
- `detail_json.importance.label`
- bounded `detail_json.optimization.assist` metadata

Current bounded low-risk families include:
- stale lifecycle marking
- bounded importance downshift
- score-label alignment with `delta = 0`

The candidate packets now also carry bounded classifier metadata:
- `risk_level` (`low | medium | high`)
- `risk_reasons[]`
- `auto_apply_eligible`

This metadata does not create a new write path by itself.
It exists so unattended low-risk promotion can be measured and fail closed later.

## Follow-up effect measurement

Phase 6 now starts with a read-only follow-up surface:

```bash
python -m openclaw_mem optimize effect-followup \
  --db /path/to/openclaw-mem.sqlite \
  --from-file /path/to/assist-effect.json \
  --json
```

This command:
- reads a prior `openclaw-mem.optimize.assist.effect-batch.v0` receipt
- compares baseline signals to current observation state + recent-use signals
- emits delayed `improved | neutral | regressed | insufficient_data` follow-up judgments
- performs **no writes**

## Verifier bundle

Phase 7 now starts with a read-only verifier surface:

```bash
python -m openclaw_mem optimize verifier-bundle \
  --db /path/to/openclaw-mem.sqlite \
  --run-dir ~/.openclaw/memory/openclaw-mem/optimize-assist \
  --json
```

This command:
- scans recent assist apply receipts
- checks effect-receipt completeness
- checks cap integrity against before receipts
- runs rollback replay simulation on a temporary DB clone when the current row state still matches the recorded after hashes
- emits a compact verifier bundle without mutating memory rows

## Challenger review

Phase 8 is now wired as a read-only challenger lane:

```bash
python -m openclaw_mem optimize challenger-review \
  --from-file /path/to/evolution.json \
  --json
```

This command:
- reads governed `evolution-review` output
- compares the current primary risk classification to a stricter shadow challenger policy
- emits disagreement receipts plus bounded disagreement clusters without changing governor or writer behavior
- keeps the challenger lane read-only while letting the controller require challenger agreement before promotion

The scheduled runner now also supports a bounded **quarantine/veto** posture:
- challenger disagreement can fail closed before `assist-apply`
- quarantine can block a candidate or an entire bounded family from the current run
- the filtered governor packet is written as `governor-filtered.json` for auditability

## Default posture

The recommended deployment posture is:
- **scheduled worker**
- **dry-run first**
- **separate from heartbeat/healthcheck lanes**
- **governor-gated only**

Do not treat this lane as a general memory editing loop.
It is a narrow hygiene lane with caps, receipts, and rollback.

## Scheduled runner

This repo ships a dedicated runner:

```bash
python tools/optimize_assist_runner.py --json
```

Default behavior:
- runs the full packet chain
- runs `challenger-review` on the same evolution packet before assist apply
- runs `verifier-bundle` after assist apply so promotion/watchdog gates can consume first-party verifier output
- keeps stale candidates and bounded importance adjustments as the approved low-risk action classes
- respects the packet classifier, so medium/high-risk candidates remain proposal-only even when approval flags are enabled
- runs `assist-apply` in **dry-run** mode unless `--allow-apply` is set
- writes runner packet artifacts under `~/.openclaw/memory/openclaw-mem/optimize-assist-runner/`
- persists controller state under `~/.openclaw/memory/openclaw-mem/optimize-assist-runner/controller-state.json`

### Controller state machine

The runner now supports a bounded controller lane:
- `dry_run`
- `canary_apply`
- `auto_low_risk`
- `paused_regression`

It also persists bounded family-level state:
- `stale_candidate`
- `importance_downshift`
- `score_label_alignment`

Families can now be independently enabled, disabled, or quarantined without code surgery.

If watchdog gates trip, the controller moves itself to `paused_regression` and future runs fail closed into dry-run posture until an operator explicitly changes mode.

### Promotion to unattended low-risk

You can now promote the lane into default unattended low-risk mode with an explicit promotion receipt:

```bash
python tools/optimize_assist_runner.py \
  --controller-mode canary_apply \
  --promotion-gate-receipt /path/to/promotion-gates.json \
  --promote-when-gates-green \
  --json
```

Expected promotion receipt keys:
- `manual_review_sample_precision`
- `repeated_miss_regression_pct`
- `rollback_replay_pass`

When all thresholds are green, the controller promotes its persisted next mode to `auto_low_risk`.
If `--challenger-require-agreement-for-promotion` is set, promotion also fails closed when the challenger lane reports disagreements above the configured threshold.

Promotion now prefers native verifier evidence from `verifier-bundle` when available, rather than relying only on operator-fed rollback receipts.

### Allow bounded apply

```bash
python tools/optimize_assist_runner.py --allow-apply --json
```

### Useful flags

- `--db /path/to/openclaw-mem.sqlite`
- `--runner-root ~/.openclaw/memory/openclaw-mem/optimize-assist-runner`
- `--operator openclaw-cron`
- `--scope team/alpha`
- `--limit 1000`
- `--stale-days 60`
- `--max-rows-per-run 5`
- `--max-rows-per-24h 20`
- `--max-importance-adjustments-per-run 3`
- `--max-importance-adjustments-per-24h 10`
- `--no-approve-importance`
- `--no-approve-stale`
- `--controller-mode canary_apply`
- `--challenger-policy-mode strict_v1`
- `--challenger-enforce-quarantine`
- `--challenger-require-agreement-for-promotion`
- `--challenger-max-disagreements-for-promotion 0`
- `--disable-family score_label_alignment`
- `--enable-family score_label_alignment`
- `--promotion-gate-receipt /path/to/promotion-gates.json`
- `--promote-when-gates-green`

## Near-ceiling posture review

Phase 11 now has a native read-only posture surface:

```bash
python -m openclaw_mem optimize posture-review \
  --runner-root ~/.openclaw/memory/openclaw-mem/optimize-assist-runner \
  --json
```

This command:
- reads controller state plus recent controller / verifier / challenger / assist receipts
- summarizes whether Phase 8, 9, 10 surfaces are actually live
- emits a bounded `near_ceiling_ready` verdict without changing memory state

## OpenClaw cron enablement

Use an isolated cron lane that runs exactly one `exec`.
Recommended message body:

```text
Run exactly one exec, then output ONLY NO_REPLY:

cd /opt/openclaw-mem && uv run --python 3.13 -- python tools/optimize_assist_runner.py --json
```

For bounded live writes, switch to:

```text
Run exactly one exec, then output ONLY NO_REPLY:

cd /opt/openclaw-mem && uv run --python 3.13 -- python tools/optimize_assist_runner.py --allow-apply --json
```

## Receipts

You should expect two layers of receipts:

### Runner artifacts
Under:
- `~/.openclaw/memory/openclaw-mem/optimize-assist-runner/...`

Artifacts include:
- `evolution.json`
- `governor.json`
- `governor-filtered.json`
- `challenger.json`
- `verifier.json`
- `assist-after.json`
- `assist-effect.json`

### Assist apply receipts
Under:
- `~/.openclaw/memory/openclaw-mem/optimize-assist/...`

Artifacts include:
- before receipt
- after receipt
- rollback artifact
- effect artifact / baseline receipt for later follow-up measurement

## Promotion checklist

Before removing dry-run:
- confirm packet counts are sane
- confirm governor approvals match expectation
- inspect assist receipts and rollback files
- confirm row/day caps fit your risk posture
- keep the job isolated from watchdog/read-only lanes

## What this lane is not

This lane does **not** authorize:
- prompt rewriting
- config mutation
- backend switching
- broad memory gardening
- cross-row merges
- autonomous high-risk changes

## Read next

- [Deployment guide](deployment.md)
- [Automation status](automation-status.md)
- [Self-optimizing memory loop](specs/self-optimizing-memory-loop-v0.md)
- [Assist-mode contract](specs/self-optimizing-memory-assist-mode-contract-v1.md)
