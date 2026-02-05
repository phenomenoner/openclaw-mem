# openclaw-mem

> Smart memory management plugin for OpenClaw — observation capture, AI compression, and progressive disclosure search.

`openclaw-mem` is the planned memory-layer plugin for [OpenClaw](https://openclaw.ai). It captures tool-use observations automatically, compresses them with AI into structured learnings, and exposes a token-efficient 3-layer progressive disclosure search CLI. Designed to slot into OpenClaw's native `memory-core` (sqlite-vec + BM25 hybrid) without adding external dependencies.

## 🙏 Credits & Inspiration

This project is heavily inspired by **[thedotmack/claude-mem](https://github.com/thedotmack/claude-mem)** — a persistent memory compression system for Claude Code that pioneered the observation → AI compression → progressive disclosure pipeline. The core architecture (hook-based capture, SQLite + FTS5 storage, 3-layer search, session lifecycle management) is adapted from that work for the OpenClaw ecosystem.

Thank you [@thedotmack](https://github.com/thedotmack) 🎉

## 📄 Current Status

✅ **M0 (minimal usable) complete!** A CLI-first SQLite + FTS5 prototype with full test coverage is ready. See "M0 Prototype" below for usage. The adoption plan and architecture design live in [`docs/claude-mem-adoption-plan.md`](docs/claude-mem-adoption-plan.md).

**What works:**
- CLI commands: `status`, `ingest`, `search`, `timeline`, `get`
- FTS5 full-text search over observations
- Progressive disclosure (3-layer search)
- AI-native: `--json` output, non-interactive, example-rich help
- Atomic file operations (WAL mode, race-safe append)
- AI compression script (`scripts/compress_memory.py`) with OpenAI API
- 13 unit tests (100% coverage) + GitHub Actions CI

**What's next:**
- ✅ Phase 1: Auto-capture via `tool_result_persist` hook (plugin ready)
- ⏳ Phase 2: Integrate AI compression into CLI
- ⏳ Phase 3: Vector search (hybrid BM25 + embeddings)

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

## 🔌 Auto-Capture Plugin (Phase 1)

The `openclaw-mem` plugin automatically captures tool executions via the `tool_result_persist` hook.

### Quick Setup

```bash
# Symlink plugin into OpenClaw plugins directory
ln -s "$(pwd)/extensions/openclaw-mem" ~/.openclaw/plugins/openclaw-mem

# Add config to openclaw.json
{
  "plugins": {
    "entries": {
      "openclaw-mem": {
        "enabled": true,
        "config": {
          "outputPath": "~/.openclaw/memory/openclaw-mem-observations.jsonl"
        }
      }
    }
  }
}

# Restart gateway
openclaw gateway restart
```

**Features:**
- ✅ Captures all tool results automatically
- ✅ Smart summaries (200 char extract from results)
- ✅ Filter controls (include/exclude specific tools)
- ✅ Optional full message capture (truncated)

See [`docs/auto-capture.md`](docs/auto-capture.md) for full documentation.

## 📦 Installation

```bash
# Clone the repo
git clone https://github.com/phenomenoner/openclaw-mem.git
cd openclaw-mem

# Install dependencies (requires Python 3.13+)
uv sync --locked

# Run CLI
uv run --python 3.13 -- python -m openclaw_mem --help
```

## 🚀 Usage (M0 Prototype)

**Goal:** usable observation store + search CLI (SQLite + FTS5) with JSON output.

### Quick Start

```bash
# Check status
uv run --python 3.13 -- python -m openclaw_mem status --json

# Ingest observations from JSONL
uv run --python 3.13 -- python -m openclaw_mem ingest --file observations.jsonl --json

# Search (Layer 1: compact results)
uv run --python 3.13 -- python -m openclaw_mem search "gateway timeout" --limit 20 --json

# Timeline (Layer 2: context window around IDs)
uv run --python 3.13 -- python -m openclaw_mem timeline 23 41 57 --window 4 --json

# Get (Layer 3: full observation details)
uv run --python 3.13 -- python -m openclaw_mem get 23 41 57 --json
```

### Input JSONL Format (ingest)
```jsonl
{"ts":"2026-02-04T13:00:00Z","kind":"tool","tool_name":"cron.list","summary":"cron list called","detail":{"ok":true}}
{"ts":"2026-02-04T13:01:00Z","kind":"tool","tool_name":"web_search","summary":"searched for 'OpenClaw'","detail":{"results":[...]}}
```

See [`docs/hooks_examples/`](docs/hooks_examples/) for real payload examples from OpenClaw hooks.

### Progressive Disclosure Workflow

```bash
# 1. Search for high-level matches
openclaw-mem search "memory bug" --json | jq '.[] | {id, ts, summary}'

# 2. Get timeline context around interesting IDs
openclaw-mem timeline 42 67 --window 5 --json

# 3. Fetch full details for final review
openclaw-mem get 42 67 --json | jq '.[] | {id, tool_name, detail_json}'
```

### Configuration

All commands support `--db` and `--json` flags (can be placed before or after the command):

```bash
# Global flags before command
openclaw-mem --db /tmp/test.sqlite --json status

# Per-command flags after command
openclaw-mem status --db /tmp/test.sqlite --json
```

Environment variables:
- `OPENCLAW_MEM_DB` — SQLite DB path (default: `~/.openclaw/memory/openclaw-mem.sqlite`)

## 🧠 AI Compression Script

Compress daily memory notes into `MEMORY.md` using OpenAI API.

### Usage

```bash
# Compress yesterday's note (default)
OPENAI_API_KEY=sk-... python scripts/compress_memory.py --json

# Compress specific date
python scripts/compress_memory.py 2026-02-04

# Dry run (preview without writing)
python scripts/compress_memory.py --dry-run

# Custom workspace
OPENCLAW_MEM_WORKSPACE=/path/to/workspace python scripts/compress_memory.py
```

### Configuration

Environment variables:
- `OPENAI_API_KEY` — **Required** OpenAI API key
- `OPENCLAW_MEM_WORKSPACE` — Workspace root (default: repo root)
- `OPENCLAW_MEM_MODEL` — Model name (default: `gpt-4.1`)
- `OPENCLAW_MEM_MAX_TOKENS` — Max output tokens (default: 700)
- `OPENCLAW_MEM_TEMPERATURE` — Sampling temperature (default: 0.2)
- `OPENAI_BASE_URL` — API base URL (default: `https://api.openai.com/v1`)

### Features
- ✅ Atomic file append (race-safe)
- ✅ Date validation (YYYY-MM-DD)
- ✅ Skip if already compressed
- ✅ Configurable via env vars & CLI flags
- ✅ 100% test coverage

See [`tests/test_compress_memory.py`](tests/test_compress_memory.py) for examples.

## 🧪 Testing

### Run Tests

```bash
# Run all tests
uv run --python 3.13 -- python -m unittest discover -s tests -p 'test_*.py' -v

# Run specific test file
uv run --python 3.13 -- python -m unittest tests/test_cli.py -v

# CI (GitHub Actions)
# Automatically runs on push/PR
```

### Test Coverage
- ✅ CLI commands (status, ingest, search, timeline, get)
- ✅ FTS5 search correctness
- ✅ AI compression (OpenAIClient mock, atomic append, date validation)
- ✅ In-memory DB support (for fast tests)
- ✅ Edge cases (empty notes, missing files, invalid dates)

### Test Fixtures
- [`docs/hooks_examples/`](docs/hooks_examples/) — Sample OpenClaw hook payloads

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
