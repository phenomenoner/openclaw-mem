# RAG backend Qdrant Edge A/B blade map v0

Date: 2026-05-09 (Asia/Taipei)
Status: Experimental design note

## Verdict
Proceed with an experimental backend/benchmark lane inside the `openclaw-mem` product line, not as a live default backend and not as a separate product truth source.

## Goal
Determine, with verifier-backed artifacts, whether Qdrant Edge is worth adopting alongside or instead of the current LanceDB-backed local RAG/retrieval path for OpenClaw/openclaw-mem workflows.

## Non-goals
- Do not replace the canonical memory truth store.
- Do not enable Qdrant Server or expose ports.
- Do not change live OpenClaw gateway config or default memory backend during the spike.
- Do not vendor Qdrant source into this repo.
- Do not claim adoption without benchmark receipts.

## Boundary
Implement the smallest rollbackable spike that can compare LanceDB vs Qdrant Edge under a shared retrieval contract. The spike may live in `openclaw-memory-bench` if that is the shortest verifier path, with product-facing docs/spec in `openclaw-mem`.

## Inputs
- Existing LanceDB benchmark/runtime receipts, when available locally.
- Existing memory benchmark datasets and runners under `openclaw-memory-bench`.
- Qdrant Edge Python binding availability check (`qdrant-edge-py`, the upstream PyPI package name used in this spike) via uv/pip in an isolated environment, no live runtime install unless separately approved.
- Representative query sets: memory/docs/ops/repo-surgery/coding-context where available; otherwise LongMemEval smoke first.

## Outputs / artifacts
- Product spec: this file.
- Dependency feasibility receipt: package availability/import smoke for Qdrant Edge, isolated from live runtime.
- Adapter contract note: common fields and result schema for LanceDB/Qdrant Edge comparison.
- Benchmark artifacts: JSON + Markdown report comparing LanceDB baseline vs Qdrant Edge experimental path.
- Decision artifact: adopt / defer / reject with evidence.
- Rollback note: all Qdrant Edge state is deletable cache under `.state`, no live backend switch.

## Invariants
- Markdown/SQLite/WAL/docs remain canonical truth.
- Retrieval backend is an index/cache, never authority.
- LanceDB remains the default until Qdrant Edge wins on named criteria.
- Failure of Qdrant Edge must degrade to existing LanceDB/SQLite paths.
- No external service, port, or server topology for the first spike.

## Topology/config impact
Unchanged for the initial spike. Any later live backend switch requires a new config spec, dry-run, readback, and live smoke.

## Backend comparison hypothesis
- LanceDB likely wins on current OpenClaw runtime fit, Node/TS plugin integration, existing receipts, and low ops friction.
- Qdrant Edge may win on payload-filter semantics, local shard/collection model, future Qdrant Server migration, and vector-search quality under constrained filters.
- Adoption is only justified if Qdrant Edge demonstrates a retrieval-quality or strategic-upgrade win large enough to pay dependency/runtime complexity.

## Fairness requirements from independent review
The first spike may prove Qdrant Edge mechanics with a deterministic local `hash_embed` vectorizer, but that smoke **must not** be used as an adoption-quality result. A real adoption A/B must compare apples to apples:

- same source documents/chunks
- same embedding provider/model/dimension
- same query vectors
- same top-k and scoring pipeline
- same required metadata mapping into `SearchHit`, especially `metadata.session_id`
- same privacy/sanitization posture for artifacts

If LanceDB is measured through live OpenClaw `memory_recall` while Qdrant Edge is measured as a raw shard, the report must label this as a surface comparison, not backend quality proof.

## Shared result contract draft
The product-level result contract is richer, but current `openclaw-memory-bench` scoring requires every backend to map into `SearchHit(id, content, score, metadata)`. At minimum, `metadata.session_id` must be present for retrieval metrics.

Each richer backend result should be mappable to:

```json
{
  "id": "string",
  "score": 0.0,
  "distance": 0.0,
  "text": "string",
  "source": "string",
  "scope": "string|null",
  "category": "string|null",
  "createdAt": "string|number|null",
  "payload": {}
}
```

Benchmark reports must include hit@k, recall@k, precision@k, MRR, NDCG, p50/p95 latency, index build time where available, dependency/runtime notes, and a qualitative failure table.

## Embedding contract
For mechanics smoke only:
- `embedder=hash_embed`, deterministic local lexical vectorizer
- dimension default: 384
- purpose: prove Qdrant Edge shard lifecycle, payload filter, adapter mapping, and benchmark integration
- limitation: not semantic-quality proof

For adoption A/B:
- pin the exact embedding provider/model/dimension and normalization
- use the same document vectors and query vectors for LanceDB and Qdrant Edge
- cache vectors under a local benchmark artifact directory such as `artifacts/provider-state/rag-backend-ab/<run-id>/vectors/`
- record embedding failures separately from backend failures

## Privacy / artifact policy
Benchmark artifacts are local-only by default. Human-facing Markdown must summarize metrics and failure modes without dumping private memory text. JSON artifacts may contain dataset or local memory text and should stay under local benchmark artifact roots unless explicitly sanitized for publication.

## Verifier plan
### Dry-run
1. Inspect existing LanceDB benchmark/runtime receipts.
2. Isolated Qdrant Edge dependency/import smoke; no live runtime mutation.
3. If package is unavailable or incompatible, record blocker and stop before code integration.

### Counterfactuals
- Qdrant package missing: benchmark must mark backend unavailable, not crash.
- Empty shard/query: bounded empty result receipt.
- Dimension mismatch: bounded error receipt.
- Backend unavailable: LanceDB/current path remains usable.
- Filter mismatch: compare scope/category payload filtering against expected IDs.

### Live smoke
Not in first spike. A later optional backend switch requires a separate live smoke after config enablement.

### Human-readable report
Write concise Markdown report derived from JSON artifacts only; include adoption recommendation and remaining risks.

## Current spike status
The first implementation slice should be interpreted as a mechanics and parity smoke, not a production adoption decision:

- Qdrant Edge can run local-first through `qdrant-edge-py` in an isolated Python environment.
- A benchmark adapter can map Qdrant Edge results into the existing `SearchHit` protocol.
- A same-document/same-vector parity harness can compare in-memory reference, LanceDB, and Qdrant Edge using deterministic local vectors.
- On a small LongMemEval smoke sample, LanceDB and Qdrant Edge produced identical retrieval metrics with the same vectors; Qdrant Edge had lower query latency but higher ingest overhead in that run.
- A follow-up production-embedding parity smoke using `text-embedding-3-small` on a 20-question LongMemEval sample also produced identical retrieval quality for LanceDB and Qdrant Edge. Qdrant Edge showed substantially lower query latency and higher ingest overhead.
- A larger production-embedding parity gate using `text-embedding-3-small` on a 50-question LongMemEval workload also supported parity: LanceDB and Qdrant Edge had equal hit/precision/recall, with Qdrant Edge slightly ahead on MRR/nDCG. Qdrant Edge search latency was much lower, while ingest and local state size were higher.

This is enough to move Qdrant Edge into optional backend design for read-heavy local RAG. It is not enough to make it the default backend. The next adoption-grade slice should cover rebuild/update/delete behavior, cache/state cleanup, dependency friction, and operational fallback cost.

### Larger gate receipt summary

Workload: LongMemEval 50-question sample, 2,436 unique documents, top-k 10, `text-embedding-3-small`, 1,536-dimensional vectors.

| backend | hit@10 | precision@10 | recall@10 | MRR | nDCG@10 | search p50 ms | search p95 ms | ingest ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| LanceDB | 0.56 | 0.056 | 0.56 | 0.2890 | 0.3538 | 58.45 | 139.60 | 1086.64 |
| Qdrant Edge | 0.56 | 0.056 | 0.56 | 0.2894 | 0.3541 | 3.98 | 6.32 | 1828.53 |

Observed local artifact/state footprint for that run: 177 MB total; 76 MB embedding cache; 38 MB LanceDB state; 63 MB Qdrant Edge state.

## Cross-validation plan
- Independent design review focused on product fit, hidden risks, and adoption criteria.
- Independent implementation review focused on the smallest code path and verifier quality.

## Adoption criteria
Adopt Qdrant Edge as optional backend only if all gate requirements pass and at least one win condition is true.

Gate requirements:
- Qdrant Edge imports and runs in isolated Python 3.13/Linux x64 with no live OpenClaw runtime mutation.
- Same docs, vectors, top-k, and scoring pipeline as the LanceDB/backend baseline for adoption A/B.
- Valid JSON report plus Markdown summary generated from JSON only.
- p95 latency and rebuild/index time stay inside local-ops budget declared in the run manifest.
- Cache is fully deletable under `.state`; fallback to current LanceDB/SQLite path remains available.
- No server, port, gateway config, or canonical truth-store change occurs in the spike.

Win conditions:
- Meaningful metric win on representative RAG/retrieval workload. Placeholder threshold before calibration: `MRR or NDCG +0.05 absolute` with no recall regression greater than `0.02`, or `p95 latency -20%` with quality neutral.
- Equivalent retrieval quality but significantly better filter/facet/shard semantics for a near-term product need.
- Clear strategic path to Qdrant Server/sync that we actually intend to use.

Reject/defer if:
- It only duplicates LanceDB with more runtime friction.
- Python/Rust binding makes runtime integration awkward without quality win.
- Benchmark improvements are within noise.
- Cache rebuild/fallback story is weaker than LanceDB.

## Rollback
Delete Qdrant Edge spike files/artifacts and local `qdrant-edge-*` cache directories. No live config or topology should have changed in this slice.
