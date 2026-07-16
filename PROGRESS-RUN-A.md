| task | status | commit | note |
| --- | --- | --- | --- |
| T00 | done | HEAD-on-commit | Branch `feat/v2-run-a`; baseline 789 passed, 3 skipped, 4 cp950 decode warnings, 87 subtests passed in 256.91s. |
| T01 | done | HEAD-on-commit | Locked 253 current command paths and help-smoked all 52 top-level commands; 54 tests passed in 5.55s. |
| T02 | done | HEAD-on-commit | Added explicit UTF-8 replacement decoding to 67 subprocess text calls across product/tools/tests; AST guard 1 passed; focused slice 58 passed, 1 skipped. |
| T03 | done | HEAD-on-commit | Added additive meta/user_version=1 stamp and `db info`; 58 DB/surface tests plus 149 CLI tests and 26 subtests passed. |
| T04 | done | HEAD-on-commit | Added migration registry, stamped connect fast-path, and future-version rejection; full suite 852 passed, 3 skipped, 87 subtests in 367.37s with prior cp950 warnings eliminated. |
| T05 | done | HEAD-on-commit | Moved qdrant-edge-py to `qdrant` extra while retaining it in dev; missing-extra status/error contracts covered; 6 focused plus 5 qdrant tests passed. |
| T06 | done | HEAD-on-commit | Added additive pack trace timings for candidates/trust_policy/graph/budget/render plus total_ms; golden/contracts 11 passed, 10 subtests. |
| T07 | done | HEAD-on-commit | Added fixed-seed offline 10k perf suite and baseline: ingest 5653.719 rows/s; search P50/P95 31.323/54.326 ms; vsearch P95 175.598 ms; pack P95 38.328 ms. Batch 1 gate: 855 passed, 3 skipped, 87 subtests in 369.40s after repairing three finite timing mocks. |
| T08 | done | HEAD-on-commit | Added stable core db/records/api modules; CLI private names now re-export core runtime implementations; MCP DB/store/default path decoupled from CLI with only the planned cmd_pack bridge remaining. Core boundary + DB/MCP/CLI focused gate 71 passed; full suite 857 passed, 3 skipped, 87 subtests in 257.39s. Legacy duplicate bodies remain compatibility scaffolding for T11 removal. |
| T09 | running | HEAD-on-commit | Slices 1-3 moved ingest/store, harvest state transitions, and episodic query/replay validation plus payload construction into output-free core modules. CLI query/replay commands are presentation-only; direct core round-trip, import-isolation, and focused episodes gates pass. Episodic append/search/embed/extract/ingest/redact/gc remain before T09 completion. |
