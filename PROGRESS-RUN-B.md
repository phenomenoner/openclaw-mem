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
| T11 | done | `7d1011e` | Extended the deterministic perf suite with sqlite-vec, end-to-end recall, and graph-auto pack lanes; added fixed 10k/100k reports, file-backed 20% regression gates with a published 1.3x tolerance band, and a scheduled 100k CI job. Product hot paths now use bounded FTS candidate scoring, O(1) sqlite-vec invalidation triggers, connection-local read tuning, and a bounded graph-scope cache with local/external write invalidation. Threshold/YAML/compile checks passed. Batch 3 full suite: 1061 passed, 3 skipped, 5 expected warnings, 87 subtests in 309.64 seconds. |
| T12 | done | `f6be312` | Added the six-state lifecycle machine, legal-transition matrix, bounded history, actionable illegal-transition receipts, missing-state=active semantics, and legacy `archived_at` compatibility. Search, recall, hybrid/vector, programmatic/CLI pack, and graph-backed pack preflight exclude soft-archived observations by default with explicit include overrides. Added `db lifecycle set`, lifecycle distributions to `db info`/`profile`, and explicit CLI surface approval. Integrated lifecycle/DB/retrieval/pack/graph/CLI slice: 266 passed plus 36 subtests. |
| T13 | done | `8253c4e` | Added the eight-kind taxonomy, deterministic bilingual classifier (48 zh/en/fallback table cases), default-on config with env/TOML opt-out, automatic store/ingest/harvest classification for note/tool/empty captures, and idempotent `db backfill --kind [--dry-run]` receipts with before/after distributions. Explicit stronger kinds remain byte-shape compatible. Added full kind distribution to `db info` and taxonomy documentation. Full-suite audit reached 1133 passed with only two obsolete fixture-shape expectations; after correcting those, focused taxonomy/config/curate/contracts and MCP equivalence slices passed. The 10k perf check measured 6,610 ingest rows/s and 15.316 ms pack p95; config-stamped internal parser caching removed repeated ~160 ms parser construction without weakening config invalidation. |
| T14 | done | `e2948d3` | Added default-on soft pack quotas with config/env controls: preference and decision reservations plus an event max-ratio cap. The shared quota planner is used by programmatic and CLI/MCP packs, excludes downstream-ineligible trust/text candidates, and finalizes reservation receipts only for actually selected refs. Trace output records `quota_hits` and event exclusions record `quota_event_capped`; disabled mode preserves baseline ordering/output shape. Golden/contract/trace/MCP/config quota slice: 23 passed plus 10 subtests. 10k perf remained healthy at 7,080 ingest rows/s and 17.704 ms pack p95. |
| T15 | done | `144b0e2` | Added opt-in composite scoring across core API, CLI, MCP, search, recall, hybrid, and pack while retaining byte-shape/order compatibility under the default relevance profile. Importance, kind-aware recency, use, and lifecycle state factors are independently configurable and emit per-candidate evidence only in composite mode; trust remains a pack hard gate. Curate drift scanning now produces governed label-calibration candidates for every detected mismatch, with before/after rollback evidence. Integrated retrieval/config/MCP/quota/curation slice: 104 passed. The opt-in 10k profile remained within SLO at 28.129 ms search p95, 30.898 ms hybrid recall p95, and 43.497 ms pack p95. |
| T16 | done | `708fc2f` | Added pack-citation-only use tracking with bulk same-connection updates, readonly/env opt-out, top-level and trace receipts, explicit-priority-first protection tiers, configurable P1/P2 decay windows, governed lifecycle-chained soft archive, rollback revival, and archive aggregation by priority/kind/trust. Focused use/config coverage passed 20 tests; the integrated legacy optimization/lifecycle/pack slice passed 79 tests. Exact JSON/MCP fixtures were updated only for planned additive receipts and sequential use counters. A Windows concurrency test was corrected from a race-prone 30-second ceiling to 90 seconds after measurement showed healthy serialized cold pipelines take 45.32 seconds; its controller revisions still pass as `[1, 2]`. Batch 4 full suite: 1166 passed, 3 skipped, 5 expected warnings, and 87 unittest subtests in 695.15 seconds. |
| T17 | done | pending commit | Extended the existing 30-case bilingual golden gate with 20 auditable competing-record lifecycle cases across superseded history, frequently used preferences, active/stale state, and soft-archived noise. The reusable gate compares both profiles on all 50 cases and emits a committed receipt. R@5 held at 1.000 for both profiles; MRR improved from 0.740 relevance to 0.990 composite (+33.78% relative), satisfying the non-regression plus ≥5% rule, so the built-in scoring default flipped to composite while the relevance override remains supported. UTC-day score references make equivalent receipts stable. Focused gate/config/scoring: 21 passed; expanded CLI/core/recall/pack/contracts/MCP slice: 205 passed plus 36 subtests. |

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
