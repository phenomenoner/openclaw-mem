# openclaw-mem

> A lightweight memory layer for OpenClaw agents — capture → store → search → (optional) compress.

`openclaw-mem` helps OpenClaw agents build **useful long-term memory** without dragging a heavyweight stack into your deployment.

It can:
- **auto-capture** tool-use observations (via OpenClaw `tool_result_persist` hook)
- store everything locally in **SQLite + FTS5**
- provide **token-efficient progressive disclosure** search (search → timeline → get)
- optionally add **embeddings + hybrid search**
- run **deterministic triage** for heartbeats (cron errors + new tasks only; deduped)

Apache-2.0 licensed. No external DB required.

## 🔗 Quick links

- [Quickstart](QUICKSTART.md) (5 minutes)
- [Changelog](CHANGELOG.md)
- [Deployment guide](docs/deployment.md)
- [Auto-capture plugin setup](docs/auto-capture.md)
- [Privacy & export rules](docs/privacy-export-rules.md)
- [Dual-language memory strategy](docs/dual-language-memory-strategy.md)
- [Tests](tests/) (32 unit + integration)

## ✨ Why it’s useful (the pitch, but true)

If you’re building agents, you quickly hit two problems:
1) **Context is expensive** (token/cost + latency)
2) **Logs are noisy** (you want the 1% that matters)

`openclaw-mem` is built around a simple idea:
- store raw observations locally
- retrieve them **progressively** (small → bigger → full)
- keep proactive “things to remember” explicit (`memory_store` / `openclaw-mem store`)
- keep automation **deterministic** by default (no LLM in heartbeats)

## ✅ What’s included (milestone wrap-up)

**Core capabilities**
- Observation DB: **SQLite + FTS5**
- Search UX: **progressive disclosure** (search → timeline → get)
- AI compression: `openclaw-mem summarize` (can route via **OpenClaw Gateway**)
- Embeddings: `embed` + `vsearch` (cosine similarity)
- Hybrid search: `hybrid` (RRF fusion)
- Proactive memory: `store` CLI + plugin tools `memory_store` / `memory_recall`
- Auto-ingest: `harvest` (log rotation + ingest + optional embed)
- Deterministic triage: `triage` modes `heartbeat` / `cron-errors` / `tasks` (dedup state)
- OpenClaw-native semantic recall (black-box embeddings): `index` + `semantic` (via Gateway `/tools/invoke` → `memory_search`)

**Safety defaults**
- Plugin defaults are designed to reduce accidental persistence of sensitive data:
  - `captureMessage: false`
  - `redactSensitive: true` (best-effort pattern redaction)
  - `excludeTools` recommended for high-sensitivity tools (see deployment guide)

## 🧭 Docs index (systematic)

Start here:
- **[QUICKSTART.md](QUICKSTART.md)** — install + first search

## 🌐 Dual-language memory (zh/en)

For mixed-language memory deployments, see **[docs/dual-language-memory-strategy.md](docs/dual-language-memory-strategy.md)**.
It covers rationale, field design (`text` + optional `text_en`), query fallback flow, tradeoffs, and rollout KPIs.

Then pick what you need:
- **[docs/auto-capture.md](docs/auto-capture.md)** — enable the plugin + troubleshooting
- **[docs/deployment.md](docs/deployment.md)** — production setup: timers/cron, rotation, backups, permissions
- **[docs/privacy-export-rules.md](docs/privacy-export-rules.md)** — guardrails for exporting memory
- **[docs/db-concurrency.md](docs/db-concurrency.md)** — WAL mode + avoiding lock issues
- **[docs/embedding-status.md](docs/embedding-status.md)** — embeddings options & tradeoffs
- **[docs/m0-prototype.md](docs/m0-prototype.md)** — original M0 design notes
- **[docs/claude-mem-adoption-plan.md](docs/claude-mem-adoption-plan.md)** — architecture/adaptation notes

## 🏁 Quickstart (tiny demo)

```bash
# status (creates DB if missing)
uv run --python 3.13 -- python -m openclaw_mem status --json

# ingest JSONL
uv run --python 3.13 -- python -m openclaw_mem ingest --file observations.jsonl --json

# search (Layer 1)
uv run --python 3.13 -- python -m openclaw_mem search "gateway timeout" --limit 10 --json
```

Full quickstart: [QUICKSTART.md](QUICKSTART.md)

## 🧩 How it works (architecture)

```
Tool executions (hook) → JSONL → SQLite observations
                                   ↓
                     (optional) embeddings / hybrid search
                                   ↓
                CLI search: search → timeline → get (progressive)
                                   ↓
         (optional) summarize → memory/*.md → OpenClaw native memorySearch
```

The design goal is **cheap retrieval**: most of the time you only need the small “index-like” layer.

## 🔌 Auto-capture plugin (hook)

The plugin listens to OpenClaw’s `tool_result_persist` hook and writes JSONL.

**Important:** treat the config snippet below as a **fragment** to merge into your existing `~/.openclaw/openclaw.json`.

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

Setup guide: [docs/auto-capture.md](docs/auto-capture.md)

## 🧪 Tests

```bash
python -m unittest discover -s tests -q
```

CI runs on GitHub Actions.

## 🙏 Credits & inspiration

This project is heavily inspired by **[thedotmack/claude-mem](https://github.com/thedotmack/claude-mem)** — the observation → AI compression → progressive disclosure pipeline was pioneered there, and adapted here for the OpenClaw ecosystem.

## 📄 License

Apache-2.0 (see [LICENSE](LICENSE)).
