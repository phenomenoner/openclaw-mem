# Run B Completion Report

Date: 2026-07-17

Branch: `feat/v2-run-b`

Baseline: Run A completion commit `70f0478`

Final verification commit: `f36a123`

GitHub landing-site sync: `84ca39b` (includes upstream `fb6f957`)

## Outcome

Run B T00-T20 is complete. The product now presents a converged primary CLI
around `recall`, `store`, `curate`, `sync`, `graph`, and `db`; bootstraps an
explicit configuration; installs and diagnoses seven harness integrations;
offers read-only MCP recall/graph tools with cross-surface equivalence; uses a
persisted sqlite-vec exact lane when available; and governs memory through an
eight-kind taxonomy, six lifecycle states, pack quotas, composite scoring,
citation-only use tracking, decay, and reversible soft archive.

The 50-case golden gate approved composite scoring as the default. Final 10k
and 100k receipts pass every published absolute product SLO. Verification also
found and fixed a real 100k pack regression in graph-scope cache invalidation;
the final 100k graph-auto pack p95 is 62.160 ms against a 300 ms target.

No Run B implementation task is blocked or skipped. Existing compatibility
commands remain callable with additive deprecation receipts; no intentional
breaking CLI, database, or MCP contract change was introduced.

## Task ledger

| Task | Status | Commit | Result |
| --- | --- | --- | --- |
| T00 | done | `1377f32` | Audited Run A prerequisites and established a 931-pass full-suite baseline with no fallback required. |
| T01 | done | `0382d8d` | Added unified fail-open recall routing across lexical, vector, hybrid, and graph lanes. |
| T02 | done | `c378782` | Added governed curate scan/review/apply/verify/rollback and preserved legacy aliases. |
| T03 | done | `14315c7` | Added sync status/run/init wrappers with honest backend capability receipts. |
| T04 | done | `a3de604` | Converged default help, retained advanced compatibility help, and regenerated ring-tiered skill guidance. |
| T05 | done | `3bb8d42` | Added idempotent init and fill-only TOML configuration with env-over-TOML precedence. |
| T06 | done | `e1c25d5` | Normalized actionable error receipts and documented stable exit behavior. |
| T07 | done | `9896917` | Added atomic detect/plan/apply/verify installer flows for Claude Code, Codex, OpenClaw, and generic harnesses. |
| T08 | done | `8c48f06` | Completed Gemini CLI, Cursor, and Windsurf adapters, doctor diagnostics, and seven short quickstarts. |
| T09 | done | `c981460` | Added read-only MCP recall and graph tools with CLI/MCP policy and result equivalence. |
| T10 | done | `f87d85f` | Added persisted sqlite-vec indexing, freshness metadata, auto fallback chain, reindex, and DB diagnostics. |
| T11 | done | `7d1011e` | Formalized deterministic 10k/100k perf lanes, stored 20% regression thresholds, and scheduled CI. |
| T12 | done | `f6be312` | Added the six-state lifecycle machine, transition receipts, compatibility, and default archive exclusion. |
| T13 | done | `8253c4e` | Added eight-kind deterministic bilingual classification, automatic capture classification, and kind backfill. |
| T14 | done | `e2948d3` | Added category-aware pack reservations/caps with traceable quota decisions. |
| T15 | done | `144b0e2` | Added configurable composite scoring with per-factor evidence and governed label calibration. |
| T16 | done | `708fc2f` | Added citation-only use tracking, protected decay tiers, reversible soft archive, and archive aggregation. |
| T17 | done | `616d6e0` | Expanded the golden set to 50 cases; gate evidence approved and enabled composite by default. |
| T18 | done | `d26d30e` | Updated changelog, migration/taxonomy/MCP docs, navigation, quickstarts, and skill command truth. |
| T19 | done | `f36a123` | Completed full/focused/perf/smoke verification, fixed cache invalidation regression, and made SLOs executable CI gates. |
| T20 | done | HEAD-on-commit | This completion report and final closure audit. |

## Final verification

- Full suite after the final code and gate changes: 1171 passed, 3 skipped,
  5 expected labs compatibility warnings, and 87 unittest subtests in 713.62
  seconds. This is 240 more passing tests than the T00 baseline with no new
  skip or warning category.
- Surface lock, legacy alias, MCP equivalence, and both golden gates: 123
  focused tests passed independently.
- Composite lifecycle gate: 50 auditable queries, including superseded,
  preference-use, stale/active, and soft-archive competition cases.
- Docs after the upstream cosmetic redesign was merged: strict MkDocs build
  passed; the docs/quickstart/skill-facing slice passed 38 tests and 3
  subtests. The new landing theme and README coexist with the Run B migration,
  harness, and taxonomy navigation.
- Skill lint: 10 cards, 68 embedded commands, zero errors, and no writes.
- Lock/build hygiene: `uv lock --check`, Python compilation, and diff checks
  passed during the final batch.
- Disposable CLI smoke passed the required chain: init; auto-classified store;
  auto recall; composite pack trace; curate scan; DB kind/lifecycle info; and
  generic harness installer dry-run. The pack returned a citation, quota
  receipt, `refreshed_refs`, and a citation-only `used_count` transition from
  0 to 1. The installer reported zero writes.

## Performance and product SLOs

Receipts: `benchmarks/perf/RUN-B-FINAL-10k.json` and
`benchmarks/perf/RUN-B-FINAL-100k.json`. Each embeds an executable
`openclaw-mem.perf.slo-gate.v1` receipt with `ok=true`.

| Metric | Target | 10k p95 | 100k p95 | Result |
| --- | ---: | ---: | ---: | --- |
| Stamped connect | < 30 ms | 5.576 ms | 10.754 ms | pass |
| Lexical recall | < 50 ms | 47.104 ms | 26.805 ms | pass |
| Hybrid recall, sqlite-vec auto | < 200 ms | 37.576 ms | 75.397 ms | pass |
| Pack, graph auto | < 300 ms | 40.802 ms | 62.160 ms | pass |
| sqlite-vec exact search | < 30 ms | 3.246 ms | 23.030 ms | pass |

| Additional metric | 10k | 100k |
| --- | ---: | ---: |
| Ingest throughput | 3,147.542 rows/s | 3,963.636 rows/s |
| Broad diagnostic search p95 | 35.620 ms | 285.449 ms |
| Exact Python vector p95 | 158.035 ms | 1,338.415 ms |
| Exact NumPy vector p95 | 7.983 ms | 42.732 ms |
| NumPy speedup over Python | 19.797x | 31.321x |

The broad single-token search lane is retained as a pressure diagnostic and is
not substituted for the published deterministic lexical recall SLO. The local
portable absolute gate is authoritative for the final workstation receipt.
The stored 20% historical comparison remains enforced on the fixed scheduled
Ubuntu runner; ad-hoc cross-machine samples were too noisy for an honest local
pass/fail claim.

## Composite default gate

| Profile | Recall@5 | MRR |
| --- | ---: | ---: |
| Relevance | 1.000 | 0.740 |
| Composite | 1.000 | 0.990 |

Composite preserved Recall@5 and improved MRR by 33.78%, exceeding the rule
that both metrics must be non-regressing and at least one improve by 5% or
more. The default therefore changed to composite. An explicit relevance
profile remains available for compatibility and diagnosis. The committed gate
receipt is `benchmarks/golden/RUN-B-T17-composite-gate.json`.

## Deviations and corrective work

- T13's first full audit exposed two obsolete exact fixture expectations after
  the planned additive taxonomy fields. The fixtures were corrected; the
  public compatibility shape outside those additive fields was retained.
- A Windows controller concurrency scenario had a 30-second ceiling below its
  measured healthy serialized cold-path time. The test ceiling was raised to
  90 seconds while retaining its revision/order assertions.
- T19 exposed a real performance defect: citation use-counter updates fired the
  same invalidation trigger as scope changes, so the next graph-auto pack
  rescanned up to 100k scopes. UPDATE invalidation now occurs only when the
  JSON scope value changes; insert/delete and actual scope changes still
  invalidate. Measured 100k pack p95 improved from 308.552 ms to 62.160 ms.
- The first unit test for the absolute SLO evaluator executed a live micro
  benchmark and was flaky under Windows load. It now tests deterministic
  boundary semantics; real latency stays in the 10k/100k perf jobs.
- At the user's request, upstream `fb6f957` was merged before closure. README
  and landing-site aesthetics were kept, while Run A's install/migration safety
  guidance and Run B's navigation entries were preserved and revalidated.

## Deferred gates

These are master-plan gates, not incomplete Run B work:

| Gate | Reason / owner |
| --- | --- |
| README/docs large-section content rewrite beyond the synced cosmetic redesign | Run D product-positioning gate. |
| Graph-first `mem_explore` and unified explore semantics | Run C E13-8 after unified graph schema/build. |
| Five-pass consolidate, promotion, dissent, and translation-quality workflow | Run C E12-5 through E12-8. |
| Qdrant L3 promotion and public LongMemEval/LoCoMo claims | Require later live-backend and external-dataset evidence. |
| v2.0.0 release, tag, PyPI publication, docs deployment, and live cutover | Run D/release authorization and rollback proof. |

## Recommended Run C starting point

Start with the graph contract before adding graph-facing UX:

1. E13-1 unified graph schema and stable identifiers.
2. E13-2 build pipeline, then E13-3 docs/facts ingestion and E13-4
   precomputation.
3. E13-7 JSON Canvas/HTML export, E13-8 flagship explore semantics, and E13-6
   impact CLI once the graph contract is stable.
4. E12-5 through E12-8 consolidate/promotion/dissent/quality workflows on top
   of the Run B lifecycle, taxonomy, and scoring evidence.
5. E11-5 SDK and E11-7 gateway OpenAPI only after the underlying contracts are
   locked by replay/scenario tests.

Preserve the 50-case composite gate, 1171-test repository baseline, fixed-runner
20% perf gate, absolute product SLOs, readonly invariants, additive alias
contracts, and reversible lifecycle receipts as Run C entry conditions.
