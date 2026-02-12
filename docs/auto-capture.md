# Auto-Capture Plugin (`openclaw-mem`)

Status: **PARTIAL** (capture-only; sidecar by design).

## Overview

The OpenClaw plugin in `extensions/openclaw-mem/` is **capture-only**:

- listens to `tool_result_persist`
- writes compact JSONL observations for later ingestion into the local SQLite store

For explicit long-term memory writes/reads, use CLI directly:
- `openclaw-mem store ...`
- `openclaw-mem hybrid ...`

### Ecosystem boundaries (why this is sidecar-only)

- `memory-core` and `memory-lancedb` are the canonical OpenClaw memory backends.
- `openclaw-mem` focuses on capture, local ingest/recall, and operations visibility.
- This keeps backend migration and rollback low-risk: slot ownership stays native, while capture/audit remains continuous.

If you want the full deployment matrix, see `docs/ecosystem-fit.md`.

---

## Features

✅ Automatic capture (append-only JSONL)  
✅ Include/exclude filtering for noisy tools  
✅ Smart summaries (compact extraction from tool results)  
✅ Optional message capture with truncation  
✅ Best-effort secret redaction before persisting

---

## Installation

The plugin source is at: `extensions/openclaw-mem/`.

### Option 1: Symlink (recommended)

```bash
# From openclaw-mem repo root
ln -s "$(pwd)/extensions/openclaw-mem" ~/.openclaw/plugins/openclaw-mem
openclaw gateway restart
```

### Option 2: Copy

```bash
cp -r extensions/openclaw-mem ~/.openclaw/plugins/
openclaw gateway restart
```

### Option 3: Plugin load path

```json
{
  "plugins": {
    "load": {
      "paths": ["/path/to/openclaw-mem/extensions/openclaw-mem"]
    }
  }
}
```

---

## Configuration

Add to `~/.openclaw/openclaw.json`:

```jsonc
{
  "plugins": {
    "entries": {
      "openclaw-mem": {
        "enabled": true,
        "config": {
          "outputPath": "~/.openclaw/memory/openclaw-mem-observations.jsonl",
          "enabled": true,
          "captureMessage": false,
          "maxMessageLength": 1000,
          "redactSensitive": true,
          "backendMode": "auto",
          "annotateMemoryTools": true,
          "memoryToolNames": ["memory_search", "memory_get", "memory_store", "memory_recall", "memory_forget"],
          "includeTools": [],
          "excludeTools": ["web_fetch"]
        }
      }
    }
  }
}
```

### Config options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | boolean | `true` | Enable/disable capture behavior inside the plugin |
| `outputPath` | string | `~/.openclaw/memory/openclaw-mem-observations.jsonl` | JSONL output file |
| `captureMessage` | boolean | `false` | Include full tool message (truncated) |
| `maxMessageLength` | number | `1000` | Max message length per content block |
| `redactSensitive` | boolean | `true` | Redact common secret patterns before persisting |
| `includeTools` | string[] | `[]` | Allowlist (if set, only these tools are captured) |
| `excludeTools` | string[] | `[]` | Denylist (excluded tools are not captured) |
| `backendMode` | string | `auto` | Memory backend annotation mode (`auto`, `memory-core`, `memory-lancedb`) |
| `annotateMemoryTools` | boolean | `true` | Write backend/tool metadata into `detail_json` |
| `memoryToolNames` | string[] | canonical set | Tool names treated as memory actions for annotations |

Note:
- If both `includeTools` and `excludeTools` are empty, all tools are captured.

---

## Output format

Each captured tool execution is written as a single-line JSON object:

```jsonl
{"ts":"2026-02-05T20:00:00.000Z","kind":"tool","tool_name":"web_search","tool_call_id":"toolu_01ABC","session_key":"agent:main:main","agent_id":"main","is_synthetic":false,"summary":"searched for OpenClaw docs"}
```

Fields:
- `ts` — ISO 8601 timestamp
- `kind` — currently always `"tool"`
- `tool_name` — tool that was executed
- `tool_call_id` — unique call id
- `session_key` — OpenClaw session identifier
- `agent_id` — agent id
- `is_synthetic` — true if synthesized by guard/repair logic
- `summary` — compact summary extracted from tool result
- `message` — (optional) full tool message if `captureMessage=true`

---

## Usage workflow

### 1) Enable plugin + verify capture

```bash
tail -f ~/.openclaw/memory/openclaw-mem-observations.jsonl
```

### 2) Ingest into SQLite

```bash
cd /path/to/openclaw-mem
uv run python -m openclaw_mem ingest \
  --file ~/.openclaw/memory/openclaw-mem-observations.jsonl --json
```

### 3) Search

```bash
uv run python -m openclaw_mem search "web_search" --json
```

### 4) Explicit memory write/read (CLI)

```bash
uv run python -m openclaw_mem store "Prefer dark theme" --category preference --importance 0.8 --json
uv run python -m openclaw_mem hybrid "theme preference" --limit 5 --json
```

---

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

### JSONL file growing too large

1. Reduce scope (`excludeTools` or `includeTools`)
2. Keep `captureMessage=false`
3. Rotate JSONL periodically (see `docs/deployment.md`)

---

## Next steps

- Deployment patterns: `docs/deployment.md`
- Privacy/export rules: `docs/privacy-export-rules.md`
