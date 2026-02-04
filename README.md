# openclaw-mem

> Smart memory management plugin for OpenClaw — observation capture, AI compression, and progressive disclosure search.

`openclaw-mem` is the planned memory-layer plugin for [OpenClaw](https://openclaw.ai). It captures tool-use observations automatically, compresses them with AI into structured learnings, and exposes a token-efficient 3-layer progressive disclosure search CLI. Designed to slot into OpenClaw's native `memory-core` (sqlite-vec + BM25 hybrid) without adding external dependencies.

## 🙏 Credits & Inspiration

This project is heavily inspired by **[thedotmack/claude-mem](https://github.com/thedotmack/claude-mem)** — a persistent memory compression system for Claude Code that pioneered the observation → AI compression → progressive disclosure pipeline. The core architecture (hook-based capture, SQLite + FTS5 storage, 3-layer search, session lifecycle management) is adapted from that work for the OpenClaw ecosystem.

Thank you [@thedotmack](https://github.com/thedotmack) 🎉

## 📄 Current Status

🚧 **M0 (minimal usable) in progress.** A CLI-first SQLite + FTS prototype is now in-repo; see "M0 Prototype" below. The adoption plan and architecture design live in [`docs/claude-mem-adoption-plan.md`](docs/claude-mem-adoption-plan.md).

## 📖 Architecture at a Glance

```
Tool executions (hook) → SQLite observations → AI batch compression
                                                      ↓
                                              memory/YYYY-MM-DD.md  ←→  Native memorySearch
                                                      ↓
                                         openclaw-mem CLI (3-layer search)
                                           search → timeline → get
```

- **Observation capture** via `tool_result_persist` hook — 100% capture rate.
- **AI compression** — 50 raw observations → ~500-token summary (10x compression).
- **Progressive disclosure search** — Layer 1 (compact index, ~50–100 tok/result) → Layer 2 (timeline context) → Layer 3 (full details). ~10x token savings vs. full dump.
- **Proactive memory tools** — `memory_store` and `memory_recall` tools for the agent to explicitly save/retrieve important facts (preferences, decisions, entities).
- **Native storage** — SQLite + FTS5 + sqlite-vec. No ChromaDB, no external deps.
- **Integrates with existing memory** — writes learnings into `memory/*.md`; OpenClaw's built-in `memorySearch` picks them up automatically.

## ✅ M0 Prototype (minimal usable milestone)

**Goal:** usable observation store + search CLI (SQLite + FTS5) with JSON output.
See full notes: [`docs/m0-prototype.md`](docs/m0-prototype.md)

```bash
# status
uv run --python 3.13 -- python -m openclaw_mem status --json

# ingest (JSONL)
uv run --python 3.13 -- python -m openclaw_mem ingest --file observations.jsonl --json

# search / timeline / get (progressive disclosure)
uv run --python 3.13 -- python -m openclaw_mem search "gateway timeout" --limit 20 --json
uv run --python 3.13 -- python -m openclaw_mem timeline 23 41 57 --window 4 --json
uv run --python 3.13 -- python -m openclaw_mem get 23 41 57 --json
```

### Input JSONL format (ingest)
```
{"ts":"2026-02-04T13:00:00Z","kind":"tool","tool_name":"cron.list","summary":"cron list called","detail":{"ok":true}}
```

## 🧠 AI Compression (script)

Standalone script to compress `memory/YYYY-MM-DD.md` into `MEMORY.md` using OpenAI API.

```bash
# Explicit date
OPENAI_API_KEY=... python scripts/compress_memory.py 2026-02-04

# Default = yesterday
python scripts/compress_memory.py --json --dry-run
```

Optional env vars:
- `OPENCLAW_MEM_MODEL` (default: `gpt-4.1`)
- `OPENCLAW_MEM_MAX_TOKENS` (default: 700)
- `OPENCLAW_MEM_TEMPERATURE` (default: 0.2)
- `OPENAI_BASE_URL` (default: `https://api.openai.com/v1`)

## 🚀 Planned CLI (later phases)

```bash
openclaw-mem summarize --session latest    # Run AI compression
openclaw-mem export --to MEMORY.md         # Export learnings to long-term memory
```

**AI-native CLI design**
- All commands support `--json` for structured output.
- No interactive prompts by default; use `--yes`/`--force` for side-effectful actions.
- Help text includes examples and explicit warnings for destructive flags.

## 📄 License

MIT
