# Qdrant Edge lifecycle gates v0

Date: 2026-05-09 (Asia/Taipei)
Status: Draft verifier plan

## Goal
Verify whether Qdrant Edge is operationally safe enough to continue from benchmark candidate into optional backend implementation design.

## Non-goals
- Do not enable Qdrant Edge as the default backend.
- Do not modify live OpenClaw or gateway configuration.
- Do not expose server ports or run Qdrant Server.
- Do not treat Qdrant Edge as a canonical data store.

## Inputs
- Existing benchmark dataset fixtures.
- Existing parity harness for LanceDB and Qdrant Edge.
- Local isolated Python environment with Qdrant Edge and LanceDB dependencies.

## Outputs
- Machine-readable lifecycle report JSON.
- Human-readable sanitized report Markdown.
- Updated decision docs if gate results change the recommendation.

## Invariants
- Canonical records remain outside Qdrant Edge.
- Qdrant Edge state is disposable and rebuildable.
- LanceDB/current backend remains the fallback.
- Public docs must not contain private names, secrets, private absolute paths, or unsanitized memory text.

## Gates

### 1. Rebuild gate
Build a shard from canonical benchmark documents, delete it, rebuild it, and verify:
- document count matches;
- top-k results match for selected queries;
- rebuild time and state size are recorded.

### 2. Incremental update gate
On an existing shard, verify:
- upsert of a new document;
- update of an existing document;
- delete/tombstone of a document;
- query results reflect each operation.

### 3. Fallback gate
Simulate bounded failures:
- missing/corrupt shard;
- dimension mismatch;
- package unavailable or import failure where safely simulatable;
- query exception.

The gate passes only if the harness either succeeds through the declared fallback backend or records a typed, bounded error without mutating canonical data.

### 4. Cleanup gate
Close all handles, delete shard/cache directories, and verify:
- state directory is removed;
- repeated cleanup is idempotent;
- no canonical records are removed.

### 5. Dependency gate
Record:
- Python version;
- Qdrant Edge package version;
- LanceDB package/version source;
- platform and architecture;
- import smoke result.

### 6. Public artifact hygiene gate
Scan public-facing docs and new code artifacts for private names, API keys, tokens, OAuth secrets, private absolute paths, and raw authorization strings. Reports must be sanitized summaries.

## Verifier command
Expected local command shape:

```bash
PYTHONPATH=src:/path/to/vendor_lancedb python scripts/run_qdrant_edge_lifecycle_gates.py \
  --dataset examples/mini_retrieval.json \
  --out-dir artifacts/qdrant-edge-lifecycle-smoke
```

`/path/to/vendor_lancedb` is a placeholder for the local LanceDB package/vendor checkout used by the verifier environment. A larger run may use `data/datasets/longmemeval-50.json`, but the first lifecycle verifier should be small, deterministic, and fast.

## Rollback
Delete lifecycle artifact directories and any Qdrant Edge provider-state directories. No live configuration should have changed.
