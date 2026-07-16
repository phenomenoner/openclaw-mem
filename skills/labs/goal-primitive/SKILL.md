---
name: openclaw-mem-goal-primitive
description: >-
  Operate the experimental read-only goal primitive and surface validation.
  Use for normalized goal status, compact goal packs, and receipt validation,
  not continuation or autonomous mutation.
metadata:
  ring: 2
  surface: [cli]
  version: 1.9.32
  requires: [openclaw-mem-memory]
---

# Goal Primitive Lab

Keep this pilot read-only. Explicit `--out` receipt files are the only permitted writes. Goal status is not an auto-continuation loop.

```bash
openclaw-mem surface validate --inventory <inventory> --json
openclaw-mem surface validate --inventory <inventory> --receipt <receipt> --json
openclaw-mem goal status --file <goal> --json
openclaw-mem goal pack --file <goal> --json
```

Protected surfaces require sufficient write authority before any future curator applies mutation. Prefer a context Pack seam for compaction-safe injection rather than pasting goal guidance into every prompt.

## Verify

```bash
openclaw-mem goal status --file <goal> --json
python -m pytest tests/test_goal_primitive.py tests/test_self_improvement_surface.py -q
git diff --check
```
