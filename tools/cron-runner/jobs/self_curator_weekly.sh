#!/usr/bin/env bash
set -euo pipefail
/root/.openclaw/workspace/tools/cron-runner/lib/run_job.sh self_curator_weekly \
  python3 /root/.openclaw/workspace/openclaw-mem/tools/self_curator_controller.py \
    --repo /root/.openclaw/workspace/openclaw-mem \
    --workspace-root /root/.openclaw/workspace \
    --skill-root /root/.openclaw/workspace/skills \
    --out-root /root/.openclaw/workspace/.state/self-curator/controller-runs \
    --mode unattended_apply \
    --max-mutations 5 \
    --cron-output
