# OpenClaw Mem Engine plugin

`openclaw-mem-engine` is the **optional memory-slot backend** shipped alongside `openclaw-mem`.

What it does:
- becomes the active OpenClaw memory backend when selected in `plugins.slots.memory`
- provides hybrid recall controls (FTS + vector) with scope-aware policies
- exposes bounded autoRecall / autoCapture controls and lifecycle receipts
- hosts the docs cold-lane ingest/search surfaces for operator-authored markdown

This package is different from the sidecar capture plugin:
- **`openclaw-mem`** = sidecar capture / observability / episodic spool / operator workflows
- **`openclaw-mem-engine`** = active memory slot backend

## Install

### Local checkout

```bash
openclaw plugins install -l ./extensions/openclaw-mem-engine
```

### Marketplace package

After publishing to ClawHub package marketplace:

```bash
openclaw plugins install @phenomenoner/openclaw-mem-engine
```

## Minimal config

```jsonc
{
  "plugins": {
    "slots": {
      "memory": "openclaw-mem-engine"
    },
    "entries": {
      "openclaw-mem-engine": {
        "enabled": true,
        "config": {
          "dbPath": "~/.openclaw/memory/lancedb",
          "tableName": "memories_engine",
          "readOnly": false,
          "docsColdLane": {
            "enabled": true
          }
        }
      }
    }
  }
}
```

## Rollback

Switch `plugins.slots.memory` back to `memory-lancedb` or `memory-core`, then restart the gateway.

## More context

See the repo docs for:
- `docs/mem-engine.md`
- `docs/ecosystem-fit.md`
- `docs/mem-engine-admin-ops.md`
