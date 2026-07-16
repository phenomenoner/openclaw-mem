# Run B Progress

Branch: `feat/v2-run-b`

Baseline: Run A completion commit `70f0478`.

## T00 precondition audit

| Precondition | Status | Evidence / effect |
| --- | --- | --- |
| Stable `openclaw_mem/core/` APIs | present | `api`, `db`, `records`, `search`, and `pack` import successfully. |
| Registry-owned CLI package | present | `openclaw_mem/cli/__init__.py` and ownership registry exist. |
| DB generation and `db info` | present | Disposable in-memory DB reports `user_version=3`, no pending migration, healthy FTS. |
| Explicit CLI surface lock | present | Surface/CJK audit slice passed 60 tests; current lock has 260 paths and 54 top-level commands. |
| Exact VectorIndex + NumPy | present | `VectorIndex` and `NumpyIndex` import; Run A final exact speedup was 15.738x. |
| Trigram and bilingual foundation | present | `tests/test_cjk_search.py` included in the 60-test audit; balanced golden gate is green. |
| Run A report and gates | present/reviewed | No blocked Run A task. Translation supply chain, public benchmarks, release/version, live cutover, and separate labs wheels remain later gates; command convergence and lifecycle work enter Run B as planned. |

Deviations: none. All Run B fallbacks are inactive at start.

Baseline full suite: 931 passed, 3 skipped, 5 expected labs compatibility
warnings, and 87 unittest subtests in 267.21 seconds. The three skips match the
Run A baseline; no new skip was introduced.

## Task ledger

| task | status | commit | note |
| --- | --- | --- | --- |
| T00 | done | `1377f32` | Created Run B branch, audited every prerequisite with zero deviations, and recorded the fresh full-suite baseline. |
| T01 | done | `0382d8d` | Added the unified fail-open `recall` entrypoint across lexical/vector/hybrid/graph lanes, including scope filters, routing receipts, and output-free core coverage. |
| T02 | done | `c378782` | Added `curate scan/review/apply/verify/rollback`, additive alias deprecation receipts, all 20 verb-target smoke cases, full soft-archive e2e, and atomic drift-guarded memory rollback. Related regression slice: 206 passed plus 13 subtests. |
| T03 | done | `14315c7` | Added `sync status/run/init` wrappers for LanceDB, service readiness stores, and Qdrant probes with honest unsupported-operation receipts and shared alias deprecations. CLI convergence regression: 255 passed plus 26 subtests. |
| T04 | done | `a3de604` | Default help now exposes only recall/store/curate/sync/graph/db while `--help-all` preserves the complete surface. Rewrote memory/curate skill routing, added the legacy map, regenerated canonical derivatives, and passed skill lint (10 files, 68 commands, zero errors). Batch 1 full suite: 985 passed, 3 skipped, 5 expected warnings, 87 subtests in 252.76 seconds. |
| T05 | done | `3bb8d42` | Added idempotent `init`, atomic fill-only `~/.openclaw-mem/config.toml`, capability receipts, and env > TOML > built-in resolution wired into DB, scope, vector, embedding, and pack defaults. Clean-HOME init/store/recall target slice: 92 passed; broad CLI/DB/embedding/vector/pack regression: 258 passed plus 55 subtests. |
| T06 | done | `e1c25d5` | Added recursive error-receipt normalization plus `_emit_error`, preserving specific hints and guaranteeing an actionable fallback hint for legacy/nested errors. Documented exit codes 0/1/2 and reserved compatibility code 3. Error-contract slice: 228 passed plus 26 subtests; full suite: 1017 passed, 3 skipped, 5 expected warnings, 87 subtests. |
| T07 | done | `9896917` | Added unified `install --harness` orchestration and core detect/plan/apply/verify phases for claude-code, codex, openclaw, and generic. Writes are atomic, changed existing targets are timestamp-backed-up, JSON/managed-card unrelated content is preserved, dry-run is zero-write, and optional apply-time verify is supported. Adapter/legacy/CLI slice: 94 passed; direct CLI dry-run/apply/verify smoke passed. |
| T08 | done | `8c48f06` | Completed the installer matrix with Gemini CLI, Cursor, and Windsurf JSON adapters using current official paths plus `--config-path` overrides. Added `doctor --harness` pass/warn/fail diagnostics, executable/skill/config checks, repair commands, and seven ≤5-step quickstarts. Harness/CLI regression: 252 passed plus 26 subtests; focused final slice: 89 passed; direct missing-install doctor exit-1 smoke and strict MkDocs build passed. |
| T09 | done | `c981460` | Added read-only MCP `mem_recall`, `graph_neighbors`, `graph_path`, and `graph_impact` tools. `mem_recall` shares the core router; `mem_pack` invokes the full CLI policy handler in-process to prevent contract drift. Added JSON-RPC invalid-parameter/error hints, deep CLI/MCP equivalence coverage after transport/timing normalization, graph wrapper tests, and an updated tool-description hash golden. Focused slice: 51 passed; compileall and direct manifest smoke passed. Batch 2 full suite: 1052 passed, 3 skipped, 5 expected warnings, 87 subtests in 259.71 seconds. |
| T10 | done | `f87d85f` | Added the optional `vec` dependency and locked sqlite-vec 0.1.9. Persisted per-model/per-dimension cosine vec0 tables now carry source row-count/max-id freshness metadata; `auto` selects fresh sqlite-vec then NumPy then Python without creating indexes, and emits actionable fallback receipts. Added `db reindex --vec`, sqlite-vec index details in `db info`, MCP/CLI backend selection, readonly zero-write checks, and top-10 equivalence to NumPy within 1e-5. Integrated regression slice: 118 passed; output-free core/vector slice: 39 passed; `uv lock --check`, compileall, and direct CLI help smoke passed. |
| T11 | done | pending commit | Extended the deterministic perf suite with sqlite-vec, end-to-end recall, and graph-auto pack lanes; added fixed 10k/100k reports, file-backed 20% regression gates with a published 1.3x tolerance band, and a scheduled 100k CI job. Product hot paths now use bounded FTS candidate scoring, O(1) sqlite-vec invalidation triggers, connection-local read tuning, and a bounded graph-scope cache with local/external write invalidation. Threshold/YAML/compile checks passed. Batch 3 full suite: 1061 passed, 3 skipped, 5 expected warnings, 87 subtests in 309.64 seconds. |

## T11 100k SLO evidence

Formal fixed-seed results are stored in `benchmarks/perf/RUN-B-numbers.json`;
the corresponding nightly limits are in `benchmarks/perf/RUN-B-thresholds.json`.
The broad single-token `search` lane remains a pressure diagnostic and is not
substituted for the documented recall SLO.

| 100k metric | target | actual p95 | result |
| --- | ---: | ---: | --- |
| stamped connect | < 30 ms | 4.102 ms | pass |
| recall lexical, deterministic three-token product queries | < 50 ms | 25.559 ms | pass |
| recall hybrid, sqlite-vec selected by auto | < 200 ms | 80.250 ms | pass |
| pack, graph auto | < 300 ms | 224.493 ms | pass |
| vsearch, sqlite-vec | < 30 ms | 21.889 ms | pass |

The 10k tier also passed every corresponding absolute SLO. The graph-auto pack
lane includes one cold scope discovery followed by correctly invalidated hot
reads; the report's p95 therefore represents the persistent CLI/MCP handler
path while retaining the cold-start sample in the distribution.
