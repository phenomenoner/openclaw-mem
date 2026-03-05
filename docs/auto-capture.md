# Auto-Capture Plugin (`openclaw-mem`)

Status: **IMPLEMENTED (sidecar)**

## Overview

`openclaw-mem` auto mode now has two capture lanes feeding one episodic spool:

1. **Plugin lane** (`extensions/openclaw-mem`)
   - captures `tool.call` / `tool.result` / `ops.alert`
2. **Conversation lane** (`episodes extract-sessions`)
   - tails OpenClaw `sessions/*.jsonl`
   - emits `conversation.user` / `conversation.assistant`

Both lanes write JSONL spool lines, then `episodes ingest` writes deterministic rows into SQLite `episodic_events`.

---

## Manual mode vs auto mode

### Manual mode

```bash
openclaw-mem episodes append ...
openclaw-mem episodes query ...
openclaw-mem episodes replay <session_id> ...
```

### Auto mode (recommended)

1) Enable plugin episodic lane in `~/.openclaw/openclaw.json`:

```jsonc
{
  "plugins": {
    "entries": {
      "openclaw-mem": {
        "enabled": true,
        "config": {
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

2) Schedule conversation extraction:

```bash
uv run python -m openclaw_mem episodes extract-sessions \
  --sessions-root ~/.openclaw/sessions \
  --file ~/.openclaw/memory/openclaw-mem-episodes.jsonl \
  --state ~/.openclaw/memory/openclaw-mem/episodes-extract-state.json \
  --payload-cap-bytes 4096 \
  --json
```

3) Schedule ingest:

```bash
uv run python -m openclaw_mem episodes ingest \
  --file ~/.openclaw/memory/openclaw-mem-episodes.jsonl \
  --state ~/.openclaw/memory/openclaw-mem/episodes-ingest-state.json \
  --conversation-payload-cap-bytes 4096 \
  --json
```

---

## Safety defaults

- query/replay are summary-only by default (`--include-payload` is explicit)
- secret redaction always on
- PII-lite redaction (email/phone) enabled by default
- conversation payload default cap: 4096 bytes
- ingest hard payload ceiling: 8192 bytes
- if secret-like/tool-dump content still looks unsafe, payload is nulled and row marked `redacted=1`

Retention defaults:
- `conversation.user`: 60d
- `conversation.assistant`: 90d

---

## Verification

```bash
# Extract + ingest once
uv run python -m openclaw_mem episodes extract-sessions --sessions-root ~/.openclaw/sessions --file ~/.openclaw/memory/openclaw-mem-episodes.jsonl --state ~/.openclaw/memory/openclaw-mem/episodes-extract-state.json --json
uv run python -m openclaw_mem episodes ingest --file ~/.openclaw/memory/openclaw-mem-episodes.jsonl --state ~/.openclaw/memory/openclaw-mem/episodes-ingest-state.json --json

# Summary-only (default)
uv run python -m openclaw_mem episodes query --global --limit 20 --json

# Payload opt-in
uv run python -m openclaw_mem episodes query --global --limit 20 --include-payload --json
```

---

## Rollback

1. set `plugins.entries.openclaw-mem.config.episodes.enabled=false`
2. disable extractor + ingest jobs
3. restart gateway

Manual mode remains available.
