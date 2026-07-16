# Run A Completion Report

Date: 2026-07-17

Branch: `feat/v2-run-a`

Baseline: `5bb0b66`

Verification commit: `dec8105`

## Outcome

Run A T00-T27 is complete. The stable storage, retrieval, episodic, pack, and
embedding paths now have output-free core APIs; historical databases have an
explicit governed migration/rollback path; bilingual lexical and exact optional
NumPy vector retrieval are covered by scenario gates; optional dependencies and
labs are isolated without removing existing public commands.

No push, release, deployment, or live-memory mutation was performed by Run A.
The larger upgrade goal continues in Run B under the user's explicit authority.

## Task ledger

| Task | Status | Commit | Result |
| --- | --- | --- | --- |
| T00 | done | `fc309b0` | Branch and tracker; baseline 789 passed, 3 skipped, 87 subtests. |
| T01 | done | `3175b06` | Locked 253 command paths and 52 top-level commands. |
| T02 | done | `37fbc19` | Explicit UTF-8 decoding at 67 subprocess text seams. |
| T03 | done | `eb03f66` | DB metadata/user-version stamp and `db info`. |
| T04 | done | `03228ca` | Migration registry, fast connect, future-version rejection. |
| T05 | done | `afab25c` | Qdrant moved to an optional extra with missing-extra contracts. |
| T06 | done | `0eac45c` | Additive pack stage/total timing receipts. |
| T07 | done | `56e6049`, `ae81f81` | Fixed-seed 10k perf suite and finite timing mocks. |
| T08 | done | `584259a` | Stable core DB/records/API boundary and MCP DB/store decoupling. |
| T09 | done | `1557223`..`37e45b2` | Store, ingest, harvest, and complete episodic lane moved into core. |
| T10 | done | `693ead3`, `a9fbd54` | Core search/pack, shared privacy/embedding seams, MCP decoupling. |
| T11 | done | `0bf313a`, `b6e9b65` | CLI became a registry-owned package with public seams preserved. |
| T12 | done | `935f7f3` | Governed v2 migration, backup receipt, hash-bound rollback, FTS reindex. |
| T13 | done | `65db782` | Generated v1.9.26/v1.9.31 historical compatibility fixtures and matrix. |
| T14 | done | `82193a3` | Subprocess proof that readonly commands do not alter DB/WAL/SHM state. |
| T15 | done | `a13c7ca` | Exact Python/NumPy vector-index protocol, cache, equivalence, CLI routing. |
| T16 | done | `5f621cd` | Governed trigram migration and CJK/mixed lexical routing. |
| T17 | done | `1cf2454`, `1ad063b` | Deterministic language labels, backfill, bilingual fallback without widening exact ASCII matches. |
| T18 | done | `3b6150e` | Retrieval KPI receipts and balanced 30-query top-5 recall gate. |
| T19 | done | `91cf2ff` | Embedding orphan/model/dimension integrity in `db info` and `doctor`. |
| T20 | done | `3376266`, `99428e0` | Optional local FastEmbed provider and real offline ingest/embed/vsearch proof. |
| T21 | done | `a920692` | Labs namespace, compatibility aliases, default-help hiding. |
| T22 | done | `a6c9430` | Ten ring-tiered skill cards, references, variant, legacy move stubs. |
| T23 | done | `d17383e` | Skill lint for metadata, size, paths, command truth, duplication. |
| T24 | done | `b4ac131`, `17e1a1d` | CI gates for skill lint, historical matrix, and golden recall. |
| T25 | done | `7625c34` | Changelog, optional extras, and governed DB upgrade documentation. |
| T26 | done | `dec8105` | Full/focused/perf/smoke/release verification. |
| T27 | done | HEAD-on-commit | This completion report. |

Blocked: none. Skipped implementation tasks: none.

## Final verification

- Full suite: 931 passed, 3 skipped, 5 expected labs compatibility warnings,
  87 unittest subtests passed in 329.30 seconds. The skip count did not increase
  from the 3-skip baseline.
- CLI surface: 55 passed; 260 paths and 54 top-level commands are locked. All
  original T01 paths remain callable; seven reviewed command paths in total,
  including two top-level surfaces, were added during Run A.
- Historical DB matrix: 3 passed independently.
- Balanced bilingual recall gate: 3 passed independently; all 30 fixture
  queries recover the expected record in top five.
- Skill lint: 10 cards and 63 embedded commands checked with zero errors and
  `writes_performed=false`.
- Real CLI smoke: status, three-row UTF-8 ingest, two-character CJK,
  four-character CJK, mixed CJK/ASCII search, traced pack, DB v3 info, and
  migration dry-run all passed on a disposable database.
- Governed release check: version 1.9.32 passed with zero writes.

## Performance

Fixed seed, 10,000 rows, Python 3.13.5, Windows 11. Lower latency is better;
higher ingest throughput is better.

| Metric | T07 baseline | T26 final | Change |
| --- | ---: | ---: | ---: |
| Ingest rows/s | 5,653.719 | 7,535.432 | +33.3% |
| Search P50 ms | 31.323 | 10.213 | -67.4% |
| Search P95 ms | 54.326 | 15.248 | -71.9% |
| Exact Python vsearch P95 ms | 175.598 | 102.642 | -41.5% |
| Exact NumPy vsearch P95 ms | unavailable | 6.522 | 15.738x vs Python |
| Pack P95 ms | 38.328 | 21.105 | -44.9% |
| Stamped connect P95 ms | 7.518 | 4.370 | -41.9% |

The first T26 perf sample was slower under concurrent machine load; the
immediate fixed-seed repeat is the committed final receipt. The earlier T20
receipt remains the best observed sample, while the conservative T26 repeat
still beats the T07 baseline on every comparable hot-path metric and exceeds
the 5x NumPy gate.

## CLI structure

- Before Run A: `openclaw_mem/cli.py`, 22,196 lines.
- After Run A: `openclaw_mem/cli/`, 22,104 total lines; the compatibility main
  module is 21,994 lines and six ownership/registry modules contain 110 lines.
- Net: 92 fewer lines overall and 202 fewer lines in the compatibility main.

The package/registry boundary and ownership metadata are real, but most legacy
handlers intentionally remain in the compatibility main. Further physical
handler extraction should be driven by Run B contracts, not counted as already
complete.

## Known risks and follow-up gates

- The public version remains 1.9.32. Version bump, release notes, tag, PyPI,
  docs deployment, and any live cutover require later release gates.
- Translation population for `summary_en` still needs an explicitly authorized
  provider/key and cost policy; deterministic language routing does not invent
  translations.
- Public LongMemEval/LoCoMo publication needs external dataset acquisition and
  a reviewed product claim. The local golden gate is not represented as that
  public benchmark.
- Optional NumPy, FastEmbed, and Qdrant behavior remains fail-open/fail-closed
  according to each lane's receipt; the default install stays SQLite-only.
- Labs are structurally isolated but not separate wheels. Legacy imports emit
  five expected deprecation warnings.
- Default CJK LIKE fallback can be linear for short queries; the 10k gate is
  green, but larger production corpora should retain latency telemetry.
- CLI physical decomposition is incomplete, as quantified above.
- Run A's original command-convergence, deprecation, lifecycle, and public-doc
  gates are handed to Run B or later master-plan gates; they are not silently
  marked complete here.

## Recommended continuation

Start Run B at T00 from this verified state. Preserve the 260-path surface lock,
historical DB/readonly invariants, bilingual top-5 gate, and T26 performance
receipt as regression baselines. Do not promote a live memory owner until the
later cutover proof explicitly authorizes it.
