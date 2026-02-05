# Auto-Capture Plugin

## Overview

The `openclaw-mem` plugin automatically captures tool execution results via the `tool_result_persist` hook and writes them to a JSONL file for ingestion into the observation store.

## Features

✅ **Automatic capture** — No manual logging required  
✅ **Filter controls** — Include/exclude specific tools  
✅ **Smart summaries** — Extracts compact summaries from tool results  
✅ **Message truncation** — Optional full message capture (size-limited)  
✅ **Crash-safe** — Append-only JSONL (durable on process termination)

## Installation

The plugin is located at `extensions/openclaw-mem/` in this repo.

### Option 1: Symlink (Development)

```bash
# From openclaw-mem repo root
ln -s "$(pwd)/extensions/openclaw-mem" ~/.openclaw/plugins/openclaw-mem

# Restart OpenClaw gateway
openclaw gateway restart
```

### Option 2: Copy (Production)

```bash
cp -r extensions/openclaw-mem ~/.openclaw/plugins/
openclaw gateway restart
```

### Option 3: Plugin Load Path

Add to `openclaw.json`:

```json
{
  "plugins": {
    "load": {
      "paths": ["/path/to/openclaw-mem/extensions/openclaw-mem"]
    }
  }
}
```

## Configuration

Add to `openclaw.json`:

```json
{
  "plugins": {
    "entries": {
      "openclaw-mem": {
        "enabled": true,
        "config": {
          "outputPath": "~/.openclaw/memory/openclaw-mem-observations.jsonl",
          "captureMessage": false,
          "maxMessageLength": 1000,
          "includeTools": [],
          "excludeTools": ["web_fetch"]
        }
      }
    }
  }
}
```

### Config Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | boolean | `true` | Enable/disable capture |
| `outputPath` | string | `~/.openclaw/memory/openclaw-mem-observations.jsonl` | JSONL output file |
| `captureMessage` | boolean | `false` | Include full tool message (truncated) |
| `maxMessageLength` | number | `1000` | Max message length per content block |
| `includeTools` | string[] | `[]` | Allowlist (if set, only these tools) |
| `excludeTools` | string[] | `[]` | Denylist (excludes specific tools) |

**Note:** If both `includeTools` and `excludeTools` are empty, all tools are captured.

## Output Format

Each captured tool execution is written as a single-line JSON object:

```jsonl
{"ts":"2026-02-05T20:00:00.000Z","kind":"tool","tool_name":"web_search","tool_call_id":"toolu_01ABC","session_key":"agent:main:main","agent_id":"main","is_synthetic":false,"summary":"searched for OpenClaw docs"}
```

### Fields

- `ts` — ISO 8601 timestamp
- `kind` — Always `"tool"` (reserved for future: `"user"`, `"assistant"`)
- `tool_name` — Tool that was executed
- `tool_call_id` — Unique call ID from LLM
- `session_key` — OpenClaw session identifier
- `agent_id` — Agent ID
- `is_synthetic` — `true` if synthesized by guard/repair logic
- `summary` — Compact summary extracted from tool result
- `message` — (optional) Full tool message if `captureMessage=true`

## Usage Workflow

### 1. Enable Plugin

```bash
# Add to openclaw.json, then restart
openclaw gateway restart
```

### 2. Verify Capture

```bash
# Check that observations are being written
tail -f ~/.openclaw/memory/openclaw-mem-observations.jsonl
```

### 3. Ingest into SQLite

```bash
cd /path/to/openclaw-mem
uv run --python 3.13 -- python -m openclaw_mem ingest \
  --file ~/.openclaw/memory/openclaw-mem-observations.jsonl --json
```

### 4. Search

```bash
uv run --python 3.13 -- python -m openclaw_mem search "web_search" --json
```

## Advanced: Periodic Ingestion (Cron)

Add a cron job to automatically ingest new observations:

```json
{
  "cron": {
    "jobs": [
      {
        "name": "Ingest openclaw-mem observations",
        "schedule": { "kind": "every", "everyMs": 300000 },
        "sessionTarget": "isolated",
        "payload": {
          "kind": "agentTurn",
          "message": "Run: cd /path/to/openclaw-mem && uv run -- python -m openclaw_mem ingest --file ~/.openclaw/memory/openclaw-mem-observations.jsonl --json",
          "deliver": false
        }
      }
    ]
  }
}
```

## Filtering Examples

### Capture Only Specific Tools

```json
{
  "openclaw-mem": {
    "config": {
      "includeTools": ["web_search", "web_fetch", "exec"]
    }
  }
}
```

### Exclude Noisy Tools

```json
{
  "openclaw-mem": {
    "config": {
      "excludeTools": ["session_status", "cron.list"]
    }
  }
}
```

## Performance & Storage

**Typical observation size:** ~200-500 bytes (without full message)  
**With full message:** ~1-5 KB per observation (depends on tool output)

**Storage estimates:**
- 1000 tool calls/day × 300 bytes = ~300 KB/day = ~9 MB/month
- 1000 tool calls/day × 2 KB = ~2 MB/day = ~60 MB/month (with messages)

**Rotation:** Use `logrotate` or a cron job to archive old JSONL files:

```bash
# ~/.openclaw/memory/openclaw-mem-observations.jsonl
# Rotate daily, keep 30 days
0 0 * * * mv ~/.openclaw/memory/openclaw-mem-observations.jsonl ~/.openclaw/memory/openclaw-mem-observations-$(date +\%Y-\%m-\%d).jsonl
```

## Troubleshooting

### Plugin not capturing

1. Check plugin is loaded:
   ```bash
   openclaw plugins list | grep openclaw-mem
   ```

2. Check config:
   ```bash
   openclaw config get | jq '.plugins.entries["openclaw-mem"]'
   ```

3. Check logs:
   ```bash
   tail -f ~/.openclaw/logs/gateway.log | grep openclaw-mem
   ```

### Permission errors

Ensure output directory exists and is writable:
```bash
mkdir -p ~/.openclaw/memory
chmod 755 ~/.openclaw/memory
```

### JSONL file growing too large

1. Enable rotation (see Performance section)
2. Reduce capture scope (use `excludeTools`)
3. Disable `captureMessage` if enabled

## Next Steps

After auto-capture is running:
1. Set up periodic ingestion (cron job)
2. Explore search & timeline commands
3. Configure AI compression (Phase 2)
4. Enable vector search (Phase 3)
