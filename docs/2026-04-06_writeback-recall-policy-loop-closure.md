# 2026-04-06 — writeback + recall policy loop closure packet

This packet closes roadmap item **1.5) Writeback + recall policy loop (M1.5)**.

## Verdict
The `1.5` slice is now treated as **DONE**.

Why this is honest:
- `openclaw-mem writeback-lancedb` now has verifier-backed proof that default writeback only fills missing fields and does **not** overwrite pre-existing operator-authored values.
- `openclaw-mem-engine` recall receipts now report the documented composite fail-open ladder truthfully:
  - `must+nice`
  - `must+nice+unknown`
  - `must+nice+unknown+ignore`
- disabled / empty importance policy is explicit fail-open behavior and reports `policyTier="ignore"`.

What is **not** being claimed here:
- no slot switch
- no cron rollout change
- no default forced overwrite behavior
- no Stage B / Stage C sunrise promotion claim

## Landed surfaces
- `extensions/openclaw-mem-engine/importancePolicyLoop.js`
- `extensions/openclaw-mem-engine/importancePolicyLoop.test.mjs`
- `extensions/openclaw-mem-engine/index.ts`
- `tests/test_writeback_lancedb_integration.py`
- `docs/mem-engine.md`

## Fresh receipts
Operator receipt:
- `projects/openclaw-mem/receipts/2026-04-06_b1_writeback-recall-policy-loop_v0.md`

That receipt covers:
- bounded writeback proof
- policy-tier ladder smoke
- disabled-policy fail-open behavior

## Commands run
From repo root / engine dir:

```bash
uv run --python 3.13 --frozen -m unittest \
  tests.test_writeback_lancedb_integration \
  tests.test_optimize_policy_loop \
  tests.test_scope \
  tests.test_cli

cd extensions/openclaw-mem-engine
node --test *.test.mjs
```

## Observed results
### Python targeted verifier pass
- `Ran 100 tests`
- `OK`

### Node targeted verifier pass
- `28 / 28` tests passed
- includes policy-loop helper coverage for:
  - baseline `must+nice`
  - widen to `unknown`
  - widen to `ignore`
  - disabled-policy fail-open

## Closure interpretation
This item is closed because the promised `1.5` behavior is now verifier-backed:
- writeback stays bounded and non-destructive by default
- recall policy receipts match the documented fail-open ladder
- empty-policy behavior is explicit and truthful instead of implicit/ambiguous

## Non-change
- Runtime topology: unchanged.
- Live cron / controller topology: unchanged.
