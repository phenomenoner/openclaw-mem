# Quickstart Guide

Get openclaw-mem up and running in under 5 minutes.

## Prerequisites

- Python 3.13+
- [uv](https://github.com/astral-sh/uv) installed
- OpenClaw gateway running (for auto-capture plugin)

## Step 1: Install

```bash
# Clone the repo
git clone https://github.com/phenomenoner/openclaw-mem.git
cd openclaw-mem

# Install dependencies
uv sync --locked
```

## Step 2: Quick Test

```bash
# Run status check (creates empty DB)
uv run --python 3.13 -- python -m openclaw_mem status --json

# Expected output:
# {
#   "db": "~/.openclaw/memory/openclaw-mem.sqlite",
#   "count": 0,
#   "min_ts": null,
#   "max_ts": null
# }
```

## Step 3: Ingest Sample Data

```bash
# Create sample observations
cat > /tmp/sample.jsonl <<'EOF'
{"ts":"2026-02-05T10:00:00Z","kind":"tool","tool_name":"web_search","summary":"searched for OpenClaw","detail":{"results":5}}
{"ts":"2026-02-05T10:01:00Z","kind":"tool","tool_name":"web_fetch","summary":"fetched openclaw.ai","detail":{"ok":true}}
{"ts":"2026-02-05T10:02:00Z","kind":"tool","tool_name":"exec","summary":"ran git status","detail":{"exit_code":0}}
EOF

# Ingest
uv run --python 3.13 -- python -m openclaw_mem ingest --file /tmp/sample.jsonl --json
```

## Step 4: Search

```bash
# Search for observations
uv run --python 3.13 -- python -m openclaw_mem search "OpenClaw" --json

# Get details for ID 1
uv run --python 3.13 -- python -m openclaw_mem get 1 --json

# Timeline around ID 2 (±2 observations)
uv run --python 3.13 -- python -m openclaw_mem timeline 2 --window 2 --json
```

## Step 5: Enable Auto-Capture (Optional)

To automatically capture tool executions:

```bash
# Symlink plugin into OpenClaw
ln -s "$(pwd)/extensions/openclaw-mem" ~/.openclaw/plugins/openclaw-mem

# Add config to ~/.openclaw/openclaw.json
cat >> ~/.openclaw/openclaw.json <<'JSON'
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
JSON

# Restart gateway
openclaw gateway restart
```

Verify capture is working:

```bash
# Check that observations are being written
tail -f ~/.openclaw/memory/openclaw-mem-observations.jsonl

# Ingest them periodically
uv run --python 3.13 -- python -m openclaw_mem ingest \
  --file ~/.openclaw/memory/openclaw-mem-observations.jsonl --json
```

## Step 6: AI Compression (Optional)

To compress daily notes into MEMORY.md:

```bash
# Set API key
export OPENAI_API_KEY=sk-...

# Compress yesterday's note (dry-run first)
uv run --python 3.13 -- python -m openclaw_mem summarize --dry-run --json

# Actually write to MEMORY.md
uv run --python 3.13 -- python -m openclaw_mem summarize --json
```

## Next Steps

- Read [`README.md`](README.md) for full documentation
- See [`docs/auto-capture.md`](docs/auto-capture.md) for plugin setup details
- Check [`CHANGELOG.md`](CHANGELOG.md) for complete feature list
- Run tests: `uv run --python 3.13 -- python -m unittest discover -s tests`

## Common Issues

### "ModuleNotFoundError: No module named 'openclaw_mem'"

Make sure you're in the openclaw-mem directory and have run `uv sync --locked`.

### "database is locked" errors

Enable WAL mode (already done by default) and ensure you're using short-lived connections. See [`docs/db-concurrency.md`](docs/db-concurrency.md).

### Plugin not capturing

1. Check plugin is loaded: `openclaw plugins list | grep openclaw-mem`
2. Check config: `openclaw config get | jq '.plugins.entries["openclaw-mem"]'`
3. Check logs: `tail -f ~/.openclaw/logs/gateway.log | grep openclaw-mem`

## CLI Cheat Sheet

```bash
# Status
openclaw-mem status --json

# Ingest
openclaw-mem ingest --file observations.jsonl --json

# Search (Layer 1: compact results)
openclaw-mem search "keyword" --limit 20 --json

# Timeline (Layer 2: context window)
openclaw-mem timeline 10 20 30 --window 4 --json

# Get (Layer 3: full details)
openclaw-mem get 10 20 30 --json

# AI compression
export OPENAI_API_KEY=sk-...
openclaw-mem summarize --dry-run --json  # preview
openclaw-mem summarize --json            # write
```

## Support

- GitHub Issues: https://github.com/phenomenoner/openclaw-mem/issues
- OpenClaw Discord: https://discord.com/invite/clawd
- Documentation: See [`README.md`](README.md)
