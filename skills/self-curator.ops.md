# Self Curator ops skill

Use when operating or explaining `openclaw-mem self-curator` autonomy.

## Contract

Self Curator is an apply-capable lifecycle controller:

```text
review -> plan -> policy -> checkpoint -> apply -> verify -> report -> rollback if requested or verify fails
```

Unattended apply means **事後報備制**: within the whitelisted low-risk envelope, the controller may apply first, then report what changed. CK/operator can roll back from the apply receipt if the change is undesirable.

## Allowed unattended low-risk family today

The controller writes skill lifecycle sidecar metadata files:

```text
skills/<name>/.curator-lifecycle.json
```

It does not rewrite `SKILL.md` content in the controller path yet. The lower-level apply engine supports broader `replace_text`, `write_file`, `move_file`, `archive_file`, and `set_frontmatter_field` plans, but scheduled controller use should stay on the whitelisted sidecar metadata family until a later policy upgrade.

## Commands

Supported controller modes today: `dry_run` and `unattended_apply`. Do not use or document `auto_low_risk` until the policy engine is explicitly upgraded.

Manual controller run:

```bash
uv run openclaw-mem self-curator controller \
  --skill-root /root/.openclaw/workspace/skills \
  --workspace-root /root/.openclaw/workspace \
  --out-root /root/.openclaw/workspace/.state/self-curator/controller-runs \
  --mode unattended_apply \
  --max-mutations 5 \
  --json
```

Cron wrapper:

```bash
python3 /root/.openclaw/workspace/openclaw-mem/tools/self_curator_controller.py \
  --repo /root/.openclaw/workspace/openclaw-mem \
  --workspace-root /root/.openclaw/workspace \
  --skill-root /root/.openclaw/workspace/skills \
  --out-root /root/.openclaw/workspace/.state/self-curator/controller-runs \
  --mode unattended_apply \
  --max-mutations 5 \
  --cron-output
```

Cron output contract:
- `NO_REPLY` when no mutation is applied.
- `NEEDS_CK: ... report=<REPORT.md> rollback=<apply-receipt.json>` when unattended apply changed files.

## Artifacts

Each run writes:

```text
.state/self-curator/controller-runs/<run-id>/
├── review.json
├── plan.json
├── policy.json
├── REPORT.md
├── controller-receipt.json
└── apply/
    ├── apply-receipt.json
    └── apply.diff
```

If verify fails, rollback receipt is also written.

## Rollback

Use the receipt path from `controller-receipt.json`:

```bash
uv run openclaw-mem self-curator rollback --receipt <apply-receipt.json> --json
```

## Cron posture

Self Curator must use a separate cron job, not heartbeat. Heartbeat remains health/alert only.

Recommended cadence: weekly. Use `unattended_apply` mode for 事後報備; use `dry_run` only for debugging or regression pauses. The cron entry belongs in `/root/.openclaw/workspace/tools/cron-runner/crontab/openclaw-mem.crontab`, not in heartbeat.
