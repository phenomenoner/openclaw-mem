# openclaw-mem

Lightweight long-term memory for OpenClaw agents.

`openclaw-mem` captures useful observations, stores them in local SQLite, and gives you cheap progressive recall (search → context window → full record), with optional embeddings/hybrid recall and deterministic triage.

## What you get

- Local memory store: **SQLite + FTS5**
- Progressive disclosure recall: `search` → `timeline` → `get`
- Optional vector recall: `embed`, `vsearch`, `hybrid`
- Dual-language memory support:
  - store original + optional English text (`--text-en`)
  - optional dedicated EN embeddings (`observation_embeddings_en`)
  - EN assist query route in hybrid (`--query-en`)
- Proactive writes: `store`
- Auto-ingest pipeline: `harvest`
- Deterministic heartbeat triage: `triage` (`heartbeat` / `cron-errors` / `tasks`)
- Optional daily memory compression: `summarize`

No external DB required.

## Install

```bash
git clone https://github.com/phenomenoner/openclaw-mem.git
cd openclaw-mem
uv sync --locked
```

## Quick usage

```bash
# Create/open DB and show counts
uv run --python 3.13 -- python -m openclaw_mem status --json

# Ingest JSONL observations
uv run --python 3.13 -- python -m openclaw_mem ingest --file observations.jsonl --json

# Layer 1 recall (compact)
uv run --python 3.13 -- python -m openclaw_mem search "gateway timeout" --limit 10 --json

# Layer 2 recall (nearby context)
uv run --python 3.13 -- python -m openclaw_mem timeline 42 --window 3 --json

# Layer 3 recall (full rows)
uv run --python 3.13 -- python -m openclaw_mem get 42 --json
```

## Dual-language memory (zh/en etc.)

```bash
# Store original text + optional English companion
openclaw-mem store "偏好：發布前先跑整合測試" \
  --text-en "Preference: run integration tests before release" \
  --lang zh --category preference --importance 0.9 --json

# Build original embeddings (default)
openclaw-mem embed --field original --limit 500 --json

# Build English embeddings from summary_en/text_en
openclaw-mem embed --field english --limit 500 --json

# Build both in one pass
openclaw-mem embed --field both --limit 500 --json

# Hybrid recall with optional EN assist query
openclaw-mem hybrid "發布前流程" --query-en "pre-release process" --limit 5 --json
```

Design notes and rollout details:
- `docs/dual-language-memory-strategy.md`
- `docs/archive/2026-02-07-dual-language-rollout.md` (historical rollout plan)

## Auto-capture plugin

`extensions/openclaw-mem` listens to OpenClaw `tool_result_persist` and writes JSONL for ingestion.

Minimal config fragment for `~/.openclaw/openclaw.json`:

```jsonc
{
  "plugins": {
    "entries": {
      "openclaw-mem": {
        "enabled": true,
        "config": {
          "outputPath": "~/.openclaw/memory/openclaw-mem-observations.jsonl",
          "captureMessage": false,
          "redactSensitive": true
        }
      }
    }
  }
}
```

## Deterministic triage (heartbeat-safe)

```bash
# 0: no new issues, 10: attention needed
openclaw-mem triage --mode heartbeat --json
```

## Docs map

Core docs:
- `QUICKSTART.md` — 5-minute setup
- `docs/auto-capture.md` — plugin setup + troubleshooting
- `docs/deployment.md` — production timers/permissions/rotation
- `docs/privacy-export-rules.md` — export safety rules
- `docs/db-concurrency.md` — WAL + lock guidance
- `docs/dual-language-memory-strategy.md` — current zh/en memory approach

Historical docs (archived):
- `docs/archive/README.md`

## Test

```bash
uv run --python 3.13 -- python -m unittest discover -s tests -p 'test_*.py'
```

## License

Apache-2.0 (`LICENSE`).
