---
name: openclaw-mem-sync
description: >-
  Govern embedding refresh, episodic evidence synchronization, metadata
  writeback, and engine dataset snapshots. Use before or after bounded sync,
  reindex, migration, or writeback operations.
metadata:
  ring: 1
  surface: [cli, plugin]
  version: 2.0.0
  requires: [openclaw-mem-memory]
---

# Sync Governance

## Boundaries

- Keep episodic evidence distinct from durable facts.
- Refresh only the requested scope, field, model, and bounded limit.
- Snapshot engine datasets before mass writeback, reindex, migration, or checkout.
- Require receipts and explicit confirmation for destructive or active-dataset actions.
- Treat model/dimension and orphan-vector warnings as integrity issues to investigate.

## Operate

```bash
openclaw-mem episodes embed --scope <scope> --limit 500 --json
openclaw-mem episodes search <query> --scope <scope> --mode hybrid --trace --json
openclaw-mem embed --field both --limit 500 --json
openclaw-mem db info --json
openclaw-mem engine snapshot create --tag <tag> --reason <reason> --json
openclaw-mem writeback-lancedb --lancedb <path> --table <table> --dry-run --json
```

Use `OPENCLAW_MEM_EMBED_PROVIDER=local` only with the embed extra installed. Local and OpenAI model rows may coexist; query the same stored model deliberately.

## Verify

```bash
openclaw-mem db info --json
openclaw-mem doctor --json
python -m pytest tests/test_embedding_providers.py tests/test_embedding_integrity.py -q
```
