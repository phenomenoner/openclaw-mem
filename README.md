# openclaw-mem

> Smart memory management plugin for OpenClaw — observation capture, AI compression, and progressive disclosure search.

`openclaw-mem` is the planned memory-layer plugin for [OpenClaw](https://openclaw.ai). It captures tool-use observations automatically, compresses them with AI into structured learnings, and exposes a token-efficient 3-layer progressive disclosure search CLI. Designed to slot into OpenClaw's native `memory-core` (sqlite-vec + BM25 hybrid) without adding external dependencies.

**🚀 Quick Links:**
- [**Quickstart Guide**](QUICKSTART.md) — Get started in 5 minutes
- [**CHANGELOG**](CHANGELOG.md) — See what's new
- [**Auto-Capture Setup**](docs/auto-capture.md) — Enable plugin
- [**Tests**](tests/) — 26 tests (unit + integration)

## 🙏 Credits & Inspiration

This project is heavily inspired by **[thedotmack/claude-mem](https://github.com/thedotmack/claude-mem)** — a persistent memory compression system for Claude Code that pioneered the observation → AI compression → progressive disclosure pipeline. The core architecture (hook-based capture, SQLite + FTS5 storage, 3-layer search, session lifecycle management) is adapted from that work for the OpenClaw ecosystem.

Thank you [@thedotmack](https://github.com/thedotmack) 🎉

## 📄 Current Status

✅ **M0 (minimal usable) complete!** A CLI-first SQLite + FTS5 prototype with full test coverage is ready. See "M0 Prototype" below for usage. The adoption plan and architecture design live in [`docs/claude-mem-adoption-plan.md`](docs/claude-mem-adoption-plan.md).

**What works:**
- CLI commands: `status`, `ingest`, `search`, `timeline`, `get`, `summarize`, `export`, `embed`, `vsearch`, `hybrid`, `store`
- Plugin: auto-capture via `tool_result_persist` + agent tools `memory_store` / `memory_recall`
- FTS5 full-text search + progressive disclosure (3-layer search)
- Vector search (cosine similarity) + hybrid search via RRF fusion
- AI-native: `--json` output, non-interactive, example-rich help
- Atomic file operations + SQLite WAL mode guidance
- 26 tests (unit + integration, 100% coverage) + GitHub Actions CI

**What's next:**
- ✅ Phase 1: Auto-capture via `tool_result_persist` hook (plugin ready)
- ✅ Phase 2: AI compression integrated into CLI (`summarize` command)
- ✅ Phase 3: Vector search (`embed` + `vsearch` cosine similarity)
- ✅ Auto-config: Reads API key from `~/.openclaw/openclaw.json` (no env var needed)
- ✅ Phase 4: Hybrid search (`hybrid` RRF fusion) + proactive memory tools (`store`, `memory_store`, `memory_recall`)
- ⏳ Next: Route embeddings/LLM calls via OpenClaw Gateway model routing (instead of direct OpenAI HTTP)
- ⏳ Next: Add a first-class auto-ingest/auto-embed workflow (cron/systemd timer)
- ⏳ Next (optional): Weighted hybrid scoring + sqlite-vec acceleration + index rebuild workflow

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
- **Native storage** — SQLite + FTS5 (+ optional sqlite-vec later). No ChromaDB, no external deps.
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

## 🧠 AI Compression (Phase 2)

Compress daily memory notes into `MEMORY.md` using OpenAI API.

### CLI Command (Recommended)

```bash
# Compress yesterday's note (default)
# Note: Automatically reads key from ~/.openclaw/openclaw.json if available
openclaw-mem summarize --json

# Compress specific date
openclaw-mem summarize 2026-02-04

# Dry run (preview without writing)
openclaw-mem summarize --dry-run --json

# Custom workspace
openclaw-mem summarize --workspace /path/to/workspace
```

### Standalone Script (Alternative)

```bash
# Run directly without CLI
OPENAI_API_KEY=sk-... python scripts/compress_memory.py --json
```

### Configuration

CLI flags:
- `--model` — OpenAI model (default: `gpt-5.2`)
- `--max-tokens` — Max output tokens (default: 700)
- `--temperature` — Sampling temperature (default: 0.2)
- `--base-url` — API base URL (default: `https://api.openai.com/v1`)
- `--workspace` — Workspace root (default: current directory)
- `--dry-run` — Preview without writing

Environment variables:
- `OPENAI_API_KEY` — OpenAI API key (optional if set in `~/.openclaw/openclaw.json`)
- `OPENCLAW_MEM_WORKSPACE` — Workspace root (used by standalone script)

### Features
- ✅ Integrated into CLI (`openclaw-mem summarize`)
- ✅ Auto-config: Reads `openclaw.json` for keys
- ✅ Atomic file append (race-safe)
- ✅ Date validation (YYYY-MM-DD)
- ✅ Skip if already compressed
- ✅ Configurable via CLI flags & env vars
- ✅ 100% test coverage

See [`tests/test_compress_memory.py`](tests/test_compress_memory.py) for examples.

## 🔎 Vector Search (Phase 3)

Vector search works in two steps:
1. **Embed** observations (`openclaw-mem embed`) — stores embeddings in SQLite
2. **Search** with cosine similarity (`openclaw-mem vsearch`)

```bash
# API key is read from ~/.openclaw/openclaw.json automatically
# Or set export OPENAI_API_KEY=sk-... to override

# Build embeddings (default model: text-embedding-3-small)
openclaw-mem embed --limit 500 --json

# Vector search
openclaw-mem vsearch "gateway timeout" --limit 10 --json
```

### Offline / Testing Mode

You can run vector search without API calls by providing a query vector:

```bash
openclaw-mem vsearch "ignored" --model test-model \
  --query-vector-json "[1.0, 0.0, 0.0]" --json
```

### Notes
- Current implementation is **cosine similarity only**.
- Hybrid search is available via `openclaw-mem hybrid` (RRF fusion of FTS + vector results).
- Weighted hybrid scoring (e.g., tuned BM25+vector weights) remains a possible future enhancement.

## 🔀 Hybrid Search (Phase 4)

Hybrid search combines:
- **FTS5 BM25** (exact text matching)
- **Embeddings cosine similarity** (semantic matching)

Fusion method: **Reciprocal Rank Fusion (RRF)** — robust to score scale differences.

```bash
# (1) Ensure you have embeddings (Phase 3)
openclaw-mem embed --limit 500 --json

# (2) Hybrid search
openclaw-mem hybrid "gateway timeout" --limit 10 --json
```

## 🧷 Proactive Memory Tools (Phase 4)

### CLI: `store`

Use this when the agent/user explicitly says “remember this”. It will:
1) Insert into SQLite
2) (If API key is available) embed it
3) Append a short line to `memory/YYYY-MM-DD.md`

```bash
openclaw-mem store "Prefer Python 3.13 + uv" --category preference --importance 0.9 --json
```

### Plugin tools: `memory_store` / `memory_recall`

The OpenClaw plugin also exposes `memory_store` + `memory_recall` tools to the agent (see `extensions/openclaw-mem/`).

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

## 🚀 Future CLI Ideas (later phases)

```bash
openclaw-mem tail --follow                 # Stream recent observations
openclaw-mem summarize --dates 2026-02-01..2026-02-07
openclaw-mem export --to MEMORY.md --yes   # Export observations (and later: learnings) to long-term memory (guarded)
```

**AI-native CLI design**
- All commands support `--json` for structured output.
- No interactive prompts by default; use `--yes`/`--force` for side-effectful actions.
- Help text includes examples and explicit warnings for destructive flags.

## 📄 License

MIT
