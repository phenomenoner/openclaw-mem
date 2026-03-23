# OpenClaw Mem plugin

`openclaw-mem` is the **OpenClaw observation-capture plugin** that feeds the wider `openclaw-mem` workflow.

What it does:
- captures tool results into JSONL for later ingest
- can optionally spool bounded episodic events (including conversations)
- can annotate memory-tool activity for backend-aware receipts

This package is the **sidecar capture plugin**, not the optional memory-slot backend.
If you want the slot-owner lane, that is `openclaw-mem-engine` and it remains a separate, more opinionated surface.

## Install

### Local checkout

```bash
openclaw plugins install -l ./extensions/openclaw-mem
```

### Marketplace package

After publishing to ClawHub package marketplace:

```bash
openclaw plugins install @phenomenoner/openclaw-mem
```

## Minimal config

Add under `plugins.entries.openclaw-mem.config` in `openclaw.json`:

```jsonc
{
  "plugins": {
    "entries": {
      "openclaw-mem": {
        "enabled": true,
        "config": {
          "outputPath": "memory/openclaw-mem-observations.jsonl",
          "captureMessage": false,
          "redactSensitive": true,
          "backendMode": "auto",
          "annotateMemoryTools": true,
          "excludeAgents": ["cron-watchdog", "healthcheck"]
        }
      }
    }
  }
}
```

## Rollback

Disable the entry or uninstall the package. The native memory slot stays untouched because this plugin is sidecar-only.

## More context

See the repo root docs for:
- install modes
- trust model / ownership boundary
- `openclaw-mem-engine` slot-backend posture
