# Pack recipes

Use Pack when the task needs a bounded working bundle rather than one fact.

```bash
openclaw-mem pack --query <query> --trace --json
openclaw-mem pack --query <query> --scope <project> --use-graph auto --trace --json
openclaw-mem pack --query <query> --tail-file <recent-context> --tail-budget-tokens 300 --trace --json
```

- Prefer `--scope <project>` for project work.
- Keep graph on `auto`; force `on` only for deliberate graph investigation.
- Reserve a protected tail for recent continuity instead of storing raw turns.
- Use compact sideband text for orientation, then rehydrate its raw artifact handle for exact claims.
- Keep citations and `recordRef` values in the delivered context.
- Treat timing, fallback, lane, and policy receipts as retrieval provenance.
