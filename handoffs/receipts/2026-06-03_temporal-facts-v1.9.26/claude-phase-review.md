## Temporal Fact View v1.9.26 — Phase-Matrix Review

Read everything in scope (core module, CLI parser+handler, tests, fixtures, docs, skill, version/nav/changelog/spec/roadmap/architecture). No files edited. Verifier receipts from parent reproduce against the code I read (version `1.9.26` in both `openclaw_mem/__init__.py:2` and `pyproject.toml:7`; registry/route/lint surfaces present).

### Top-line verdict
**Release/tag readiness: GO** with should-fix cleanups. No must-fix found — no correctness bug breaks a stated phase verifier or the Store/Pack/Observe ownership contract. Findings below are should/should-note quality and test-coverage gaps.

### Phase matrix

| Phase | Verdict | Note |
|---|---|---|
| P0 Contract freeze | **should-fix** | Schema, predicate registry, source-ref resolver, interval semantics, stable-id all implemented. But the on-disk fixture set (`tests/data/temporal_fact_view/TEMPORAL_FACT_VIEW_FIXTURES.v0.jsonl`) holds only 2 happy-path records; the spec's required coverage (stale/dangling/conflict/supersede/invalidate) lives in test *code*, not fixture data. Deliverable is thinner than the spec text claims. |
| P1 Deterministic core | **pass** | `facts.py` file/SQLite-backed, typed `SourceResolution` reasons, deterministic lint, `rebuild_from_records`. Rebuild-id stability test passes. No live memory-backend writes — receipt resolution is read-only `SELECT` on `observations`. |
| P2 Operator CLI | **should-fix** | assert/current/timeline/lint wired; lint exits nonzero (`cli.py:14392-14393`); bad source → bounded error JSON + exit 2 (`cli.py:14455-14457`). Missing direct test for the P2/lint exit-gate counterfactual (two overlapping *active* single-value facts without supersede → `single_value_interval_conflict`). |
| P3 Pack integration | **pass** (1 note) | ContextPack-compatible, cites assertion ref, budget+max_items trace, `allIncludedHaveSources`. Note: full pack JSON is not byte-stable across runs because `ts=utcnow_iso()` is embedded; only `bundle_text` is stable. No test pins byte-stability. |
| P4 Staleness/synth reuse | **pass** | Source-hash drift → `stale`, excluded from current truth by default, `--include-stale` opt-in (tested). Note: no explicit test for "supersede/refresh clears stale only with a new assertion receipt." |
| P5 Default route | **should-fix** | `route_fact_query` returns visible fact-pack receipt; fallback branches exist (`no_subject_detected`, `unknown_subject_or_no_current_facts`). Only the positive path is tested — the unknown-subject fallback (P5 verifier) has no test. |
| P6 Extraction assist | **pass** | `propose_extractions` and `measure_extraction_precision` both hard-code `writes_performed=False` / `apply_allowed=False`; source refs required; no apply lane exists. Review-only contract holds. |

### Must-fix
None.

### Should-fix (quality)
1. **Confidence-cap logic is partly dead and non-monotonic** — `source_confidence_cap` (`facts.py:445-454`):
   - `if len(resolved) >= 2 and len(kinds) >= 1:` — `len(kinds) >= 1` is always true when `resolved` is non-empty, so kind-diversity is never enforced. Two refs to the *same file/kind* are graded `corroborated`. This weakens the named risk-ledger control "over-confident source tiers" and the P1 lint guard.
   - Non-monotonic: a single `receipt` source caps at `operator_asserted` (tier 3), but adding a second receipt drops the cap to `corroborated` (tier 2) via the `>=2` branch. More evidence → lower allowed confidence; re-asserting after adding a corroborating receipt could spuriously trip `confidence_exceeds_source_cap`. Likely intended `len(kinds) >= 2`.
2. **P0 fixture coverage** — add stale/dangling/conflict/supersede/invalidate as actual fixture rows (or split files) so the P0 "fixture set" deliverable matches the spec rather than being satisfied only by imperative test code.
3. **Missing counterfactual tests** (none currently fail, but the exit-gates are unproven):
   - lint single-value overlap conflict on two active facts without supersede (P2).
   - route unknown-subject / no-current-facts fallback returns `fact_view_used=false` (P5).
4. **Extractor predicate list duplicated** — `propose_extractions` regex hard-codes the predicate alternation (`facts.py:1073-1075`) independently of `PREDICATE_REGISTRY`; registry changes won't propagate. Maintainability only.

### Risk-area readouts (all clear)
- **Truth-owner / source-link:** View stays derived. `resolve_source_ref` (`facts.py:379-433`) treats `memory`/`daily_log`/`episodic` as file hash+existence checks and `receipt` as read-only `observations` SELECT — no memory-backend coupling, no writes to Store. Pack reuses `context_pack_v1` (Pack ownership preserved); pack notes warn against treating stale/excluded as current truth.
- **CLI contract:** `graph fact` is a pure sub-subparser under `graph` (`cli.py:19757-19842`); no new top-level command, no Gateway/cron/topology surface. Error path is bounded JSON + nonzero exit. lint exits 1 on unresolved errors; unsupported subcommand exits 2.
- **Pack/trace/citation:** every included item carries `source_refs` and an `assertion_ref` citation; budget/max_items exclusions are traced with reasons; at least one item always retained so a single over-budget fact isn't silently dropped.
- **Extraction review-only:** enforced in both library and CLI; `--source-ref` required; `writes_performed`/`apply_allowed` constant false; `measure-extraction` cannot apply.
- **Docs hygiene:** version consistent (init + pyproject), CHANGELOG `[1.9.26]`, `docs/releases-v1.9.26.md`, mkdocs nav entry (`mkdocs.yml:86`), README rows, roadmap §1.7d, architecture "SHIPPED v1.9.26", spec status lines all aligned. `mkdocs build --strict` passes per receipts.

### One observation worth surfacing
`handoffs/receipts/2026-06-03_temporal-facts-v1.9.26/claude-phase-review.md` is a 0-byte placeholder — presumably the intended sink for this review. I did not write to it (review-only). Flag it so it doesn't ship empty.
I have enough from the source, tests, CLI handlers/parser, and docs. (Bash was blocked by the sandbox, so I reviewed statically rather than executing tests.)

## Findings - temporal fact materialized view

### Must-fix
None that corrupt the Store or bypass review. The core safety invariants hold: `assert`/`invalidate` require resolved sources (`require_resolved_sources=True`, `facts.py:639`), extraction is write-free (`writes_performed=False`, `apply_allowed=False`), and there is no `apply` subcommand wired in the parser.

### Should-fix
1. `source_confidence_cap` is the enforcement point for "confidence capped by source evidence" and is logically broken (`facts.py:445-454`).
   - `if len(resolved) >= 2 and len(kinds) >= 1` - the `len(kinds) >= 1` clause is always true, so any 2+ resolved sources return `corroborated`, including two refs to the same doc. Sources are never de-duped (`build_fact_record:494`), so `--source-ref doc:a.md --source-ref doc:a.md` inflates the cap. Looks like it was meant to be `len(kinds) >= 2`.
   - Inversion: one `receipt` -> `operator_asserted` (3); two `receipt`s -> `corroborated` (2). Adding evidence lowers the cap, so a documented `--confidence-tier operator_asserted` assert that passes with one receipt is rejected with two (`confidence_exceeds_source_cap`). This is the strongest issue in the diff.

2. Single-value conflict is not enforced at assert time (`facts.py:605-650`). The registry marks `status`/`source_of_truth`/etc. as `single` and docs say overlapping active facts "must not" exist, but `assert_fact` never checks overlap - it only requires a matching `--supersedes`. Two overlapping active `status` facts can be asserted, and `current_facts` will return both as current truth; only `lint` (out-of-band) flags it as `single_value_interval_conflict`. Truth-ownership would be tighter if `assert` refused the conflicting write, or at least the docs stated lint is the only gate.

3. ContextPack citations omit evidence sources (`facts.py:962-967`). `citations.recordRef` carries only `assertion_ref.ref` (the receipt). For a "source-linked" pack the evidence `source_refs` appear only in `bundle_text`, not structurally in the item's citations. `trace.allIncludedHaveSources` is computed, but consider surfacing source refs in citations so a consumer can cite evidence, not just the assertion act.

### Minor / nits
- `rebuild --allow-dangling-source` (`cli.py:14450`) bypasses source resolution, contradicting the doc line "A fact without a resolvable source is rejected." It defaults off and is fixture-scoped, but the doc should note the exception.
- `propose` with neither `--text` nor `--file` silently yields `proposal_count: 0` rather than an arg error (`cli.py:14428-14437`).
- `_fact_pack_text(item)` is computed twice per item (budget projection + ContextPack item) - harmless perf nit (`facts.py:947,966`).
- CLI contract is otherwise clean: `lint` exits 1 on findings, other failures exit 2 via `_graph_fact_error`, errors carry structured `issues`. Good.

### Release verdict
Conditional go. No data-integrity or review-bypass blockers; review-only extraction and source-resolution gating are correctly enforced, and `tests/test_graph_facts.py` covers rebuild idempotency, dangling rejection, supersede/invalidate, stale drift, pack trace, route, and CLI end-to-end. Fix the `source_confidence_cap` logic (#1) before release - it silently mis-tiers confidence, which is the feature's central trust claim. #2 and #3 can be fast-follows if documented. Note: I could not execute the suite (sandbox blocked `python -m pytest`/`unittest`); recommend confirming green locally before tagging.
