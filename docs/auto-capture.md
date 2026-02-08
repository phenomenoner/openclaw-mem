# Auto-Capture Plugin (`openclaw-mem`)

## Overview

The OpenClaw plugin in `extensions/openclaw-mem/` provides two complementary capabilities:

1. **Auto-capture**: listens to the OpenClaw `tool_result_persist` hook and writes compact JSONL observations for later ingestion into the local SQLite store.
2. **Agent memory tools**: exposes `memory_store` / `memory_recall` tools that call into the `openclaw-mem` CLI.

This makes `openclaw-mem` feel like a real “memory layer”:
- passive capture for factual traces of agent work
- explicit store/recall for preferences/tasks you want to persist reliably

---

## Features

✅ Automatic capture (append-only JSONL)  
✅ Include/exclude filtering for noisy tools  
✅ Smart summaries (compact extraction from tool results)  
✅ Optional message capture with truncation  
✅ Best-effort secret redaction before persisting  
✅ Agent tools: `memory_store`, `memory_recall`

---

## Installation

The plugin source is at: `extensions/openclaw-mem/`.

### Option 1: Symlink (recommended)

This keeps the plugin located *inside* the `openclaw-mem` repo, which is important if you want `memory_store` / `memory_recall` to work.

```bash
# From openclaw-mem repo root
ln -s "$(pwd)/extensions/openclaw-mem" ~/.openclaw/plugins/openclaw-mem
openclaw gateway restart
```

### Option 2: Copy (capture-only)

If you copy only the plugin folder into `~/.openclaw/plugins`, auto-capture still works.
However, `memory_store` / `memory_recall` may not work unless the Python project/CLI is installed and available.

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

Note:
- If both `includeTools` and `excludeTools` are empty, all tools are captured.

Tool policy note:
- If your OpenClaw setup uses strict tool policy, explicitly opt-in plugin tools so the agent can call them.
- Recommended additive config (keeps existing profile/allow behavior):

```jsonc
{
  "tools": {
    "alsoAllow": ["memory_store", "memory_recall"]
  }
}
```

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

## Agent memory tools (`memory_store`, `memory_recall`)

When the plugin is enabled, it exposes tools to the agent runtime:

- `memory_store`: stores a memory (calls `openclaw-mem store ...`)
- `memory_recall`: recalls memories (calls `openclaw-mem hybrid ...`)

Implementation note:
- Tool exposure is wired using the official OpenClaw plugin API (`api.registerTool(...)` in `register()`), matching first-party extensions.
- If capture logs appear but these tools are missing, verify you are running a plugin build that includes this registration path and restart the gateway.

Practical notes:
- These tools are best used for **explicit** memory: preferences, tasks, durable facts.
- They require `openclaw-mem` to be runnable (either via `uv` in the repo, or via an installed CLI on PATH).

---

## Usage workflow

### 1) Enable plugin + verify capture

```bash
tail -f ~/.openclaw/memory/openclaw-mem-observations.jsonl
```

### 2) Ingest into SQLite

```bash
cd /path/to/openclaw-mem
uv run openclaw-mem ingest \
  --file ~/.openclaw/memory/openclaw-mem-observations.jsonl --json
```

### 3) Search

```bash
uv run openclaw-mem search "web_search" --json
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
