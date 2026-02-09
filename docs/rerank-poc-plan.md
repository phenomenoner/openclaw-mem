# Hybrid Rerank POC Plan (v0.5.10-proposed)

Status: draft POC scope (opt-in only, default behavior unchanged)

## Goal

Evaluate whether post-retrieval reranking improves `openclaw-mem` hybrid recall quality enough to justify extra latency/cost.

## POC scope (low risk)

- Only touch `hybrid` command path.
- Keep default mode unchanged (`--rerank-provider none`).
- Add providers:
  - `jina`
  - `cohere`
- Fail-open behavior:
  - rerank error/missing key/network failure => return base RRF ranking.

## New CLI flags (POC)

- `--rerank-provider none|jina|cohere` (default: `none`)
- `--rerank-model <name>`
- `--rerank-topn <int>`
- `--rerank-api-key <secret>` (or env fallback)
- `--rerank-base-url <url>`
- `--rerank-timeout-sec <int>`

## Baseline + A/B benchmark plan

Use `openclaw-memory-bench` with same dataset and seed.

### A) Baseline (rerank off)

- Run with current hybrid behavior (`--rerank-provider none`).

### B) Treatment (rerank on)

- Run same data and config, only enabling rerank.
- Suggested first pass:
  - provider: `jina`
  - model: `jina-reranker-v2-base-multilingual`
  - `topn`: 20

### C) Compare

Track:
- retrieval: `hit@k`, `mrr`, `ndcg@k`
- latency: p50/p95
- failure rate / timeout rate
- token/API cost per query (provider-side)

## Success criteria (initial)

- Quality gain threshold:
  - `mrr` +0.02 or more, OR
  - `ndcg@k` +0.03 or more
- With acceptable regression:
  - p50 latency increase under +700ms/query on target workloads
  - no material increase in failed queries

## Notes

- This POC is additive and reversible.
- If gains are weak on target data, keep rerank as advanced opt-in only.
