# OpenClaw Mem Engine plugin

`openclaw-mem-engine` is the **optional memory-slot backend** shipped alongside `openclaw-mem`.

What it does:
- becomes the active OpenClaw memory backend when selected in `plugins.slots.memory`
- provides hybrid recall controls (FTS + vector) with scope-aware policies
- exposes bounded autoRecall / autoCapture controls and lifecycle receipts
- frames live-turn bounded recall as **Proactive Pack**: pre-reply orchestration, not a separate hidden memory layer
- injects live-turn recall through `before_prompt_build` on current OpenClaw, with `before_agent_start` kept as a legacy fallback for older installs
- can optionally call `openclaw-mem route auto` before recall injection and add a compact routing hint block into live turns
- hosts the docs cold-lane ingest/search surfaces for operator-authored markdown
- can optionally auto-run **Wei Ji memory preflight** before `memory_store` writes
- can optionally write-through mirror each `memory_store` into a dedicated `gbrain` import root

This package is the engine-role package inside the same `openclaw-mem` family:
- **`openclaw-mem`** = sidecar capture / observability / episodic spool / operator workflows
- **`openclaw-mem-engine`** = active memory slot backend

Public contract: the prompt-build hook is a **Pack runtime mode**. In docs and operator language, call it **Proactive Pack**.

The marketplace split is there to keep install and rollback boundaries honest, not to imply two unrelated products.

## Install

### Local checkout

```bash
cd extensions/openclaw-mem-engine
npm install
cd ../..
openclaw plugins install -l ./extensions/openclaw-mem-engine
```

Why the extra step:
- this extension imports runtime Node dependencies such as `@sinclair/typebox`
- a source checkout needs its local `node_modules/` present before the gateway can load the plugin cleanly

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

If you want **Proactive Pack** live turns to consult the graph/transcript router before normal memory recall, enable `autoRecall.routeAuto`.

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

Operator bridge note:
- blocked receipts now surface Wei Ji `traceId` / `intent_id` so an approved review can be retried against the same governed write instead of opening a blind fresh queue item

## GBrain write-through mirror (optional)

If you want each successful `memory_store` to also land in `gbrain`, enable `gbrainMirror`.

This is separate from the experimental **GBrain sidecar** described in [`docs/experimental/gbrain-sidecar/README.md`](../../docs/experimental/gbrain-sidecar/README.md).
`gbrainMirror` is an engine-side write-through mirror for successful `memory_store` writes, not the read-only lookup / restricted helper-job bridge described in the sidecar doc.

Example host config:

```jsonc
{
  "plugins": {
    "entries": {
      "openclaw-mem-engine": {
        "enabled": true,
        "config": {
          "gbrainMirror": {
            "enabled": true,
            "mirrorRoot": "~/.openclaw/memory/gbrain-mirror",
            "command": "gbrain",
            "timeoutMs": 12000,
            "importOnStore": true
          }
        }
      }
    }
  }
}
```

Behavior:
- engine still writes LanceDB first, as canonical memory owner
- after `memory_store`, the plugin writes a dedicated markdown twin under `mirrorRoot/<memory-id>.md`
- when `importOnStore=true` (default), it runs `gbrain import <mirrorRoot> --workers 1`
- the subprocess inherits `OPENAI_API_KEY` from the engine config/env so gbrain embeddings do not silently fail on missing key
- failures are fail-open for the canonical write path, but receipts expose whether the mirror/import actually landed

Receipts:
- `memory_store.details.receipt.gbrainMirror`

## Rollback

- Disable `plugins.entries.openclaw-mem-engine.config.weijiMemoryPreflight.enabled`
- Or switch `plugins.slots.memory` back to `memory-lancedb` or `memory-core`
- Restart the gateway after either change

## More context

See the repo docs for:
- `docs/mem-engine.md`
- `docs/experimental/gbrain-sidecar/README.md`
- `docs/ecosystem-fit.md`
- `docs/mem-engine-admin-ops.md`
