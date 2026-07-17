---
name: openclaw-mem-gbrain-sidecar
description: >-
  Operate the experimental GBrain lookup, restricted helper-job, and governed
  refresh-canary lanes. Use only when GBrain integration is explicitly enabled.
metadata:
  ring: 2
  surface: [cli]
  version: 2.0.0
  requires: [openclaw-mem-memory]
---

# GBrain Sidecar Lab

GBrain is a retrieval/helper substrate, not a backend replacement, second truth store, broad jobs runner, or `gbrainMirror`.

## Surfaces

```bash
openclaw-mem gbrain-sidecar consult --query <query> --json
openclaw-mem gbrain-sidecar jobs-smoke --json
openclaw-mem gbrain-sidecar jobs-list --json
openclaw-mem gbrain-sidecar recommend-refresh --json
openclaw-mem gbrain-sidecar refresh-canary --json
```

Only the `embed` helper family is allowed. Persistent workers need PostgreSQL-backed GBrain; treat pglite as bounded, non-daemon operation. Keep OpenClaw Mem as Store/Pack/Observe governor and mem-engine as durable slot owner. Pack-side failures fail open unless the command contract states otherwise.

## Verify

```bash
openclaw-mem gbrain-sidecar jobs-smoke --json
python -m pytest tests/test_gbrain_sidecar.py -q
git diff --check
```
