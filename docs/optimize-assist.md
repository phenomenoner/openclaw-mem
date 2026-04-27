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
- `detail_json.lifecycle.soft_archive_candidate`
- `detail_json.lifecycle.archived_at`
- `detail_json.lifecycle.archive_reason_code`
- `detail_json.importance.score`
- `detail_json.importance.label`
- bounded `detail_json.optimization.assist` metadata

Current bounded low-risk families include:
- stale lifecycle marking
- governed soft-archive lifecycle marking (`set_soft_archive_candidate`, explicit governor flag required)
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
- checks no-hard-delete posture via before/after observation row-count snapshots
- runs rollback replay simulation on a temporary DB clone when the current row state still matches the recorded after hashes
- reports per-action family accounting (including `set_soft_archive_candidate`) in verifier summary
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
- `soft_archive_candidate`
- `importance_downshift`
- `score_label_alignment`

Families can now be independently enabled, disabled, or quarantined without code surgery.

If watchdog gates trip, the controller moves itself to `paused_regression` and future runs fail closed into dry-run posture until an operator explicitly changes mode.

### Promotion to unattended low-risk

You can now promote the lane into default unattended low-risk mode with native in-run promotion truth:

```bash
python tools/optimize_assist_runner.py \
  --controller-mode canary_apply \
  --importance-drift-profile strict \
  --promote-when-gates-green \
  --promotion-gate-receipt /path/to/emitted-promotion-gates.json \
  --json
```

The runner now computes promotion metrics from first-party receipts produced in the same control loop, including:
- native effect precision proxy from recent effect receipts
- native regression-rate percentage from recent effect receipts
- `rollback_replay_pass` from `verifier-bundle`
- challenger agreement status when challenger agreement is required
- read-only `importance_drift` posture via `importance_drift_policy` from the same evolution packet
- bounded historical baseline evidence from recent controller receipts (`importance_drift_gate.baseline_comparator`)

`--promotion-gate-receipt` is now an **output path only**.
It emits the runner-computed promotion-gate artifact and is no longer accepted as authoritative input.

When all thresholds are green, the controller promotes its persisted next mode to `auto_low_risk`.
If `--challenger-require-agreement-for-promotion` is set, promotion also fails closed when the challenger lane reports disagreements above the configured threshold.
If importance-drift policy is not acceptable (for example high-risk under-label detections or mismatch/missing rates above thresholds), promotion fails closed with `importance_drift_policy_hold` and receipts carry the policy card under `promotion_gates.importance_drift_gate.policy_card`.
When baseline evidence is sufficient, the promotion receipt also classifies drift as transient (`transient_spike_detected`) vs persistent (`persistent_drift_detected`).

### Importance-drift policy card (proposal-only)

`optimize review` now emits a deterministic read-only policy card:
- path: `signals.importance_drift.policy_card`
- kind: `openclaw-mem.optimize.importance-drift-policy-card.v0`
- posture: `mode=proposal_only_read_only`, `query_only_enforced=true`, `writes_performed=0`
- profile selection: `--importance-drift-profile strict|balanced|lenient` (default: `strict`)

`optimize evolution-review` mirrors the same card at `importance_drift_policy`, and text renderers show one compact line:
- `importance_drift_gate=<accept|hold> acceptable=<true|false> rows=<n> profile=<name>`

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
- `--importance-drift-profile strict`
- `--importance-drift-baseline-limit 6`
- `--importance-drift-baseline-min-samples 3`
- `--importance-drift-persistent-hold-rate 0.6`
- `--max-rows-per-run 5`
- `--max-rows-per-24h 20`
- `--max-importance-adjustments-per-run 3`
- `--max-importance-adjustments-per-24h 10`
- `--no-approve-importance`
- `--no-approve-stale`
- `--approve-soft-archive`
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
- verifies recent importance-drift gate health from controller promotion receipts, including profile/baseline metadata and persistent-drift counters
- emits a bounded `near_ceiling_ready` verdict without changing memory state

## Canary advisory report

Canary cron can now end with a read-only advisory report:

```bash
python -m openclaw_mem optimize canary-advisory \
  --posture-file /path/to/posture.json \
  --verifier-file /path/to/verifier.json \
  --json
```

Or, when a runner root carries `posture.json` and recent `verifier.json` receipts:

```bash
python -m openclaw_mem optimize canary-advisory \
  --runner-root ~/.openclaw/memory/openclaw-mem/optimize-assist-runner \
  --json
```

The report emits `openclaw-mem.optimize.canary-advisory.v0` with `overall_status` plus per-feature decisions for:
- `soft_archive_canary`
- `lifecycle_mvp`
- `optimizer_gates`

Statuses are `can_enable`, `monitor_only`, or `not_ready`, each with deterministic reasons and evidence refs. The command performs no writes, keeps Working Set frozen/default-off, and treats hard delete as forbidden.

## OpenClaw cron enablement

Use an isolated cron lane that runs exactly one `exec`.
Recommended message body:

```text
Run exactly one exec, then output ONLY NO_REPLY:

cd /opt/openclaw-mem && uv run --python 3.13 -- python tools/optimize_assist_runner.py --json
```

For the new controller/challenger-gated dry-run posture, prefer this packet body instead:

```text
Run exactly one exec, then output ONLY NO_REPLY:

cd /opt/openclaw-mem && uv run --python 3.13 -- python tools/optimize_assist_runner.py --controller-mode dry_run --challenger-enforce-quarantine --challenger-require-agreement-for-promotion --challenger-max-disagreements-for-promotion 0 --json
```

Ready-to-paste snippet:
- `docs/snippets/openclaw-cron.optimize-assist-controller-dry-run.json`

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
