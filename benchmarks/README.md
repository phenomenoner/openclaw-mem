# Benchmarks and proofs

This directory contains small public fixtures for evaluating `openclaw-mem` behavior.

The first public artifact is deliberately a **synthetic proof**, not a broad statistical benchmark.

## Trust-policy synthetic proof

Run:

```bash
uv run --python 3.13 --frozen -- \
  python benchmarks/trust_policy_synthetic_proof.py --json
```

What it proves:

- vanilla packing can select a quarantined row when the text matches the query
- trust-aware packing can exclude that row with an explicit receipt reason
- citation coverage is preserved for selected rows
- the proof uses only checked-in synthetic memory

What it does not prove:

- broad retrieval quality
- hosted/vector recall superiority
- production workload lift
- latency at scale

For narrative docs, see:

- [`docs/showcase/trust-policy-synthetic-proof.md`](../docs/showcase/trust-policy-synthetic-proof.md)
- [`docs/showcase/trust-aware-context-pack-proof.md`](../docs/showcase/trust-aware-context-pack-proof.md)

## Existing fixture sets

- `docs_memory_query_set.v1.jsonl` — query set for docs-memory Hit@K checks.
- `importance_grading_set.v1.jsonl` — fixture for importance grading behavior.

These are useful for development and regression checks. They are not yet a public comparative benchmark suite.
