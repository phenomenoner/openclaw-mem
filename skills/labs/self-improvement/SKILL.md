---
name: openclaw-mem-self-improvement
description: >-
  Inspect experimental self-improvement consolidation surfaces. Use for
  read-only validation, goal readback, staged skill proposals, curator review,
  and system status.
metadata:
  ring: 2
  surface: [cli]
  version: 1.9.32
  requires: [openclaw-mem-memory]
---

# Self-improvement Lab

## Surfaces

```bash
openclaw-mem surface validate --inventory <inventory> --receipt <receipt> --json
openclaw-mem goal status --file <goal> --json
openclaw-mem goal pack --file <goal> --json
openclaw-mem skill-capture propose --text <proposal> --out <artifact> --json
openclaw-mem skill-curator review --skill-root <workspace>/skills --no-write --json
openclaw-mem mem-system status --json
```

Goal and system status are read-only. Curator review is report-only. Skill capture may write only an explicit staged proposal. These surfaces do not patch live skills, schedule cron, change gateway/plugin configuration, or enable auto-continuation. Higher-authority operations remain manual approval territory.

## Verify

```bash
openclaw-mem mem-system status --json
python -m pytest tests/test_self_improvement_surface.py tests/test_skill_capture.py -q
git diff --check
```
