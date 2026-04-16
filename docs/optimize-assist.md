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
- keeps stale candidates and bounded importance adjustments as the approved low-risk action classes
- runs `assist-apply` in **dry-run** mode unless `--allow-apply` is set
- writes runner packet artifacts under `~/.openclaw/memory/openclaw-mem/optimize-assist-runner/`

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
- `--no-approve-importance`
- `--no-approve-stale`

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
