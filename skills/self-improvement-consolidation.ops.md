# self-improvement-consolidation.ops

Use for operating the OpenClaw Mem self-improvement consolidation surfaces.

## Surfaces

Read-only / report-only / staged-only commands:

```bash
openclaw-mem surface validate --inventory surfaces.json --receipt receipt.json --json
openclaw-mem goal status --file goal.json --json
openclaw-mem goal pack --file goal.json --json
openclaw-mem skill-capture propose --text "..." --out proposal.json --json
openclaw-mem skill-curator review --skill-root skills --json
openclaw-mem mem-system status --json
```

## Authority rules

- `goal status`, `goal pack`, and `mem-system status` are read-only.
- `skill-curator review` is non-mutating report-only: it may write review JSON/Markdown artifacts under `--out-root`, or payload-only with `--no-write`.
- `skill-capture propose` may write only an explicit L1 staged proposal artifact.
- No command in slices 2–5 patches live skills, schedules cron, changes gateway/plugin config, or enables auto-continuation.
- L3/L4 surfaces remain manual/CK approval territory.

## Verifier posture

Before claiming a slice is installed:

1. Run targeted pytest.
2. Run CLI smoke for every new command.
3. Run MkDocs strict build for public docs.
4. Run public-facing second-brain review before public push.
5. Run local editable install smoke.
6. Write WAL with topology impact and rollback.
