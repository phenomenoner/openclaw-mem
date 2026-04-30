# Plain-vanilla ContextPack benchmark

This benchmark is a small, public, reproducible check for the core `openclaw-mem` promise.

It does **not** read a real OpenClaw memory store. It uses only the synthetic fixture in this repository:

- [`artifacts/trust-aware-context-pack.synthetic.jsonl`](artifacts/trust-aware-context-pack.synthetic.jsonl)

## What it compares

The benchmark ingests the fixture into a temporary SQLite database and runs the same query twice:

1. **Vanilla pack** — local retrieval and packing without a trust policy.
2. **Trust-aware pack** — the same pack command with `--pack-trust-policy exclude_quarantined_fail_open`.

The expected result is intentionally narrow:

- the vanilla pack selects a quarantined row because it matches the query text
- the trust-aware pack excludes that quarantined row with an explicit receipt reason
- citation coverage remains intact for the selected rows
- unknown-trust rows stay explicit fail-open when they are selected

## Run it

```bash
uv run --python 3.13 --frozen -- \
  python benchmarks/plain_vanilla_context_pack_benchmark.py --json
```

The command exits non-zero when any assertion is false. That means the proof did not hold; inspect the JSON assertion block before treating it as an environment failure.

Optional receipt:

```bash
uv run --python 3.13 --frozen -- \
  python benchmarks/plain_vanilla_context_pack_benchmark.py \
    --json \
    --artifact .state/plain-vanilla-context-pack-benchmark.json
```

## Metrics emitted

The JSON result includes:

- selected refs before and after the trust policy
- selected trust-tier counts
- citation coverage
- bundle character count
- trust-policy reason counts
- boolean assertions for the public proof

The assertion block is the important part:

```json
{
  "synthetic_fixture_only": true,
  "no_real_memory_paths_used": true,
  "quarantined_removed": true,
  "citation_coverage_preserved": true,
  "trust_policy_explains_exclusion": true
}
```

## What this proves

This benchmark proves one small but useful thing:

> For the same synthetic memory and the same query, a trust-aware `ContextPack` can remove quarantined content, preserve citations for selected rows, and leave an inspectable reason trail.

That is the public product wedge: not bigger memory, but safer and more explainable context.

## What it does not prove

It does not claim broad retrieval superiority, hosted-vector performance, or production quality lift across every workload. Those require larger benchmark suites. This script is the first evaluator-friendly check: simple enough for independent reviewers to rerun, narrow enough to audit, and safe enough to publish.
