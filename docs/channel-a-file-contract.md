# Channel A file contract

Channel A is the offline file-based ContextPack producer path for host agents.

It exists so a host can keep running even when online MCP recall is unavailable:

1. ingest local JSONL observations idempotently
2. build a bounded ContextPack v1
3. write `<packs-dir>/<agent>/latest.json`
4. let the host skip missing or invalid files fail-open

## Command

```bash
openclaw-mem-channel-a \
  --db /path/to/openclaw-mem.sqlite \
  --input-jsonl /path/to/observations.jsonl \
  --packs-dir /path/to/packs \
  --agent main \
  --query "current session memory" \
  --limit 8 \
  --budget-tokens 1200
```

The pack uses:

```json
{"schema": "openclaw-mem.context-pack.v1"}
```

## Observation JSONL shape

```json
{"observationId":"obs-001","kind":"decision","text":"Keep ContextPack v1 stable.","ts":"2026-06-12T00:00:00Z"}
```

Rules:

- `observationId` is the idempotency key
- duplicate ids are skipped on retry
- UTF-8 BOM JSONL input is accepted
- `text` is required; legacy `summary` is not silently promoted to memory text
- `<private>`, `[NOEXPORT]`, `[PRIVATE]`, and `[NOMEM]` rows are skipped
- invalid rows are skipped and counted in the receipt

Migration note: producers that previously emitted only `summary` must emit `text`
before relying on Channel A injection. Rows without `text` are treated as invalid
instead of being converted implicitly.

## Shared fixtures

Compatibility fixtures live in `docs/fixtures/context-pack-v1-compat/`.

They cover legal, oversized, missing-required-field, and ingest-idempotency cases.

## Verification

```bash
uv run --python 3.13 --frozen pytest tests/test_channel_a.py tests/test_context_pack_v1_compat_fixtures.py
```
