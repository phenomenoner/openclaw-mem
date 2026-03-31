# 2026-03-31 — importance grading benchmark closure packet

This packet closes roadmap item **`1) Importance grading rollout (MVP v1)`**.

## Verdict
The MVP slice is now treated as **DONE**.

Why this is honest:
- canonical `detail_json.importance` shape is already shipped
- deterministic scorer `heuristic-v1` is already shipped
- ingest/harvest autograde wiring is already feature-flagged and fail-open
- the missing benchmark packet now exists as a bounded, operator-curated receipt

This is **not** a broad external quality claim.
It is a small operator-curated regression benchmark intended to prove the MVP closure gate.

## Benchmark source of truth
- `benchmarks/importance_grading_set.v1.jsonl`

This benchmark corpus is also used by the scorer regression test so the benchmark and the test lane stay aligned.

## Receipt
- `handoffs/receipts/2026-03-31_importance-benchmark/importance-benchmark.v1.json`

Receipt kind:
- `openclaw-mem.importance-benchmark.v1`

## Command used
From repo root:

```bash
PYTHONPATH=. python3 tools/importance_benchmark.py \
  --input benchmarks/importance_grading_set.v1.jsonl \
  --output handoffs/receipts/2026-03-31_importance-benchmark/importance-benchmark.v1.json
```

## Observed results
- total cases: `34`
- before operator labels:
  - `must_remember = 5`
  - `nice_to_have = 25`
  - `ignore = 4`
- after `heuristic-v1` predictions:
  - `must_remember = 5`
  - `nice_to_have = 25`
  - `ignore = 4`
- label agreement: `1.0`
- mismatch count: `0`
- `must_remember_precision = 1.0` (`5/5`)
- `ignore_precision = 1.0` (`4/4`)

## Ignore spot-check set
The receipt includes a bounded `ignore_spot_check` block covering the predicted ignore cases, including:
- `tc06` — pure progress update
- `tc08` — calendar-only note
- `tc09` — acknowledgement/chit-chat
- `tc11` — secret-like content (redacted)

## Regression verification
```bash
PYTHONPATH=. python3 -m unittest -q \
  tests.test_heuristic_v1 \
  tests.test_importance_autograde_e2e
```

Result:
- `Ran 12 tests in 2.633s`
- `OK`

## Closure interpretation
This closes the MVP item because the roadmap's last missing gate now has a concrete artifact:
- small before/after benchmark set
- operator-labeled benchmark source
- explicit `must_remember` precision
- explicit `ignore` spot-check receipt

## Non-change
- No scorer logic change was required for this closure.
- No new runtime authority was added.
- No recall/writeback policy changed here.
