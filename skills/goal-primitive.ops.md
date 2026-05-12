# goal-primitive.ops

Use when operating the read-only OpenClaw Mem goal primitive pilot.

## Purpose

The goal primitive is the first low-risk product slice of the OpenClaw self-improvement consolidation plan. It provides status/readback and validation before any continuation runtime or skill-learning loop is allowed to mutate durable state.

## Commands

Validate a surface inventory or receipt:

```bash
openclaw-mem surface validate --inventory surfaces.json --json
openclaw-mem surface validate --inventory surfaces.json --receipt receipt.json --out validation.json --json
```

Read goal status:

```bash
openclaw-mem goal status --file goal.json --json
openclaw-mem goal status --file goal.json --out goal-status.json --json
```

## Rules

- Treat this pilot as read-only. `writes_performed` must remain `false` unless the only write is an explicit `--out` receipt.
- Protected surfaces require sufficient write authority before any future curator can apply mutations.
- For compaction-safe injection, prefer a context engine/pack seam. Do not paste all goal guidance into every system prompt.
- `goal status` is not an auto-continuation loop. It only normalizes and verifies the current goal receipt.

## Closeout checks

- Unit tests pass for surface validation and goal status.
- CLI smoke passes through the installed `openclaw-mem` command.
- Public docs are reviewed before push.
- WAL/receipt names the exact commands and artifacts.
