# Memory Strata WS10 Retrieval Regression Baseline — 2026-05-25

Status: **completed / read-only baseline**  
Companion specs: `docs/specs/memory-strata-boundary-map-v0.md`, `docs/specs/memory-strata-todo-v0.md`  
Topology impact: **unchanged** — no runtime config, cron, slot, schema, install, durable memory, docs ingest, episodes ingest, graph capture, push, or tag changes were made.

## Goal

Create a fixed regression query set before changing recall defaults, bootstrap contents, graph integration, Working Set behavior, or promotion/writeback policy.

## Artifacts

- Query set: `docs/receipts/artifacts/memory-strata-regression-queries-2026-05-25.json`
- Machine baseline: `docs/receipts/artifacts/memory-strata-regression-baseline-2026-05-25.json`

## Safety posture

- Store searches used read-only FTS query commands.
- Episodic searches used `episodes search`; no `episodes ingest`, append, redact, or GC.
- Docs searches used `docs search`; no `docs ingest`.
- Pack traces used `--pack-lifecycle-shadow off --pack-lifecycle-write off --use-graph off`.
- Graph baseline used `graph index` only; no capture/refresh/export mutation.

## Baseline summary

| Query id | Intent | Lane | Exit | Non-empty output | Elapsed ms |
|---|---|---:|---:|---:|---:|
| q01-durable-slot | stable decision/preference | store_fts | 0 | yes | 342 |
| q02-durable-retention | durable policy | store_fts | 0 | no | 275 |
| q03-episodic-trail | session trail | episodes_lexical | 0 | yes | 230 |
| q04-episodic-semantic | raw wording evidence | episodes_hybrid | 0 | yes | 2146 |
| q05-docs-cold | spec/doc lookup | docs_search | 0 | yes | 3672 |
| q06-graph-topology | dependency relationship | graph_index | 0 | yes | 239 |
| q07-pack-contract | final pack quality | pack_trace | 0 | yes | 1036 |
| q08-working-set | active goal/backbone | store_fts | 0 | no | 251 |
| q09-promotion | writeback governance | docs_search | 0 | yes | 1805 |
| q10-privacy-scope | privacy/scope gate | episodes_lexical | 0 | yes | 487 |
| q11-bootstrap | bootstrap slimming | pack_trace | 0 | yes | 810 |
| q12-release | release closure | store_fts | 0 | yes | 243 |

## Initial observations

- All 12 commands exited successfully.
- Empty-result baseline items: `q02-durable-retention, q08-working-set`.
- Empty results are kept as useful regression facts; they identify queries that may need better wording, better indexing, or future product work.
- `episodes_hybrid` and `docs_search` were slower than pure FTS, as expected; later WS4/WS8 should evaluate quality, not only latency.
- `pack_trace` works with lifecycle writes disabled, preserving the current boundary map posture.

## Counterfactual / failure sensitivity

A future change should be treated as suspicious if it:

- changes a successful lane into command failure,
- causes pack traces to require writeback,
- increases cross-lane result volume without better citation/why-included evidence,
- makes currently empty baseline queries appear only through unrelated/stale hits,
- or introduces graph/default activation before WS1/WS10 receipts are reviewed.

## Closure

WS10 baseline is sufficient for Milestone 1 review. It does **not** prove retrieval quality is good enough for runtime/default changes; it only establishes a reproducible pre-change floor.
