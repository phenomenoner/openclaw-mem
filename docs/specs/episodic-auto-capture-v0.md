# Episodic Auto-Capture v0 (tool/alert + conversation fallback)

Status: **IMPLEMENTED (dev)**

Owner: `openclaw-mem` sidecar plugin + CLI

## 1) Architecture

Auto mode is rollbackable and split into lanes:

1. **Plugin lane** (`extensions/openclaw-mem`)
   - auto-emits episodic spool JSONL for:
     - `tool.call`
     - `tool.result`
     - `ops.alert`
2. **Conversation extractor lane** (`openclaw-mem episodes extract-sessions`)
   - tails OpenClaw `sessions/*.jsonl`
   - emits:
     - `conversation.user`
     - `conversation.assistant`
   - uses per-file offset+inode state (`episodes-extract-state.json`)
3. **Ingest lane** (`openclaw-mem episodes ingest`)
   - consumes spool with offset state (`episodes-ingest-state.json`)
   - inserts deterministic rows into `episodic_events`

---

## 2) Safety policy (defaults)

- Query/replay are **summary-only by default**.
  - Payload is returned only with explicit `--include-payload`.
- Secret-like redaction is always on.
- PII-lite redaction (email/phone) is enabled by default.
- Payload policy:
  - conversation payload default cap: **4096 bytes**
  - ingest hard ceiling: **8192 bytes**
- If content still looks secret-like after redaction, or clearly looks like a tool dump,
  ingest stores `payload_json = NULL` and `redacted = 1`.

---

## 3) Scope derivation

For conversation extraction:

- parse leading tag in message text: `[SCOPE: x]`
- if absent, fallback scope = `global`

---

## 4) Retention defaults

`episodes gc` default policy:

- `conversation.user`: **60d**
- `conversation.assistant`: **90d**
- `tool.call`: 30d
- `tool.result`: 30d
- `ops.alert`: 90d
- `ops.decision`: forever

---

## 5) Enablement

### Plugin config (tool/alert lane)

`plugins.entries["openclaw-mem"].config.episodes`:

```jsonc
{
  "enabled": true,
  "outputPath": "memory/openclaw-mem-episodes.jsonl",
  "scope": "global",
  "captureToolCall": true,
  "captureToolResult": true,
  "captureOpsAlert": true,
  "payloadCapBytes": 2048,
  "refsCapBytes": 1024,
  "maxSummaryLength": 220
}
```

### Conversation extractor lane

```bash
openclaw-mem episodes extract-sessions \
  --sessions-root ~/.openclaw/sessions \
  --file ~/.openclaw/memory/openclaw-mem-episodes.jsonl \
  --state ~/.openclaw/memory/openclaw-mem/episodes-extract-state.json \
  --payload-cap-bytes 4096 \
  --json
```

### Ingest lane

```bash
openclaw-mem episodes ingest \
  --file ~/.openclaw/memory/openclaw-mem-episodes.jsonl \
  --state ~/.openclaw/memory/openclaw-mem/episodes-ingest-state.json \
  --conversation-payload-cap-bytes 4096 \
  --json
```

---

## 6) Cron wiring (example)

Every 2 minutes, silent on green:

```bash
*/2 * * * * cd /opt/openclaw-mem && uv run --python 3.13 -- python -m openclaw_mem episodes extract-sessions --sessions-root ~/.openclaw/sessions --file ~/.openclaw/memory/openclaw-mem-episodes.jsonl --state ~/.openclaw/memory/openclaw-mem/episodes-extract-state.json --json >/dev/null 2>&1
*/2 * * * * cd /opt/openclaw-mem && uv run --python 3.13 -- python -m openclaw_mem episodes ingest --file ~/.openclaw/memory/openclaw-mem-episodes.jsonl --state ~/.openclaw/memory/openclaw-mem/episodes-ingest-state.json --conversation-payload-cap-bytes 4096 --json >/dev/null 2>&1
```

---

## 7) Rollback

Immediate rollback:

1. set `plugins.entries.openclaw-mem.config.episodes.enabled=false`
2. disable extractor + ingest cron jobs
3. restart gateway

Manual episodic mode remains available (`append/query/replay/redact/gc`).
