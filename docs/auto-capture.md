# Auto-capture (tool_result_persist)

## What it does
Captures **tool results** as JSONL via a lightweight OpenClaw plugin hook, then you can ingest into SQLite with the M0 CLI.

## Plugin location
This repo ships a plugin at:
```
extensions/openclaw-mem/
```

## Enable in OpenClaw
Add the plugin path and config to `openclaw.json` (example):

```json5
plugins: {
  load: { paths: ["/path/to/openclaw-mem/extensions/openclaw-mem"] },
  entries: {
    "openclaw-mem": {
      enabled: true,
      config: {
        enabled: true,
        outputPath: "~/.openclaw/memory/openclaw-mem-observations.jsonl",
        // optional filters
        // includeTools: ["cron.list", "gateway.config.get"],
        // excludeTools: ["web_fetch"]
      }
    }
  }
}
```

Then restart the gateway.

## Ingest into SQLite
```bash
uv run --python 3.13 -- python -m openclaw_mem ingest \
  --file ~/.openclaw/memory/openclaw-mem-observations.jsonl --json
```

## Notes
- `tool_result_persist` **must be synchronous**; the plugin writes JSONL via `appendFileSync`.
- This is minimal by design (no LLMs, no extra deps).
