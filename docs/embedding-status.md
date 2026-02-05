# Embedding Availability & Status

## Problem
The plugin relies on OpenClaw's native embedding provider for vector search. If embeddings are unavailable (no API key, provider disabled, or offline mode), the plugin should gracefully fall back to FTS-only mode.

## Solution: Runtime Detection + Status Reporting

### 1. Detection Order
On plugin init or first index operation:

1. Check OpenClaw `memorySearch` config for embedding provider
2. If configured → attempt to generate a test embedding
3. If successful → enable vector index
4. If failed or unconfigured → disable vector index, log warning, continue in FTS-only mode

### 2. Status Command Output
The `openclaw-mem status --json` command should report:

```json
{
  "db": "/home/agent/.openclaw/memory/openclaw-mem.sqlite",
  "count": 1234,
  "min_ts": "2026-02-01T00:00:00Z",
  "max_ts": "2026-02-05T19:00:00Z",
  "embedding": {
    "available": true,
    "provider": "openai",
    "model": "text-embedding-3-small",
    "fingerprint": "openai:text-embedding-3-small:v1"
  },
  "index": {
    "fts": true,
    "vector": true,
    "last_rebuild": "2026-02-05T18:00:00Z"
  }
}
```

If embeddings are unavailable:

```json
{
  ...
  "embedding": {
    "available": false,
    "reason": "No embedding provider configured"
  },
  "index": {
    "fts": true,
    "vector": false
  }
}
```

### 3. Fallback Behavior
- **FTS-only mode**: All searches use SQLite FTS5
- **Hybrid mode** (when embeddings available): Combine vector similarity + BM25 scoring

### 4. Environment Variable Override
For testing or CI environments without embeddings:

```bash
OPENCLAW_MEM_DISABLE_VECTOR=1 openclaw-mem status --json
```

### 5. Embedding Fingerprint
Track which embedding model was used to build the index. If the model changes, rebuild the index:

```sql
CREATE TABLE IF NOT EXISTS index_meta (
  key TEXT PRIMARY KEY,
  value TEXT
);

INSERT OR REPLACE INTO index_meta (key, value)
VALUES ('embedding_fingerprint', 'openai:text-embedding-3-small:v1');
```

On startup, compare fingerprint. If mismatch → warn and offer `openclaw-mem index --rebuild`.

## Implementation Status
- ✅ FTS5 index working (M0)
- ⏳ Vector index (Phase 3)
- ⏳ Hybrid scoring (Phase 3)
- ⏳ Status reporting (Phase 2)

## Next Steps
1. Add embedding detection to plugin init
2. Extend `status` command with embedding info
3. Implement hybrid search with weight tuning (`--text-weight`, `--vector-weight`)
