---
name: openclaw-mem-dream-lite
description: >-
  Operate experimental Dream Lite planning, governed refresh canaries,
  rollback, and Director rehearsals. Use only for explicitly reviewed derived
  card maintenance.
metadata:
  ring: 2
  surface: [cli]
  version: 1.9.32
  requires: [openclaw-mem-memory]
---

# Dream Lite Lab

## Authority

- Keep `apply plan` and `apply verify` zero-write.
- Restrict `apply run` to one governor-approved `refresh_card` with witness, snapshots, TTL, rolling write caps, receipt, and rollback.
- Keep `compile_new_card` proposal-only.
- Treat Director observe, stage, checkpoint, and apply outputs as untrusted rehearsal artifacts.
- Never let Director rehearsal canonize authority files or claim live mutation.

```bash
openclaw-mem dream-lite apply plan --json
openclaw-mem dream-lite apply verify --receipt <receipt> --json
openclaw-mem dream-lite apply rollback --receipt <receipt> --json
openclaw-mem dream-lite director observe --json
openclaw-mem dream-lite director checkpoint --json
```

Human notifications should summarize suggestions, recommended handling with reasons, choices, and the run window. Keep ordinary no-op and rehearsal-only runs silent.

## Verify

```bash
openclaw-mem dream-lite apply plan --json
python -m pytest tests/test_cli_surface_lock.py -q
git diff --check
```
