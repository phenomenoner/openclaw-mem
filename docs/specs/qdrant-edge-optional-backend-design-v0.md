# Qdrant Edge optional backend design v0

Date: 2026-05-09 (Asia/Taipei)
Status: Draft design gate

## Verdict
Qdrant Edge should be designed as an optional local retrieval backend for read-heavy RAG workloads. It should not replace LanceDB as the default backend until lifecycle and fallback gates pass.

## Evidence summary
Production-embedding parity gates using the same documents and vectors showed retrieval parity with LanceDB and substantially lower Qdrant Edge query latency.

Largest current receipt:

- Workload: LongMemEval 50-question sample, 2,436 unique documents, top-k 10
- Embeddings: `text-embedding-3-small`, 1,536 dimensions
- LanceDB: hit@10 0.56, MRR 0.2890, nDCG@10 0.3538, p50/p95 search 58.45/139.60 ms, ingest 1086.64 ms
- Qdrant Edge: hit@10 0.56, MRR 0.2894, nDCG@10 0.3541, p50/p95 search 3.98/6.32 ms, ingest 1828.53 ms
- Local footprint: 177 MB run dir; 76 MB embedding cache; 38 MB LanceDB state; 63 MB Qdrant Edge state

## Intended role
Qdrant Edge is an index/cache backend, not a canonical memory store.

Canonical truth remains in the existing durable memory/docs/WAL stores. Qdrant Edge shards must be rebuildable from canonical records and disposable without data loss.

## Backend boundary
Introduce Qdrant Edge behind a backend-selection boundary equivalent to:

```text
canonical records/chunks
  -> embedding pipeline
  -> retrieval backend adapter
      - LanceDB default
      - Qdrant Edge optional
  -> SearchHit-compatible results
  -> pack/context assembly
```

The adapter must produce the existing benchmark/runtime result shape:

```json
{
  "id": "string",
  "content": "string",
  "score": 0.0,
  "metadata": {
    "session_id": "string|null",
    "source": "string|null",
    "scope": "string|null",
    "category": "string|null"
  }
}
```

## Configuration shape
Draft only; do not enable by default:

```json
{
  "backend": "lancedb",
  "qdrantEdge": {
    "enabled": false,
    "shardRoot": "artifacts/provider-state/qdrant-edge",
    "vectorName": "text",
    "optimizeOnRebuild": true,
    "fallbackBackend": "lancedb"
  }
}
```

Production configuration must use a private runtime path for shard state; public docs should avoid machine-specific absolute paths.

## Required lifecycle gates before default adoption

### 1. Rebuild gate
- Build a shard from canonical records only.
- Delete the shard and rebuild it deterministically.
- Verify same document count and comparable top-k results.
- Measure rebuild time and final state size.

### 2. Incremental update gate
- Upsert new records.
- Update changed records.
- Delete or tombstone removed records.
- Verify query results reflect each operation without full rebuild.

### 3. Fallback gate
- Simulate missing package, corrupt/missing shard, dimension mismatch, and query exception.
- Verify fallback to LanceDB or current backend.
- Verify no canonical data is lost.

### 4. Cleanup gate
- Remove Qdrant Edge shard/cache directories.
- Verify no live config or canonical store is affected.
- Verify no orphaned handles prevent deletion after close.

### 5. Dependency gate
- Pin compatible package versions for the supported Python runtime.
- Record wheel/platform constraints.
- Verify import smoke in a clean isolated environment.

### 6. Public artifact gate
- Public-facing docs must not contain private names, secrets, private absolute paths, or unsanitized memory text.
- Machine reports can remain local-only; publish only sanitized summaries.
- See `qdrant-edge-lifecycle-gates-v0.md` for the verifier shape.

## Implementation pointer
Qdrant Edge implementation should land behind the retrieval backend adapter boundary and remain disabled by default until the lifecycle gates in `qdrant-edge-lifecycle-gates-v0.md` pass in the target runtime.

## Adoption recommendation
Move to optional backend design and lifecycle validation. Do not make Qdrant Edge the default backend yet.

Lifecycle smoke status: the six-gate verifier (`rebuild`, `incremental update`, `fallback`, `cleanup`, `dependency`, and `public artifact hygiene`) passed on a small deterministic fixture. This supports continuing optional-backend design work. A larger lifecycle/load run is still required before enabling it by default.

A default switch becomes reasonable only if:

- lifecycle gates pass,
- fallback is proven,
- repeated representative workloads keep quality at parity or better,
- query-latency gains matter to a product path,
- ingest/state overhead is acceptable for expected usage.

## Rollback
Disable the optional backend and delete Qdrant Edge shard/cache directories. Continue using LanceDB/current backend. Because Qdrant Edge is only an index/cache, rollback must not require data migration.
