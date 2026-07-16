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
| T06 | done | pending commit | Added recursive error-receipt normalization plus `_emit_error`, preserving specific hints and guaranteeing an actionable fallback hint for legacy/nested errors. Documented exit codes 0/1/2 and reserved compatibility code 3. Error-contract slice: 228 passed plus 26 subtests; full suite: 1017 passed, 3 skipped, 5 expected warnings, 87 subtests. |
