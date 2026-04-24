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

2) Run conversation extraction on a short cadence (cron/systemd timer):

```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem episodes extract-sessions \
  --sessions-root ~/.openclaw/sessions \
  --file ~/.openclaw/memory/openclaw-mem-episodes.jsonl \
  --state ~/.openclaw/memory/openclaw-mem/episodes-extract-state.json \
  --payload-cap-bytes 4096 \
  --json
```

3) Run ingest in **follow mode** (recommended default):

```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem episodes ingest \
  --file ~/.openclaw/memory/openclaw-mem-episodes.jsonl \
  --state ~/.openclaw/memory/openclaw-mem/episodes-ingest-state.json \
  --conversation-payload-cap-bytes 4096 \
  --follow \
  --poll-interval-ms 1000 \
  --json
```

Useful follow flags:
- `--poll-interval-ms <N>`: idle polling interval (low CPU when idle; default `1000`, min `100`)
- `--idle-exit-seconds <N>`: optional auto-exit after N idle seconds (`0` = never; useful for supervised jobs/tests)
- `--rotate-on-idle-seconds <N>`: when fully caught up and idle, rotate the spool to keep it bounded (`0` = disabled)
- `--rotate-min-bytes <N>`: only rotate when spool size is at least N bytes (default: 1MB)
- follow mode uses a sibling lock file (e.g. `openclaw-mem-episodes.jsonl.lock`) to avoid racing writers during rotation
- `--follow` cannot be combined with `--truncate`/`--rotate` (maintenance actions stay batch-only)

---

## Safety defaults

- query/replay are summary-only by default (`--include-payload` is explicit)
- secret redaction always on
- PII-lite redaction (email/phone) enabled by default
- conversation capture strips runtime artifacts before spooling/ingest:
  - recalled-memory injection blocks
  - channel/sender metadata envelopes
  - internal delivery/result markers
  - assistant control-only replies such as `NO_REPLY`
  - media-delivery directives such as `MEDIA:`
- conversation payload default cap: 4096 bytes
- ingest hard payload ceiling: 8192 bytes
- if secret-like/tool-dump content still looks unsafe, payload is nulled and row marked `redacted=1`

Retention defaults:
- `conversation.user`: 60d
- `conversation.assistant`: 90d

---

## Verification

```bash
# Extract once + run ingest daemon (Ctrl+C to stop)
uv run --python 3.13 --frozen -- python -m openclaw_mem episodes extract-sessions --sessions-root ~/.openclaw/sessions --file ~/.openclaw/memory/openclaw-mem-episodes.jsonl --state ~/.openclaw/memory/openclaw-mem/episodes-extract-state.json --json
uv run --python 3.13 --frozen -- python -m openclaw_mem episodes ingest --file ~/.openclaw/memory/openclaw-mem-episodes.jsonl --state ~/.openclaw/memory/openclaw-mem/episodes-ingest-state.json --follow --poll-interval-ms 1000 --json

# Summary-only (default)
uv run --python 3.13 --frozen -- python -m openclaw_mem episodes query --global --limit 20 --json

# Payload opt-in
uv run --python 3.13 --frozen -- python -m openclaw_mem episodes query --global --limit 20 --include-payload --json
```

---

## Rollback

1. stop follow process/service (`Ctrl+C` or service stop)
2. switch back to periodic ingest pump (same command, without `--follow`)
3. if needed, set `plugins.entries.openclaw-mem.config.episodes.enabled=false`
4. restart gateway

No schema migration is required; ingest state file is shared between batch and follow modes.
Manual mode remains available.
