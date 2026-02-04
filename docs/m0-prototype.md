# M0 Prototype (Minimal Usable Milestone)

## Goal
Provide a **usable** observation store + search workflow without full plugin wiring.
This delivers immediate value for debugging and recall by letting us ingest tool logs (JSONL)
and search them with progressive disclosure (search → timeline → get).

## Scope (M0)
- SQLite store with FTS5 index.
- CLI: `status`, `ingest`, `search`, `timeline`, `get`.
- AI‑native: `--json` output, non‑interactive, example‑rich help.

## Quickstart
```bash
# From repo root
uv run --python 3.13 -- python -m openclaw_mem status --json

# Ingest JSONL
uv run --python 3.13 -- python -m openclaw_mem ingest --file observations.jsonl --json

# Search / timeline / get
uv run --python 3.13 -- python -m openclaw_mem search "gateway timeout" --limit 20 --json
uv run --python 3.13 -- python -m openclaw_mem timeline 23 41 57 --window 4 --json
uv run --python 3.13 -- python -m openclaw_mem get 23 41 57 --json
```

## JSONL format
One observation per line:
```json
{"ts":"2026-02-04T13:00:00Z","kind":"tool","tool_name":"cron.list","summary":"cron list called","detail":{"ok":true}}
```

## Limitations (M0)
- Manual ingestion only (no hooks yet).
- FTS‑only search (no embeddings/hybrid).
- No AI compression or MEMORY.md export.

## Next steps
- Hook-based auto-capture (`tool_result_persist`).
- AI compression pipeline + export.
- Hybrid vector + BM25 scoring.
