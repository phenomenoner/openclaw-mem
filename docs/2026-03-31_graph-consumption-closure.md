# 2026-03-31 — graph consumption closure packet

This packet closes roadmap item **`1.7) Graphic Memory consumption (triggered preflight → pack integration)`**.

## Verdict
The bounded product slice is now treated as **DONE**.

Why this is honest:
- `pack` now supports explicit graph posture control: `--use-graph=off|auto|on`
- `auto` mode exposes a deterministic, redaction-safe trigger envelope in `--trace`
- graph-preflight failures stay fail-open and do not break baseline pack output
- graph-derived candidate inclusion already consumes structured-provenance policy with deterministic include/exclude reasons
- policy and usage receipts remain bounded (`graph_provenance_policy`, `policy_surface`, `lifecycle_shadow`)

What is **not** being claimed here:
- no claim that higher-level graph semantic memory is closed
- no claim that topology-seed automation is closed
- no claim that graph must run on every pack call

## Fresh repo-local smoke receipts
Stored under:
- `handoffs/receipts/2026-03-31_graph-consumption/01-pack-graph-off.json`
- `handoffs/receipts/2026-03-31_graph-consumption/02-pack-graph-auto-keyword.json`
- `handoffs/receipts/2026-03-31_graph-consumption/graph-consumption-smoke.sqlite`

Fixture generator used:
- `/root/.openclaw/workspace/_scratch/openclaw_mem_graph_consumption_smoke.py`

## Smoke commands
From repo root:

```bash
PYTHONPATH=. python3 tools/graph_consumption_smoke.py

PYTHONPATH=. python3 -m openclaw_mem --db handoffs/receipts/2026-03-31_graph-consumption/graph-consumption-smoke.sqlite \
  --json pack --query "where is roadmap" --trace --use-graph off

PYTHONPATH=. python3 -m openclaw_mem --db handoffs/receipts/2026-03-31_graph-consumption/graph-consumption-smoke.sqlite \
  --json pack --query "where is roadmap" --trace --use-graph auto
```

## Observed smoke results
### `--use-graph off`
- baseline `pack` output stays unchanged
- bundled one matching observation
- no graph trigger envelope is added

### `--use-graph auto`
- deterministic keyword trigger fired for the same query
- trace shows:
  - `trigger_reason = "keyword:A+B"`
  - `stage1.categories = ["A", "B"]`
  - `matched_keywords = ["roadmap", "where is"]`
  - `probe.ran = false`
- graph preflight stayed bounded and fail-open-safe
- baseline pack output still succeeded

Interpretation:
- OFF preserves existing pack behavior
- AUTO is deterministic + traceable on repo-local truth

## Targeted verification
```bash
PYTHONPATH=. python3 -m unittest -q \
  tests.test_cli.TestCliM0.test_pack_use_graph_on_adds_graph_payload_and_trace_extensions \
  tests.test_cli.TestCliM0.test_pack_use_graph_auto_keyword_trigger_is_traceable \
  tests.test_cli.TestCliM0.test_pack_use_graph_auto_probe_strong_triggers_preflight \
  tests.test_cli.TestCliM0.test_pack_use_graph_on_provenance_policy_filters_unstructured_graph_candidates \
  tests.test_cli.TestCliM0.test_pack_use_graph_on_provenance_policy_fail_open_on_query_error \
  tests.test_cli.TestCliM0.test_pack_graph_provenance_and_trust_policy_contracts_are_compatible
```

Result:
- `Ran 6 tests in 0.105s`
- `OK`

What these tests cover:
- forced `on` mode emits graph payload + trace extension
- `auto` keyword trigger is deterministic + traceable
- `auto` probe-strong trigger is deterministic + traceable
- structured provenance policy includes/excludes graph-derived candidates deterministically
- provenance query failures stay fail-open
- graph provenance and pack trust policy receipts stay contract-compatible

## Closure interpretation
This roadmap item is closed because the promised product boundary is now met:
- graph consumption is integrated into `pack`
- posture is explicit (`off|auto|on`)
- trigger behavior is deterministic and inspectable
- failures stay fail-open
- policy receipts stay bounded and machine-readable

## Non-change
- No runtime/system topology changed.
- No live cron topology changed.
- No automatic topology-seed claim was added here.
- No higher-level semantic-memory claim was added here.
