# Self Curator controller / autonomy receipt

Date: 2026-05-02

## Changed truth

Self Curator now has an autonomy controller for **unattended apply / 事後報備制**.

Within the current low-risk envelope, the controller may apply first, then report what changed. CK/operator can keep the mutation or use the apply receipt to roll it back.

The autonomy loop is:

```text
review -> plan -> policy -> checkpoint -> apply -> verify -> report -> rollback if verify fails or operator requests
```

## Controller scope

The scheduled controller currently applies only one low-risk mutation family:

```text
skills/<name>/.curator-lifecycle.json
```

This writes lifecycle sidecar metadata for reviewed skills. It does not rewrite `SKILL.md` content in scheduled mode yet, even though the lower-level apply engine supports broader patch/write/move/archive/frontmatter operations.

## CLI / wrapper

Supported controller modes today: `dry_run` and `unattended_apply`. `auto_low_risk` is intentionally not exposed until a later policy upgrade.

Manual controller:

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
python3 /root/.openclaw/workspace/openclaw-mem/tools/self_curator_controller.py --mode unattended_apply --cron-output
```

Stable repo cron job script:

```text
/root/.openclaw/workspace/openclaw-mem/tools/cron-runner/jobs/self_curator_weekly.sh
```

Installed cron-runner script path:

```text
/root/.openclaw/workspace/tools/cron-runner/jobs/self_curator_weekly.sh
```

## Artifacts per run

```text
/root/.openclaw/workspace/.state/self-curator/controller-runs/<run-id>/
├── review.json
├── plan.json
├── policy.json
├── REPORT.md
├── controller-receipt.json
└── apply/
    ├── apply-receipt.json
    └── apply.diff
```

If verification fails, rollback is executed and a rollback receipt is emitted.

## Verification receipts

```text
uv run -- python -m py_compile openclaw_mem/self_curator.py openclaw_mem/cli.py tools/self_curator_controller.py
uv run -- python -m unittest tests.test_self_curator -q
```

Result:

```text
Ran 15 tests
OK
```

Wrapper smoke with synthetic workspace:

- `python3 tools/self_curator_controller.py ... --mode unattended_apply --cron-output`
- emitted controller receipt
- wrote `.curator-lifecycle.json`
- verify returned `ok=true`

## Cron posture

Self Curator must run via a separate cron job. It is not heartbeat. Heartbeat remains health/alert only.

Recommended cadence: weekly, unattended apply mode. Cron output is `NO_REPLY` on no-op and `NEEDS_CK` with report/rollback paths when files changed.

## Rollback

Use the apply receipt from the controller run:

```bash
uv run openclaw-mem self-curator rollback --receipt <apply-receipt.json> --json
```

## Topology delta

Changed once cron is installed: one dedicated Self Curator weekly cron job.
No gateway config or heartbeat topology changes.

## Final closure update

QA attempts:

- Full controller QA timed out; no pass verdict was accepted from the timeout.
- Narrow QA timed out; no pass verdict was accepted from the timeout.
- Ultra-short diff QA returned must-fix findings for operator surface clarity; fixes applied:
  - renamed mode to `unattended_apply` everywhere;
  - removed exposed `auto_low_risk` mode until a later policy upgrade;
  - made README/skill cron commands absolute and explicit;
  - verified repo wrapper and installed cron-runner script use `/root/.openclaw/workspace` as workspace root and `/root/.openclaw/workspace/skills` as skill root.

Final verification:

```text
uv run -- python -m py_compile openclaw_mem/self_curator.py openclaw_mem/cli.py tools/self_curator_controller.py
uv run -- python -m unittest tests.test_self_curator -q
```

Result:

```text
Ran 16 tests
OK
```

Controller output smoke:

- dry run: `NO_REPLY`
- first unattended apply on fixture: `NEEDS_CK ... changed 1 file(s) ... report=... rollback=...`
- repeat unattended apply on same fixture: `NO_REPLY` because existing sidecar is skipped to avoid timestamp churn.

Live canary:

- Ran `python3 /root/.openclaw/workspace/openclaw-mem/tools/self_curator_controller.py --mode unattended_apply --cron-output`
- Result: created 5 real skill lifecycle sidecars under `/root/.openclaw/workspace/skills/*/.curator-lifecycle.json`.
- Report: `/root/.openclaw/workspace/.state/self-curator/controller-runs/controller-20260502-123759/REPORT.md`
- Rollback receipt path: `/root/.openclaw/workspace/.state/self-curator/controller-runs/controller-20260502-123759/apply/apply-receipt.json`

Cron install readback:

```text
42 10 * * 6 /root/.openclaw/workspace/tools/cron-runner/jobs/self_curator_weekly.sh
```

Supercronic was preflight-tested with `-test`, then restarted to load the updated crontab:

```text
old_pid=1363
new_pid=11730
```
