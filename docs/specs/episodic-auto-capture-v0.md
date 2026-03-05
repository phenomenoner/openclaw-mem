# Episodic Auto-Capture v0 (spool + deterministic ingest)

Status: **IMPLEMENTED (dev)**

Owner: `openclaw-mem` sidecar plugin + CLI

## 1) What this adds

`openclaw-mem` now supports an **episodic auto mode** that is intentionally split into two stages:

1. **Node plugin capture** (`extensions/openclaw-mem`)
   - emits bounded episodic event JSONL lines to a local spool file
   - does **not** write SQLite directly
2. **Python ingest** (`openclaw-mem episodes ingest`)
   - reads only new bytes (offset state file)
   - appends deterministic rows into `episodic_events`

This keeps runtime writes simple and rollback-safe while preserving deterministic receipts.

---

## 2) Captured vs not captured (v0)

### Captured automatically

- `tool.call` (synthetic from `tool_result_persist` context)
- `tool.result`
- `ops.alert`
  - tool-result failure-pattern alerts (bounded signal only)
  - `agent_end` unsuccessful turn alert

### Not captured automatically (default)

- full conversation transcripts (`conversation.user` / `conversation.assistant`)
- raw tool stdout/stderr payloads
- unbounded tool result blobs

Conversation events remain **manual mode** in v0 (`episodes append`) unless explicitly added in future revisions.

---

## 3) Safety posture

Default posture is **summary-first + bounded payloads**:

- summary is short, redaction-aware text
- payload/refs are bounded by byte caps
- known output-like fields (`stdout`, `stderr`, etc.) are dropped/redacted before insert
- ingest applies guardrails against secret-like or tool-output-like fragments
- SQLite query remains summary-only unless `--include-payload` is requested

No raw stdout/stderr storage by default.

---

## 4) Config knobs (plugin)

`~/.openclaw/openclaw.json` under `plugins.entries["openclaw-mem"].config.episodes`:

```jsonc
{
  "enabled": false,
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

Notes:
- `enabled=false` is the safe default (feature-flag rollback path).
- `outputPath` is resolved under effective OpenClaw state dir when relative.

---

## 5) Ingest command + state model

```bash
openclaw-mem episodes ingest \
  --file ~/.openclaw/memory/openclaw-mem-episodes.jsonl \
  --state ~/.openclaw/memory/openclaw-mem/episodes-ingest-state.json \
  --json
```

State file schema: `openclaw-mem.episodes.ingest.state.v0`

Core behavior:
- reads from `offset` → current snapshot end
- ingests only complete lines (trailing partial line waits for next run)
- skips invalid JSON lines and invalid events with bounded error sample
- dedupe via unique `event_id`
- deterministic receipt includes processed SHA-256 and counters

Optional maintenance flags:
- `--truncate`: truncate spool only when fully consumed and unchanged during run
- `--rotate`: rotate spool to timestamped `.ingested` file only when fully consumed and unchanged

---

## 6) Cron wiring (example)

Every 2 minutes, silent on green:

```bash
*/2 * * * * cd /opt/openclaw-mem && uv run --python 3.13 -- python -m openclaw_mem episodes ingest --file ~/.openclaw/memory/openclaw-mem-episodes.jsonl --state ~/.openclaw/memory/openclaw-mem/episodes-ingest-state.json --json >/dev/null 2>&1
```

Optional daily spool rotation (if you prefer file GC in same command):

```bash
5 0 * * * cd /opt/openclaw-mem && uv run --python 3.13 -- python -m openclaw_mem episodes ingest --file ~/.openclaw/memory/openclaw-mem-episodes.jsonl --state ~/.openclaw/memory/openclaw-mem/episodes-ingest-state.json --rotate --json >/dev/null 2>&1
```

---

## 7) Rollback

Immediate rollback (no schema drop):
1. set `plugins.entries.openclaw-mem.config.episodes.enabled=false`
2. disable/stop ingest cron job

Manual-mode episodic commands continue to work:
- `episodes append/query/replay/redact/gc`

No DB migration rollback is required for disable-only rollback.
