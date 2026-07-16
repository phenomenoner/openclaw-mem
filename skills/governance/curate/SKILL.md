---
name: openclaw-mem-curate
description: >-
  Govern memory, episode, skill, and fact lifecycle maintenance through the
  unified curate scan, review, apply, verify, and rollback verbs.
metadata:
  ring: 1
  surface: [cli]
  version: 1.9.32
  requires: [openclaw-mem-memory]
---

# Curate Governance

Use `scan → review → apply → verify → rollback` as the explicit governed loop. Every wrapper preserves the complete engine receipt in `inner`.

## Authority

- Scout with zero-write review before judgment.
- Keep low-risk unattended mutation within the explicit whitelist and mutation cap.
- Report post-hoc apply with exact changed paths and rollback receipt.
- Do not merge scout, governor, and writer authority into one hidden step.
- Run scheduled curation separately from heartbeat health checks.

## Operate by verb

```bash
openclaw-mem curate scan --target memory --json
openclaw-mem curate scan --target episodes --json
openclaw-mem curate scan --target skills --skill-root <workspace>/skills --json
openclaw-mem curate scan --target facts --source-root <workspace> --json
openclaw-mem curate review --target memory --from-file <recommendation.json> --json
openclaw-mem curate apply --target memory --from-file <governor.json> --json
openclaw-mem curate verify --target memory --run-dir <receipt-dir> --json
openclaw-mem curate rollback --target memory --receipt <rollback.json> --json
```

Skill mutation remains checkpointed and whitelist-only: pass an explicit self-curator plan to `curate apply --target skills --plan <plan.json>`. Unsupported verb-target pairs return stable zero-write receipts.

See [legacy commands](references/legacy-commands.md) when maintaining older automation. Aliases remain callable and emit deprecation guidance; do not remove them during migration.

## Verify

```bash
openclaw-mem curate scan --target skills --skill-root <workspace>/skills --json
python -m pytest tests/test_self_curator.py -q
git diff --check
```
