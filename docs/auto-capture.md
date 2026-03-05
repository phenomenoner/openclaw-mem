# Auto-Capture Plugin (`openclaw-mem`)

Status: **IMPLEMENTED (sidecar)**

## Overview

The OpenClaw plugin in `extensions/openclaw-mem/` now supports two parallel lanes:

1. **Observations lane** (existing)
   - listens to `tool_result_persist`
   - appends compact observation JSONL (`openclaw-mem-observations.jsonl`)
2. **Episodic auto lane** (new, optional)
   - emits bounded episodic events JSONL (`openclaw-mem-episodes.jsonl`)
   - ingested later by `openclaw-mem episodes ingest` into SQLite table `episodic_events`

The plugin remains sidecar-only (no slot ownership).

### Ecosystem boundaries

- `memory-core` / `memory-lancedb` stay canonical slot backends.
- `openclaw-mem` provides capture + local ingest/query + auditability.

For backend-layer auto recall/capture, use optional `openclaw-mem-engine` (`docs/mem-engine.md`).

---

## Features

✅ Observation auto-capture JSONL  
✅ Episodic auto spool (tool.call / tool.result / ops.alert)  
✅ Summary-first bounded payload/refs  
✅ Secret/output guardrails  
✅ Deterministic offset-based episodic ingest receipts

---

## Installation

Plugin source: `extensions/openclaw-mem/`

```bash
ln -s "$(pwd)/extensions/openclaw-mem" ~/.openclaw/plugins/openclaw-mem
openclaw gateway restart
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
          "captureMessage": false,
          "maxMessageLength": 1000,
          "redactSensitive": true,
          "backendMode": "auto",
          "annotateMemoryTools": true,
          "memoryToolNames": ["memory_search", "memory_get", "memory_store", "memory_recall", "memory_forget"],
          "includeTools": [],
          "excludeTools": ["web_fetch"],
          "episodes": {
            "enabled": true,
            "outputPath": "~/.openclaw/memory/openclaw-mem-episodes.jsonl",
            "scope": "global",
            "captureToolCall": true,
            "captureToolResult": true,
            "captureOpsAlert": true,
            "payloadCapBytes": 2048,
            "refsCapBytes": 1024,
            "maxSummaryLength": 220
          }
        }
      }
    }
  }
}
```

Important:
- If using `OPENCLAW_STATE_DIR`, keep both spool paths under that state dir.
- Episodic auto mode is feature-flagged via `episodes.enabled` (default false).

---

## Manual mode vs auto mode

### Manual mode

```bash
openclaw-mem episodes append ...
openclaw-mem episodes query ...
openclaw-mem episodes replay <session_id> ...
```

### Auto mode

1) enable `config.episodes.enabled=true`  
2) ingest episodic spool on schedule:

```bash
uv run python -m openclaw_mem episodes ingest \
  --file ~/.openclaw/memory/openclaw-mem-episodes.jsonl \
  --state ~/.openclaw/memory/openclaw-mem/episodes-ingest-state.json \
  --json
```

Optional spool maintenance in same command:
- `--truncate`
- `--rotate`

Both are safe-guarded to only apply after full snapshot consumption.

---

## What auto mode captures (v0)

Captured:
- `tool.call`
- `tool.result`
- `ops.alert`

Not captured by default:
- full conversation transcripts
- raw stdout/stderr blobs

Safety posture: summary-first, bounded payload, no raw tool output persistence by default.

---

## Verification

```bash
# 1) trigger some tool usage in OpenClaw
# 2) run ingest
uv run python -m openclaw_mem episodes ingest --file ~/.openclaw/memory/openclaw-mem-episodes.jsonl --state ~/.openclaw/memory/openclaw-mem/episodes-ingest-state.json --json

# 3) query latest episodic rows
uv run python -m openclaw_mem episodes query --global --limit 20 --json
```

Expected:
- ingest receipt `inserted` increases after activity
- query `count` grows

---

## Troubleshooting

### Plugin not capturing

1. `openclaw plugins list | grep openclaw-mem`
2. `openclaw config get | jq '.plugins.entries["openclaw-mem"]'`
3. `tail -f ~/.openclaw/logs/gateway.log | grep openclaw-mem`

### Episodic ingest not moving

- Check state offset file exists and updates.
- Check spool has newline-terminated lines.
- Query receipt fields: `invalid_json`, `invalid_event`, `duplicates`, `trailing_partial_bytes`.

### JSONL growing too large

- tighten include/exclude tool filters
- keep `captureMessage=false`
- schedule `episodes ingest --rotate` or external log rotation

---

## References

- `docs/specs/episodic-events-ledger-v0.md`
- `docs/specs/episodic-auto-capture-v0.md`
- `docs/deployment.md`
