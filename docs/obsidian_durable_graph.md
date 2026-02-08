# Obsidian durable-memory graph (Hub/Spoke)

This doc describes a **clean + link-rich** way to browse and recall *durable* memories using Obsidian, without polluting the vault with raw tool-result logs.

## Philosophy

### Separate "observations" from "durable memory"

- **Observations**: high-volume, noisy, audit logs (tool calls/results, cron outputs, etc.)
  - Great for debugging and traceability.
  - Not ideal for human navigation.

- **Durable memories**: low-volume, human-approved (or explicitly stored) facts/preferences/decisions/tasks/entities.
  - These are what should influence the agent long-term.

### Why structure helps *agent recall*

OpenClaw recall is primarily retrieval over text chunks (vector + keyword/FTS). Obsidian links are not "graph algorithms" for the agent, but a structured, canonical naming scheme helps retrieval because it:

- increases **keyword hit-rate** (stable canonical titles)
- improves **embedding quality** (shorter, single-topic notes)
- creates a human-maintained **index** (Hub notes act like a curated reranker)

## Implementation (in `openclaw-mem`)

### 1) Durable memory source

`openclaw-mem store` appends to:

- `<workspace>/memory/YYYY-MM-DD.md`

Lines look like:

- `- [PREFERENCE] Prefer concise bullet-point summaries (importance: 0.9)`

### 2) Build the graph (deterministic)

Run:

```bash
cd /home/agent/.openclaw/workspace/openclaw-mem
uv run --python 3.13 -- python scripts/durable_structure.py --workspace /home/agent/.openclaw/workspace
```

This generates:

- `<workspace>/memory/durable/DurableHub.md`
- `<workspace>/memory/durable/Category-<cat>.md`
- `<workspace>/memory/durable/items/<YYYY-MM-DD>/<id>.md`

Only durable memories are included (no raw observations).

### 3) Mirror to Obsidian vault

Use the daily export script to copy artifacts into the vault (see `scripts/obsidian_daily_export.sh`).

## Recommended workflow

1. Human approves durable memories (Obsidian approval gate).
2. Run importer manually (`scripts/obsidian_approved_import.py --apply`).
3. Build/update durable graph (`scripts/durable_structure.py`).
4. Export/mirror to the Obsidian vault for browsing/diffing.

## Notes

- This is intentionally LLM-free and deterministic.
- If you want rich entity/project/topic pages, add explicit wikilinks in approved memory text, e.g.:
  - `[decision|0.8] Decide to keep importer manual for now [[Project-OpenClawMem]]`
