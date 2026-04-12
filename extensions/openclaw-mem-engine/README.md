# OpenClaw Mem Engine plugin

`openclaw-mem-engine` is the **optional memory-slot backend** shipped alongside `openclaw-mem`.

What it does:
- becomes the active OpenClaw memory backend when selected in `plugins.slots.memory`
- provides hybrid recall controls (FTS + vector) with scope-aware policies
- exposes bounded autoRecall / autoCapture controls and lifecycle receipts
- injects live-turn recall through `before_prompt_build` on current OpenClaw, with `before_agent_start` kept as a legacy fallback for older installs
- can optionally call `openclaw-mem route auto` before recall injection and add a compact routing hint block into live turns
- hosts the docs cold-lane ingest/search surfaces for operator-authored markdown
- can optionally auto-run **Wei Ji memory preflight** before `memory_store` writes

This package is the engine-role package inside the same `openclaw-mem` family:
- **`openclaw-mem`** = sidecar capture / observability / episodic spool / operator workflows
- **`openclaw-mem-engine`** = active memory slot backend

The marketplace split is there to keep install and rollback boundaries honest, not to imply two unrelated products.

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

## Prompt hook compatibility

`openclaw-mem-engine` now registers prompt mutation on both hook surfaces:
- primary: `before_prompt_build`
- fallback: `before_agent_start`

The plugin dedupes by run/session key so a newer OpenClaw that invokes both paths does not inject the same recall block twice.

## Route-auto prompt hook (optional)

If you want live turns to consult the graph/transcript router before normal memory recall, enable `autoRecall.routeAuto`.

Example host config:

```jsonc
{
  "plugins": {
    "entries": {
      "openclaw-mem-engine": {
        "enabled": true,
        "config": {
          "autoRecall": {
            "enabled": false,
            "routeAuto": {
              "enabled": true,
              "timeoutMs": 1800,
              "maxChars": 420,
              "maxGraphCandidates": 2,
              "maxTranscriptSessions": 2
            }
          }
        }
      }
    }
  }
}
```

Behavior:
- shells out to `openclaw-mem route auto "<prompt>"`
- if graph-semantic is ready and returns candidates, injects a compact graph-routing hint block
- when route-auto reports `preferredCardRefs` / `coveredRawRefs`, the hint prefers the fresh synthesis card while preserving the covered-raw receipt
- otherwise fails open to a compact transcript-recall hint block
- runtime failures/timeouts remain fail-open (the turn continues without the route block)

Rollback:
- set `plugins.entries.openclaw-mem-engine.config.autoRecall.routeAuto.enabled = false`
- restart the gateway

## Wei Ji memory preflight (optional)

`memory_store` can be guarded by Wei Ji before the engine writes memory into LanceDB.

Example host config:

```jsonc
{
  "plugins": {
    "entries": {
      "openclaw-mem-engine": {
        "enabled": true,
        "config": {
          "weijiMemoryPreflight": {
            "enabled": true,
            "command": "uv",
            "commandArgs": [
              "run",
              "--project",
              "/root/.openclaw/workspace/delirium-to-weiji",
              "weiji-memory-preflight"
            ],
            "dbPath": "/root/.openclaw/workspace/delirium-to-weiji/.state/d2w/verdicts.sqlite3",
            "timeoutMs": 12000,
            "failMode": "open",
            "failOnQueued": false,
            "failOnRejected": false
          }
        }
      }
    }
  }
}
```

Behavior:
- `enabled=false` (default): no Wei Ji subprocess call
- `failMode=open`: runtime/preflight execution failure does **not** block memory writes
- `failMode=closed`: runtime/preflight execution failure blocks the write
- `failOnQueued=true`: block when Wei Ji queues the write for review
- `failOnRejected=true`: block when Wei Ji rejects the write

Receipts:
- `memory_store.details.receipt.weiJiMemoryPreflight`

## Rollback

- Disable `plugins.entries.openclaw-mem-engine.config.weijiMemoryPreflight.enabled`
- Or switch `plugins.slots.memory` back to `memory-lancedb` or `memory-core`
- Restart the gateway after either change

## More context

See the repo docs for:
- `docs/mem-engine.md`
- `docs/ecosystem-fit.md`
- `docs/mem-engine-admin-ops.md`
