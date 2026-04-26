# Changelog

All notable changes to **openclaw-mem** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Hardened episodic conversation auto-capture so runtime recall blocks, channel metadata envelopes, internal delivery markers, and assistant control-only replies are stripped before events enter the episodic spool.
- Added regression coverage for sanitized conversation extraction to keep public query/replay surfaces focused on user-visible dialogue rather than runtime transport artifacts.
- Aligned mem-engine auto-capture `maxCharsPerItem` runtime normalization with the plugin schema guardrail floor so too-short capture snippets fail closed consistently.
- Added a default uv `dev` dependency group for pytest and documented the local verification command in the contributor workflow.
- Promoted the docs front door into a clearer operator path: 60-second proof, quickstart, install modes, automation status, and product roadmap are now visible from the top nav and landing surfaces.
- Fixed repo-internal docs links that pointed outside MkDocs' docs tree so `mkdocs build --strict` can pass cleanly again.
- Hardened the experimental GBrain sidecar call wrapper against malformed JSON, oversized stdout, timeouts with large partial output, and non-zero calls with empty stderr while keeping fail-open receipts bounded.
- Added `scripts/operator_template_demo.sh`, a synthetic one-command operator handoff template that generates a temporary decision/runbook workspace, ingests JSONL into an isolated DB, and emits a cited pack receipt without touching OpenClaw config or the host memory journal.
- `optimize review` now emits bounded `signals.importance_drift` spot-checks (score-vs-label mismatch, missing/unparseable metadata, conservative high-risk under-label content detection, and normalized label distribution) while staying query-only and proposal-only.
- `optimize review` now emits bounded read-only `signals.soft_archive_candidates` proposals for stale low-importance observations (`ignore` / `nice_to_have`) with explicit protections for `must_remember`, recently-used lifecycle rows, and already-archived rows; no write path was added and default behavior remains query-only/proposal-only.
- `optimize evolution-review` now carries compact upstream importance-drift counters for operator visibility without widening apply behavior.
- Added a deterministic read-only `importance_drift.policy_card` gate (`openclaw-mem.optimize.importance-drift-policy-card.v0`) with conservative count/rate thresholds and compact text-line rendering in optimize review/evolution outputs.
- Wired the importance-drift gate into optimize-assist promotion/controller receipts as a non-mutating constraint (`promotion_gates.importance_drift_gate`) and surfaced it in posture review readiness checks.
- Added operator-selectable importance-drift threshold profiles (`strict` default, `balanced`, `lenient`) to `optimize review`, `optimize evolution-review`, and `tools/optimize_assist_runner.py`, with profile metadata now embedded in policy-card JSON and compact text output.
- Added a bounded historical baseline comparator for importance drift in optimize-assist promotion receipts (`promotion_gates.importance_drift_gate.baseline_comparator`) so the lane distinguishes transient spikes from persistent drift posture using recent native controller receipts.
- Extended posture-review output to carry live importance-drift profile/baseline metadata and persistent-drift run counters without widening write authority.
- Hardened secret-like detection for capture lanes by adding deterministic high-risk patterns (OpenAI `sk-proj` keys, `github_pat` tokens, AWS secret-access-key assignments, and long Bearer auth values) across mem-engine autoCapture and episodic CLI helpers, while keeping autoCapture receipts aggregate-only (`filteredOut.secrets_like`) so skip evidence stays bounded and non-leaking.
- Added a shared synthetic secret-detector golden corpus (`tests/data/SECRET_DETECTOR_GOLDEN.v1.json`) and wired it into mem-engine source-contract guards, episodic CLI secret guard tests, and sidecar/plugin redaction coverage so drift is caught from one source of truth.
- Expanded sidecar/plugin redaction coverage for `github_pat` and AWS secret-access-key assignment patterns to match the hardened high-risk corpus.
- Added a bounded runtime-side black-box summary test for `extensions/openclaw-mem` (`toolResultSummary.js` + `toolResultSummary.test.mjs`) so episodic tool-result summaries are validated against the shared secret-detector golden corpus for leak suppression and benign-pass behavior.
- Added a tiny fake-API end-to-end plugin harness test for `tool_result_persist` (`extensions/openclaw-mem/toolResultPersistE2E.test.mjs`) so emitted episodic `tool.result` JSONL rows are verified on disk for redaction, leak suppression, bounded summaries, explicit stdout/stderr-style summary collapse (`result captured (output redacted)` posture), and benign non-stdout text retention.
- Hardened plugin tool-result summary behavior for structured JSON payloads: JSON bodies that carry output-like fields (`stdout`/`stderr` and aliases) now collapse to bounded `result captured (output redacted)` posture, while benign JSON/docs payloads without output fields remain informative.
- Added a precision guard for docs/prose mentions of JSON-escaped output-key strings (for example `\"stdout\"`, `\"stderr\"`) so benign explanatory text stays informative instead of collapsing to redacted-output posture.
- Tightened malformed-JSON fallback precision for tool-result summaries: JSON-like payloads that start with `{` but only mention quoted `"stdout"`/`"stderr"` inside prose string content now stay informative across both top-level and nested object/array contexts, while true key-like malformed output fields (including nested `stdout`/`stderr` keys in truncated JSON) still collapse to bounded redacted-output posture.
- Extended malformed-JSON fallback boundary coverage to root array-first (`[`) payloads with full `OUTPUT_FIELD_KEYS` parity: malformed array docs/prose that only mention quoted `"stdout"`/`"stderr"` terms inside string content now stay informative, while malformed array payloads containing true nested output keys (`stdout`, `stderr`, `raw_stdout`, `raw_stderr`, `tool_output`, `command_output`) still collapse to bounded redacted-output posture without leaking synthetic high-risk needles.
- Exported `OUTPUT_FIELD_KEYS` from `toolResultSummary.js` as a readonly runtime constant and introduced a shared malformed-array output-key test table helper so alias coverage references one explicit list.

### Testing

- Added optimize-review regression coverage for importance-drift JSON shape, top-bounded output, mismatch detection, text rendering, and read-only/query-only posture.
- Added optimize-review regression coverage for archive-first proposal candidates, including stale low-importance detection, `must_remember` exclusion, recent-use protection, already-archived exclusion, and `--top` bounded JSON output.
- Added regression coverage for importance-drift gate pass/fail policy behavior, runner promotion-gate integration, and posture-review gate visibility.
- Added regression coverage for deterministic profile pass/fail behavior, runner baseline-comparator transient-vs-persistent classification, parser flag propagation, and posture-review baseline surface fields.
- Added secret-hardening regression coverage for episodic extraction/guardrails (new token families redacted with null payload, no secret echo in guard errors) plus mem-engine autoCapture receipt-boundedness/source-contract checks.
- Added shared-golden regression checks in both Python and Node test lanes, including `extensions/openclaw-mem-engine/secretDetectorGolden.test.mjs`, so mem-engine and sidecar/plugin anchors stay in sync with the shared corpus.
- Added sidecar/plugin behavioral runtime coverage for emitted tool-result summaries via `extensions/openclaw-mem/toolResultSummary.test.mjs` (invoked by `tests/test_plugin_episodic_summary_runtime.py`).
- Added sidecar/plugin behavioral runtime coverage for the full `tool_result_persist` episodic append path via `extensions/openclaw-mem/toolResultPersistE2E.test.mjs` (invoked by `tests/test_plugin_episodic_summary_runtime.py` with `--experimental-strip-types`), including a stdout/stderr-style payload assertion that emitted `tool.result` summaries collapse to bounded redacted-output posture and never leak raw output needles into the JSONL record.
- Extended sidecar/plugin runtime coverage so structured JSON tool outputs with `stdout`/`stderr` fields are asserted end-to-end (`tool.result` JSONL no-leak + redacted-output collapse), and benign structured JSON/docs payloads are asserted to remain informative.
- Extended sidecar/plugin runtime coverage with a negative-control case where benign docs/prose text mentions JSON-escaped `"stdout"`/`"stderr"` keys; verifier now asserts emitted `tool.result` JSONL stays informative and does not falsely collapse to redacted-output posture.
- Extended sidecar/plugin runtime coverage with malformed-JSON boundary assertions: `{`-prefixed payloads with quoted `"stdout"`/`"stderr"` terms inside prose string content must remain informative in both top-level and nested object/array cases, while malformed key-like output fields (top-level and nested) still must collapse to bounded redacted-output posture.
- Extended sidecar/plugin runtime coverage with malformed array-first boundary assertions and full `OUTPUT_FIELD_KEYS` parity: `[`-prefixed malformed payloads that quote `"stdout"`/`"stderr"` inside prose string content must remain informative, while malformed array payloads with real nested output keys (`stdout`, `stderr`, `raw_stdout`, `raw_stderr`, `tool_output`, `command_output`) must still collapse to bounded redacted-output posture and remain non-leaking in emitted JSONL.
- Added a contract test that enforces parity between runtime `OUTPUT_FIELD_KEYS` and malformed-array key tables, so future runtime key changes fail fast unless alias-coverage tables are updated.

## [1.8.0] - 2026-04-18

### Changed

- `pack --use-graph=auto` now productizes graph participation behind explicit scope, trigger, and latency receipts, so project-scoped packs can opportunistically pull topology evidence without forcing graph-only cost on routine turns.
- Added dedicated agent-memory skill guidance for bounded packs: prefer `openclaw-mem pack --trace`, protected tail continuity, and `--use-graph=auto` for repo/product queries.
- Added a governed optimization bridge for low-risk observation lifecycle maintenance: `optimize evolution-review` now packetizes stale-candidate updates, `optimize governor-review` can approve them explicitly, and `optimize assist-apply` can execute the bounded write with before/after + rollback receipts.
- Narrowed the first shipped apply whitelist to lifecycle stale-candidate fields plus bounded `optimization.assist` metadata so the write lane stays auditable and rollbackable.
- Added `tools/optimize_assist_runner.py` as the dedicated scheduled-worker surface for the governed optimize-assist lane, plus deployable OpenClaw/systemd enablement docs and snippet assets.
- Updated README, deployment guidance, optimization specs, and public skill-card docs so the shipped apply lane is described in external-safe product language.
- Added the next-phase planning spec `docs/specs/self-optimizing-memory-autonomy-ramp-v0.md` to define the bounded path from governed canary toward higher-autonomy low-risk evolution.
- Expanded the governed canary whitelist to include bounded low-risk importance downshifts (`adjust_importance_score`), plus governor/runner flags for approving that class without opening a general-purpose edit lane.
- Added Phase 1 effect-receipt foundation for optimize assist: applied rows now carry bounded `optimization.assist.effect` metadata and assist runs emit a dedicated effect artifact as the baseline measurement surface for later autonomy phases.
- Added the Phase 2 classifier foundation for optimize assist: evolution packets now emit evidence-backed `risk_level`, `risk_reasons`, and `auto_apply_eligible`, and governor approval flags fail closed when a candidate is no longer low-risk eligible.
- Added the first Phase 3 family-cap foundation for optimize assist: assist apply now enforces bounded per-run / rolling-24h caps for `adjust_importance_score`, and after receipts summarize applied action counts for cap replay.
- Added the Phase 4 controller/watchdog lane for optimize assist: the scheduled runner now persists controller state, emits controller receipts, and pauses itself on missing effect receipts, regressed effect summaries, or rollback replay failure receipts.
- Added the Phase 5 promotion-gate lane for optimize assist: the runner now accepts explicit promotion gate receipts and can promote persisted mode to `auto_low_risk` when thresholds stay green.
- Added `docs/specs/self-optimizing-memory-max-safe-autonomy-roadmap-v0.md` as the post-Phase-5 blade map for pushing from bounded low-risk autonomy toward a near-ceiling safe autonomy system without collapsing governor boundaries.
- Added the first Phase 6 blade for optimize assist: `optimize effect-followup` now ingests prior effect-batch receipts, compares them to current observation/recent-use state, and emits delayed read-only follow-up effect judgments.
- Added the first Phase 7 blade for optimize assist: `optimize verifier-bundle` now scans recent assist receipts, checks effect-receipt completeness + cap integrity, and runs rollback replay simulation on a temporary DB clone.
- Completed Phase 8 for optimize assist: `optimize challenger-review` now emits auditable disagreement clusters and quarantine recommendations, and the scheduled runner can require challenger agreement before promotion gates pass.
- Added the first Phase 9 blade for optimize assist: evolution-review can now emit bounded score-label alignment candidates (`delta = 0`, `reason_code = label_alignment`) as a separately-bounded low-risk family.
- Added the first Phase 10 blade for optimize assist: runner controller state now tracks `soak_green_cycles` and `regression_strikes`, supports soak-based promotion, and can demote `auto_low_risk` back to `canary_apply` when gates fail.
- Closed the remaining Phase 8-10 controller gaps for optimize assist: the runner now writes `governor-filtered.json`, can enforce challenger-driven quarantine before assist apply, persists family-level enable/disable/quarantine state, and runs native `verifier-bundle` each cycle for first-party gating.
- Added the Phase 11 posture surface for optimize assist: `optimize posture-review` now reads native runner receipts and emits a bounded `near_ceiling_ready` verdict.
- Added a controller-gated OpenClaw cron snippet for optimize assist dry-run bring-up: `docs/snippets/openclaw-cron.optimize-assist-controller-dry-run.json`.
- Added `docs/specs/optimize-assist-nine-point-hardening-roadmap-v0.md` to define the shortest hardening-first path from the current ~5.5-6/10 posture toward a truthful 9/10 near-ceiling safe-autonomy claim.
- Landed the first hardening trio for optimize assist: challenger and runner now share a canonical family taxonomy, controller state writes are lock-serialized with digest-checked atomic persistence, and promotion truth is now computed from native runner/verifier/challenger receipts instead of trusting external promotion-receipt input.
- Hardened the optimize-assist controller for Blade D+E: recent malformed assist/effect receipts now degrade fail-closed through watchdog accounting, malformed persisted controller state aborts instead of silently resetting, unsigned legacy controller state is now rejected by default with an explicit one-shot migration path, apply-capable modes now pause when rollback replay evidence is missing, and the runner path is now covered by real subprocess end-to-end proofs.

### Testing

- Added CLI/parser + mutation-path coverage in `tests/test_optimize_evolution_review.py`, `tests/test_optimize_assist_apply.py`, and `tests/test_optimize_governor_review.py`.
- Added runner coverage in `tests/test_optimize_assist_runner.py`.
- Re-ran the optimize review/governor/apply suite plus policy/consolidation regression coverage.
- Added regression coverage for importance-adjustment proposal, approval, assist-apply, and runner flag propagation.
- Added assist-apply coverage for effect artifact emission and persisted row-level effect metadata.
- Added classifier coverage for low-vs-medium importance candidates and fail-closed governor behavior on medium-risk packets.
- Added assist-apply and runner coverage for importance-family caps and propagated cap flags.
- Added runner coverage for controller pause behavior and promotion-gate driven `auto_low_risk` promotion.
- Added parser + follow-up effect coverage in `tests/test_optimize_effect_followup.py`.
- Added parser + verifier bundle coverage in `tests/test_optimize_verifier_bundle.py`.
- Added parser + challenger review coverage in `tests/test_optimize_challenger_review.py`.
- Expanded runner coverage so challenger receipts are written every cycle and promotion can fail closed on challenger disagreement.
- Added evolution-review coverage for score-label alignment candidates.
- Added runner coverage for soak-based promotion counters and demotion from `auto_low_risk`.
- Added parser + posture verdict coverage in `tests/test_optimize_posture_review.py`.
- Expanded `tests/test_optimize_assist_runner.py` with malformed-state / malformed-receipt fail-closed coverage, unsigned-legacy migration coverage, missing-rollback gating coverage, and real subprocess end-to-end runner proofs for promotion, pause, abort, and concurrent controller revision serialization paths.

## [1.6.0] - 2026-04-15

### Changed

- Clarified the mem-engine **single-write-path posture** across plugin schema help, mem-engine docs, and source markers so slot ownership stays explicit when `openclaw-mem-engine` is active.
- Re-stated the graph boundary in pack-facing docs: graph may improve bounded pack selection/coverage, but it does not become a competing truth owner.
- Reframed mem-engine live-turn recall as **Proactive Pack** across README, docs, skill cards, and plugin metadata so the public story stays aligned with `Store / Pack / Observe`.
- Added `openclaw-mem artifact compact-receipt` as the first shipped **command-aware compaction sideband** contract: compact command output can now point back to a recoverable raw artifact instead of silently replacing it.
- Added the command-aware compaction adoption note + `command-aware-compaction-sideband-v0` spec so the product line explicitly absorbs command-aware compaction as an Observe-layer pattern, not as a shell-hook rewrite of canonical evidence.
- Extended the context-supply-chain blueprint so Observe now explicitly covers compacted-command sideband receipts alongside raw artifact offload.
- Landed the first **pack consume path** for compaction receipts: when pack selects a sideband receipt, it now prefers `compact.text` in bundle output, emits `compaction_sideband` recovery metadata, and records the preference in pack trace extensions.
- Added `openclaw-mem artifact rehydrate` as a bounded raw-recovery helper for compaction receipts / raw artifact handles, and added lightweight family classification for `git_diff`, `test_failures`, and `long_logs` compaction lanes.
- Added advisory-only `compaction_policy_hints` to pack / trace outputs so family metadata can shape operator guidance without mutating retrieval ranking.
- Added README / QUICKSTART operator examples for compaction receipts and bounded raw rehydrate.
- Added a public-safe showcase proof for command-aware compaction plus `compaction-family-policy-cards-v0` so the advisory family lane is now documented as an operator surface.
- Extended the showcase proof pack with synthetic `git_diff` and `test_failures` examples covering receipt -> rehydrate -> pack -> advisory guidance.
- Updated external docs + skill-card surfaces so compaction evidence is framed as orientation-first, raw-evidence-second behavior instead of durable truth.

### Testing

- Added `tests/test_mem_engine_write_authority.py` to lock the single-write-path wording across docs/schema/source markers.
- Added `tests/test_proactive_pack_docs.py` to lock the public Proactive Pack wording across docs and plugin metadata.
- Added parser/CLI contract coverage for `artifact compact-receipt` and `artifact rehydrate` in `tests/test_artifact_cli_parser.py` and `tests/test_artifact_cli.py`.
- Added pack-path coverage for compaction receipts, raw-rehydrate hints, family classification, and advisory `compaction_policy_hints` in `tests/test_cli.py`.

## [1.5.1] - 2026-04-13

### Changed

- Shipped a stable `openclaw-mem.context-pack.v1` contract from `openclaw-mem pack` while keeping the legacy top-level `bundle_text` / `items` / `citations` keys for migration safety.
- Reframed the public product surface around **Store / Pack / Observe** so docs, quickstart, and architecture all describe the same bounded-context supply-chain story.
- Added deterministic artifact CLI contract coverage and exact-key contract tests for the new `context_pack` payload.
- Carried the already-landed mem-engine prompt-hook migration line into the current mainline release surface so route-auto + context-pack docs stay aligned with shipped behavior.

### Testing

- Re-ran `python -m unittest tests.test_cli tests.test_json_contracts tests.test_artifact_sidecar tests.test_artifact_cli_parser tests.test_artifact_cli`.
- Re-ran the same suite on `main` after merge conflict resolution to confirm the trust-policy contract path also accepts additive `context_pack` output.

## [1.4.3] - 2026-04-09

### Fixed

- The CJK fallback search path now uses the same scope-inference fallback as the main FTS route: scoped CJK queries no longer drop valid file/repo-backed capture rows just because `detail.scope` is missing.

### Testing

- Added CJK-scope regression coverage in `tests/test_route_a.py` for repo-root inference when `detail.scope` is absent.
- Re-ran `python3 -m unittest tests/test_route_a.py tests/test_graph_match_cli.py tests/test_autonomous_default_routing_cli.py tests/test_cli.py`.

## [1.4.2] - 2026-04-09

### Fixed

- `graph match` now applies scope filtering more truthfully for file/repo-backed capture rows: if a row lacks explicit `detail.scope`, the filter falls back to project inference from the candidate/repo-root path instead of discarding the row before candidate grouping. This unblocks production `graph match` / `route auto` on real host capture data.
- `graph synth compile` now commits its newly written synthesis card before returning, so file-backed / production DB invocations no longer report a `cardRef` that vanishes on reconnect.
- `graph synth refresh` now commits the new card + superseded-card update before returning, keeping refresh lifecycle state durable on file-backed / production DBs.

### Testing

- Added regression coverage in `tests/test_graph_match_cli.py` for scope-filter fallback via repo-root inference when `detail.scope` is missing.
- Added file-backed persistence coverage in `tests/test_cli.py` for `graph synth compile` and `graph synth refresh`.
- Re-ran `python3 -m unittest tests/test_graph_match_cli.py tests/test_autonomous_default_routing_cli.py tests/test_cli.py`.
- Re-ran host-local proof against `/root/.openclaw/memory/openclaw-mem.sqlite`; `graph match` and `route auto` now surface `graph_match`, and host-local patched proof shows `preferredCardRefs` / `coveredRawRefs`.

## [1.4.1] - 2026-04-09

### Changed

- `openclaw-mem route auto` now propagates **synthesis-aware coverage receipts** when a fresh synthesis card truthfully covers multiple matched raw refs.
  - graph-route selections now expose `preferredCardRefs` + `coveredRawRefs` in the route-auto JSON path
  - candidate rows now include additive `graph_consumption` metadata instead of forcing graph-as-truth behavior
  - route-auto remains fail-open when graph-synthesis enrichment is unavailable or errors
- `openclaw-mem-engine` `autoRecall.routeAuto` now renders the same synthesis-aware preference in its injected routing hint block and receipt counters.
- Added a deterministic repo-level smoke script: `tools/route_auto_synthesis_smoke.py`.
- Added a dedicated operator card for this lane: `skills/route-auto-synthesis.ops.md`.
- Reconciled docs/install/operator surfaces so route-auto, the mem-engine hook, and the skill cards all describe the same synthesis-aware contract.

### Testing

- Expanded `tests/test_autonomous_default_routing_cli.py` to cover synthesis-aware route-auto receipts and fail-open enrichment errors.
- Expanded `extensions/openclaw-mem-engine/routeAuto.test.mjs` to cover synthesis-aware rendering + receipt counters.
- Re-ran targeted hook-contract coverage with `tests/test_mem_engine_route_auto_hook.py` and the deterministic smoke `tools/route_auto_synthesis_smoke.py`.

## [1.4.0] - 2026-04-08

### Changed

- Added a first production-safe **verbatim semantic lane** for episodic evidence recall.
  - new `openclaw-mem episodes embed` command builds/search-refreshes embeddings over redacted `episodic_events.search_text`
  - `openclaw-mem episodes search` now supports `--mode lexical|hybrid|vector`, optional `--query-en`, and `--trace` receipts for FTS/vector/fused rankings
  - hybrid/vector episodic retrieval stays additive, scope-aware, read-only, and fail-open when the vector lane is unavailable
  - new `episodic_event_embeddings` table stores deterministic `search_text_hash` receipts so embedding refreshes can detect substrate changes without mutating episodic truth
- Added focused docs and operator guidance for the new lane in `docs/verbatim-semantic-lane.md`, `docs/specs/verbatim-semantic-lane-v0.md`, and `skills/verbatim-semantic-lane.ops.md`.
- Reconciled docs truth across README / QUICKSTART / architecture / mem-engine / dual-language / roadmap / MkDocs navigation so the new lane is described consistently as a retrieval tactic rather than a new memory type.

### Testing

- Added episodic CLI regression coverage for `episodes embed`, hybrid/vector parser flags, vector-backed session grouping, and hybrid fail-open fallback when embeddings are unavailable.
- Re-ran focused episodic/router coverage (`tests/test_episodes.py`, `tests/test_autonomous_default_routing_cli.py`) plus broader CLI/docs-memory regression coverage (`tests/test_cli.py`, `tests/test_docs_memory.py`).

## [1.3.2] - 2026-04-06

### Changed

- Added an optional `openclaw-mem-engine` prompt hook under `autoRecall.routeAuto`.
  - calls `openclaw-mem route auto` before agent start
  - injects a bounded routing hint block into live turns when graph-semantic or transcript recall returns useful guidance
  - remains fail-open on timeout/runtime failure
- Promoted `openclaw-mem-engine` package metadata from `0.0.1` to `0.0.2` to reflect the new prompt-hook surface.

### Testing

- Added `extensions/openclaw-mem-engine/routeAuto.test.mjs` behavioral coverage for graph/transcript route rendering and fail-open subprocess failure.
- Added `tests/test_mem_engine_route_auto_hook.py` schema + source marker coverage.

## [1.3.1] - 2026-04-06

### Changed

- Added `openclaw-mem graph readiness` as a bridge surface between graph cache freshness, topology-source drift, and graph-match support-plane availability.
  - emits a machine-readable `green/yellow/red` verdict for unattended routing
  - checks: freshness, non-empty cache, topology source presence, topology source drift tolerance, and recent graph-support observations
- Added `openclaw-mem episodes search` to support transcript-style recall over episodic events.
  - uses SQLite FTS5 over bounded `search_text`
  - groups matched events by `session_id`
  - returns a replay hint for each session
- Added `openclaw-mem route auto` as a deterministic default router across graph-semantic matching and episodic transcript recall.
  - consults `graph readiness` first
  - prefers graph-semantic only when the graph is ready **and** returns candidates
  - otherwise fails open to `episodes search`

### Testing

- Added `tests/test_autonomous_default_routing_cli.py` coverage for `episodes search`, `graph readiness`, and `route auto` selection behavior.

## [1.3.0] - 2026-04-06

### Changed

- Added `openclaw-mem graph match` as a bounded local-first graph-semantic v0 surface for idea → project routing.
  - groups local graph evidence into 3–10 candidate projects
  - returns explanation paths + provenance refs for each candidate
  - stays fail-open so baseline recall/pack remain usable when graph-semantic data is weak or absent
- Added `openclaw-mem graph health` to summarize graph cache freshness, node/edge counts, last refresh timestamp, and staleness for daily canary / autonomous-readiness checks.
- Recut public roadmap/docs truth for graph-semantic v0 and rollout/deployment guardrail positioning, including the `1.6` rollout ladder vs `1.6a` platform/deployment guardrail split.
- Updated the agent-memory operating skill surfaces to route idea → project requests through `graph match` and to recommend `graph health` before unattended graph-semantic use.
- Added `openclaw-mem optimize consolidation-review` as a recommendation-only episodic maintenance observer for dream-style candidate generation without canonical rewrite.
  - scans `episodic_events` under strict zero-write/query-only posture
  - emits three bounded candidate families: summary compression groups, archive-review rows near GC horizon, and cross-session link proposals
  - includes source episode refs/provenance in the JSON report `openclaw-mem.optimize.consolidation-review.v0`
  - explicitly records `policy.canonical_rewrite=forbidden` so consolidation stays review-gated rather than silently mutating memory truth
- Documented the new consolidation-review slice in `README.md`, `QUICKSTART.md`, `docs/about.md`, `docs/reality-check.md`, `docs/roadmap.md`, `docs/specs/self-optimizing-memory-loop-v0.md`, and added `docs/specs/dream-style-consolidation-review-v0.md` as the focused design note.
- Added use-based decay v0 as a recommendation-only recent-use protection layer for review commands.
  - `optimize review` now scans recent `pack_lifecycle_shadow_log` rows and emits `signals.recent_use` plus `staleness.protected_recent_use`
  - old rows still being selected into packs are protected from naive age-only stale recommendations
  - `optimize consolidation-review` now protects archive candidates when their episode refs point at observations with recent pack selection
  - added `--lifecycle-limit` to both review commands to bound lifecycle evidence scanning
- `optimize consolidation-review` link candidates now use a bounded hybrid gate when lifecycle rows exist: receipt-derived co-selection remains the default path, with capped lexical low-confidence backfill for recall recovery.
  - new CLI knob: `--link-lexical-backfill-max` (default: `1`) controls how many lexical-only cross-session pairs may backfill when lifecycle evidence exists
  - link items now expose inspectable `evidence_mode` + `confidence` and `signals.link_evidence` carries hybrid-gate counters (`lexical_backfill_pairs`, candidate/suppressed counts, gate metadata)
  - cold-start behavior still supports lexical fallback when lifecycle evidence is unavailable
- `optimize consolidation-review` link confidence/ranking is now evidence-weighted (`evidence_weighted_v0`) instead of fixed mode-only constants.
  - per-link `confidence` now blends inspectable components (`co_selection_events`, `shared_selected_count`, lexical overlap score, shared token count) with mode-specific base/cap weights
  - each link item now includes `confidence_components` for transparent scoring receipts
  - `signals.link_evidence.confidence_model` now publishes mode weights/caps and normalization constants used by the scorer
- `optimize consolidation-review` receipt-backed link confidence now adds an explicit lifecycle recency component (`co_selection_recency`) so newer co-selection evidence scores higher than stale co-selection evidence.
  - receipt evidence now emits `co_selection_last_ts`, `co_selection_recency_days`, and `co_selection_recency_score`
  - `confidence_components` now includes recency inputs/weights/contributions without changing recommendation-only zero-write behavior
- Documented use-based decay v0 in `README.md`, `QUICKSTART.md`, `docs/about.md`, `docs/reality-check.md`, `docs/specs/self-optimizing-memory-loop-v0.md`, and `docs/specs/use-based-decay-v0.md`.

### Testing

- Added graph query regression coverage for `query_graph_health` plus CLI coverage for `graph match` candidate grouping / explanation-path receipts.
- Added `tests/test_optimize_consolidation_review.py` coverage for parser wiring, zero-write JSON contract, summary/archive/link candidate detection, recent-use archive protection, and scope/session filtering.
- Expanded `tests/test_optimize_consolidation_review.py` coverage for evidence-weighted link confidence receipts (`confidence_components`) and stronger co-selection → higher confidence ordering.
- Added targeted recency-weighting coverage in `tests/test_optimize_consolidation_review.py` to verify equal-count receipt pairs score higher when lifecycle co-selection is newer.
- Expanded `tests/test_optimize_review.py` coverage for `--lifecycle-limit`, `signals.recent_use`, and stale-candidate protection when old rows still show recent pack selection.


## [1.2.0] - 2026-03-25

### Changed
- `openclaw-mem docs search` now supports `--scope-repos <repo> [<repo> ...]` for exact repo-allowlist candidate pushdown in both FTS and vector docs retrieval paths.
- `openclaw-mem-engine` docs cold lane now pushes resolved repo allowlists into the CLI for scoped queries, and cold-lane receipts/logs carry `pushdownRepos` + `pushdownApplied` alongside candidate counters.
- Recorded the follow-up posture explicitly in docs truth: reducing scoped overfetch is deferred to a later optimization phase after the broader development line stabilizes.
- Simplified the root `LICENSE` file to the canonical MIT text so GitHub/license scanners can detect a standard license instead of showing `Other`/`Unknown`, while preserving the repo's dual-license contract (`MIT OR Apache-2.0`) in `README.md` and `LICENSE-APACHE`.
- Removed the redundant `LICENSE-MIT` file now that root `LICENSE` already carries the canonical MIT text; dual-license docs now point to `LICENSE` + `LICENSE-APACHE` only.
- Tightened relaunch release surfaces around one consistent getting-started sequence (`prove locally`, `sidecar default`, `optional engine`) and added `docs/launch/release-surface-proof-pack-v0.md` as the release-note/hero/install sync proof card.
- Finalized the relaunch release-note body source in `docs/launch/release-note-body-v0-final.md` and executed the proof-first relaunch checklist as PASS 4 release-candidate closure.
- Completed PASS 4 external-language hygiene pass: removed internal writing-framework labels from public README/docs surfaces, moved launch-governance links under explicit maintainer-only sections, and added scope notes across `docs/launch/*` to keep internal vs external narratives clearly separated.

## [1.1.0] - 2026-03-10

### Changed

- `graph query provenance` now supports `--source-path` filtering (path before `#anchor`) so provenance concentration checks can scope deterministically to one topology source while preserving optional anchor-level breakdowns.

- `graph query provenance` now supports `--source-path-prefix` filtering (path before `#anchor`) for deterministic provenance-family slicing without requiring exact file-path matches.

- `graph query provenance` now supports source-level grouping (`--group-by-source`) that collapses line-anchored provenance keys into path-level concentration views while preserving edge-type breakdowns.

- Added parser regression coverage for NFKC-normalized full-width bracket wrappers in task markers (｛TODO｝ / ［TODO］).

- Expanded triage task-marker docs/examples to include NFKC-normalized full-width bracket wrappers (`｛TODO｝ ...`, `［TODO］ ...`) in QUICKSTART and upgrade-checklist guidance.

- Expanded task-marker parser regression coverage to include NFKC-normalized full-width parenthesized marker form （TASK）.
- Added CLI regression coverage for compact no-space full-width parenthesized task markers (`（TASK）rotate runbook`) to keep marker-only and compact suffix behavior aligned under NFKC normalization.
- Centralized TODO/TASK/REMINDER marker parsing into `openclaw_mem.task_markers` and wired both triage and heuristic scoring to the shared contract, reducing parser drift across CLI surfaces.
- Heuristic task detection now evaluates both raw summaries and `tool: summary` payloads, so plain `TODO: ...` summaries no longer lose task classification due to colon splitting.
- Added self-optimizing memory v0.1 observer/reporter command: `openclaw-mem optimize review` (recommendation-first, zero-write).
  - bounded source scan over `observations` (default limit: 1000)
  - computes low-risk signals: staleness, duplication, bloat, weakly-connected candidates, and repeated no-result `memory_recall` miss patterns
  - emits structured report `openclaw-mem.optimize.review.v0` + recommendation list (no mutation path)
- `optimize review --scope` now uses the same scope-token normalization for filtering as duplicate clustering (for example `Alpha Team` and `alpha-team` are treated consistently).
- `optimize review` now adds a repeated no-result `memory_recall` miss signal (`signals.repeated_misses`) plus a recommendation-first `widen_scope_candidate` proposal, with optional threshold tuning via `--miss-min-count`.
- Graphic Memory `graph index` / `graph preflight` / `graph export` now enforce `--scope` as a normalized `detail.scope` filter (including CJK fallback + neighborhood expansion), instead of treating it as an advisory hint.
- Added an initial deterministic query-plane foundation module (`openclaw_mem.graph`) with rebuildable SQLite schema + refresh contract (`topology -> graph_nodes/graph_edges`) and refresh metadata receipts (`schema_version`, digest, counts, source path).
- Added `openclaw-mem graph query ...` CLI subcommands for deterministic topology reads (`upstream`, `downstream`, `lineage`, `writers`, `filter`) with structured receipt payload `openclaw-mem.graph.query.v0`.
- Added `openclaw-mem graph query drift --live-json <path> --db <path>` to compare stable topology nodes against runtime-state snapshots (missing/runtime-only/non-ok buckets) without mutating topology truth.
- Added `openclaw-mem graph query provenance` for deterministic provenance-cardinality reads (with optional node/edge-type filters) so operators can inspect lineage source concentration without mutating graph truth.
- `graph query provenance` now also returns per-provenance `edge_types` breakdowns (`edge_type` + count) to expose lineage concentration without requiring extra follow-up queries.
- `graph query provenance` now trims blank/whitespace provenance keys before grouping and supports `--min-edge-count` for bounded high-signal concentration views.
- Plain-text `graph query provenance` output now includes per-provenance `edge_types=<type:count,...>` summaries so non-JSON operator checks retain concentration detail.
- `graph query receipts` now supports optional exact filters (`--source-path`, `--topology-digest`) and returns `total_count` alongside paged `count`, so operators can inspect receipt history slices without losing overall cardinality.
- Expanded episodic auto-mode flow to full conversation coverage:
  - `extensions/openclaw-mem` emits bounded episodic spool JSONL for `tool.call`, `tool.result`, and `ops.alert` under feature flag `config.episodes.enabled`.
  - added extractor lane `openclaw-mem episodes extract-sessions` to tail OpenClaw session JSONL and emit `conversation.user` / `conversation.assistant` with offset-state tracking.
  - extractor filter defaults to all `chat_type=direct` chats (Telegram direct + WebUI direct), excludes groups by default, and supports optional `--chat-id` allowlist narrowing.
  - `openclaw-mem episodes ingest --file <jsonl> --state <state.json> [--truncate|--rotate]` keeps deterministic offset-state ingest into `episodic_events`.
- Hardened episodic safety/retention defaults:
  - summary-first defaults for query and replay (`--include-payload` opt-in)
  - secret redaction always-on + PII-lite redaction (email/phone) at capture and ingest second-pass
  - late detection at ingest now nulls payload **and refs** and sets `redacted=1`
  - conversation payload default cap 4096 bytes (configurable) with ingest hard ceiling 8192 bytes
  - retention defaults updated (`conversation.user` 60d, `conversation.assistant` 90d)
- `openclaw-mem-engine` now supports configurable embedding clamp knobs (`embedding.maxChars`, `embedding.headChars`, `embedding.maxBytes`) and enforces them in both recall/store paths.
- Memory recall/store now fail-open when embeddings are unavailable, provider errors, or input is over long:
  - `memory_recall` still returns lexical (FTS) results when vector path is skipped.
  - `memory_store` still stores the memory with a zero vector fallback so ingest never blocks on embedding failure.
- `memory_recall` and `memory_store` now emit explicit warnings when recall/store quality is degraded due to embedding skip.
- Expanded memory-engine tunables for recall/capture/receipts behavior and harden-config parsing in plugin schema/normalization (`autoRecall`, `autoCapture`, `receipts`).
- Added Rollout Step 3 TODO guardrails to `openclaw-mem-engine` autoCapture/autoRecall:
  - new `autoCapture` knobs: `maxTodoPerTurn`, `todoDedupeWindowHours`, `todoStaleTtlDays` (with `captureTodo` still defaulting to `false`)
  - same-scope, time-bounded TODO dedupe window
  - deterministic recall-time stale TODO TTL filtering
  - bounded `openclaw-mem-engine:todoGuardrail` drop markers and receipt counters for TODO rate-limit/dedupe drops.
- Hardened TODO guardrail helper fallback behavior (`todoGuardrails.js`): invalid/non-finite dedupe window or stale TTL inputs now deterministically clamp to a safe 1-unit window instead of producing `NaN` cutoffs that silently disable filtering.
- Added installable **Docs Memory cold lane** to `openclaw-mem-engine`:
  - new config surface `docsColdLane` (`enabled`, `sourceRoots`, `sourceGlobs`, `scopeMappingStrategy`, `maxChunkChars`, bounded recall knobs)
  - new tools: `memory_docs_ingest`, `memory_docs_search`
  - `memory_recall` + `autoRecall` now optionally consult docs cold lane only when hot lane is insufficient (`minHotItems`)
  - bounded receipt/log markers: `openclaw-mem-engine:docsColdLane.ingest`, `openclaw-mem-engine:docsColdLane.search`, plus optional `coldLane` block in recall lifecycle receipts.
  - scoped docs search now uses bounded candidate over-fetch before scope filtering, and search receipts/logs expose `rawCandidates` + `scopedCandidates` counters to distinguish index misses from scope starvation.
  - documented the scoped-search starvation root cause / live verifier note and added the next-slice scope-pushdown plan for the docs cold lane.

### Docs
- Added QUICKSTART task-marker examples for solid-circle and hollow-circle markdown bullet wrappers (● TODO ..., ○[x] TODO ...) to mirror parser acceptance and existing upgrade-checklist coverage.


- Added QUICKSTART provenance concentration examples for `graph query provenance --group-by-source`, `--source-path`, and `--source-path-prefix` to make path-level, per-source, and source-family checks explicit in the optional topology smoke lane.
- Added README quick-proof timeline example (`timeline 2 --window 2`) so the local proof demonstrates the full search → timeline → get recall loop.
- Updated `docs/specs/graphic-memory-query-plane-v0.md` Stage-2 CLI examples to reflect shipped `graph query drift --live-json <path> --db <path>` command shape.
- Updated `docs/roadmap.md` section 1.7a to PARTIAL status with shipped query-plane slice (`graph query ...`, `graph query drift --live-json <path> --db <path>`) while keeping deeper provenance integration as roadmap work.

- Reframed `README.md` as a slimmer product/entry page focused on value, audience, adoption paths, and a quick local proof.
- Added `docs/about.md` and `docs/install-modes.md` so the docs site has a product-facing story plus one install/setup decision page.
- Reworked `docs/index.md`, `docs/quickstart.md`, and `mkdocs.yml` navigation into a coherent entry flow: about -> install path -> quickstart -> reality check -> reference.
- Documented self-optimizing memory v0.1 observer command (`optimize review`) in `README.md`, `QUICKSTART.md`, `docs/reality-check.md`, `docs/roadmap.md`, and `docs/specs/self-optimizing-memory-loop-v0.md`.
- Expanded triage marker docs to include ASCII/full-width angle wrappers (`<TODO> ...`, `＜TODO＞ ...`) in `README.md`, `QUICKSTART.md`, and `docs/upgrade-checklist.md`.
- Expanded `README.md` triage marker docs to match current parser separators/wrapper coverage (`;` / `；` / `.` / `。` separators plus extended bracket wrapper examples already documented in QUICKSTART/upgrade checklist).
- Added a direct README pointer to task-marker acceptance details in `docs/upgrade-checklist.md`, so operators can verify accepted TODO/TASK/REMINDER forms without hunting through docs.
- Aligned triage marker docs with parser support by documenting `[☒]` checklist marker in `README.md`, `QUICKSTART.md`, and `docs/upgrade-checklist.md`.
- Removed duplicate legacy `uv run python -m openclaw_mem triage --mode tasks ...` example blocks; docs now keep only the frozen `uv run --python 3.13 --frozen -- python -m openclaw_mem ...` form.
- Standardized README and `docs/upgrade-checklist.md` command examples to deterministic 'uv run --python 3.13 --frozen -- python -m openclaw_mem ...' form.
- Corrected `QUICKSTART.md` Graphic Memory examples to use the supported global `--json` placement and current `graph query subgraph` flags (`--hops`, `--max-nodes`, `--max-edges`).
- Added `docs/specs/episodic-auto-capture-v0.md` (capture scope, safety posture, config defaults, cron wiring, rollback).
- Updated `README.md`, `docs/auto-capture.md`, and `docs/deployment.md` with a manual-vs-auto episodic guide and verification steps.

### Testing

- Added graph query regression coverage for `query_graph_health` plus CLI coverage for `graph match` candidate grouping / explanation-path receipts.
- Hardened mem-engine TODO guardrail schema contract tests to derive defaults and max bounds directly from `index.ts` runtime constants/object defaults (`DEFAULT_AUTO_CAPTURE_CONFIG`, `AUTO_CAPTURE_MAX_*`), reducing plugin-schema drift risk at the integration boundary.
- Added heuristic regression coverage for shared task-marker contract parity (`TODO: ...`, compact wrapper chains like `●[x]TODO ...`, and tool-prefixed marker summaries).
- Added heuristic fixture coverage for French guillemet task marker form (angle quote wrapper TODO marker) in tests/data/HEURISTIC_TESTCASES.jsonl (tc33) to keep task-marker parity with parser and docs wrapper support.
- Added `tests/test_optimize_review.py` coverage for parser wiring, structured report shape, signal generation, repeated miss detection (`memory_recall` no-result patterns), and read-only behavior of `optimize review`.
- Added guardrail regression coverage for invalid/non-finite TODO dedupe and stale-TTL inputs in `extensions/openclaw-mem-engine/todoGuardrails.test.mjs`.
- Added task-marker regression coverage for ASCII angle wrappers (`<TODO>...`) in parser and triage flows, plus heuristic fixture parity (`tc31`).
- Added triage tasks regression coverage for emoji checkbox wrappers (`[✅] TODO ...`) to keep task-marker parity with parser-level acceptance rules.
- Added episodic ingest regression tests (`tests/test_episodes_ingest.py`) for offset state handling, invalid JSON lines, bounded payload behavior, and deterministic query ordering after ingest.
- Added conversation extractor regression tests (`tests/test_episodes_extract_sessions.py`) for scope-tag parsing, PII redaction, payload truncation, and redacted/null payload policy.
- Added plugin contract checks (`tests/test_plugin_episodic_spool.py`) for episodic spool schema + event-type emission markers.
- `test_triage_json_contract_v0` now writes a temporary cron jobs fixture and passes `--cron-jobs-path`, preventing host-state coupling to `~/.openclaw/cron/jobs.json`.
- Added docs-cold-lane contract tests (`test_mem_engine_docs_cold_lane.py`) for config schema defaults, trust/provenance markers, and runtime marker wiring.
- Added `tests/test_graph_refresh.py` coverage for deterministic topology refresh, schema/meta initialization, JSON topology loading, and unknown-node edge rejection.
- Added regression coverage for `graph query provenance` in both query-layer and CLI JSON contract tests (`tests/test_graph_query.py`, `tests/test_graph_query_cli.py`).
- Added provenance source-family filter regression coverage for the new `--source-path-prefix` query/CLI contract.
- Added provenance guardrail tests for whitespace provenance exclusion and `min_edge_count` filtering in query-layer and CLI paths.
- Added CLI plain-text coverage for provenance output `edge_types` summaries (`tests/test_graph_query_cli.py`).

### Benchmarks
- Added a fixed docs-memory query set for repeatable benchmark runs (`benchmarks/docs_memory_query_set.v1.jsonl`).

## [1.0.3] - 2026-02-28

### Changed
- `openclaw-mem-engine` autoRecall trivial-prompt gating is now more robust to *decorations*:
  - acknowledgements / greetings with trailing emoji or punctuation now skip recall (e.g. `好的👌`, `ok👍`, `hi～`, `收到!!`).
  - punctuation-only prompts now skip recall (e.g. `？`, `...`).

### Docs
- Clarified autoRecall trivial-prompt policy + examples in `docs/mem-engine.md`.
- Updated roadmap status to reflect shipped mem-engine M1 and partial sunrise/writeback progress.

### Testing
- Added contract-style regression coverage for the trivial-prompt skip behavior.

## [1.0.2] - 2026-02-28

### Changed
- Added `graph auto-status` command to report effective Graphic Memory automation env toggles (`OPENCLAW_MEM_GRAPH_AUTO_RECALL`, `OPENCLAW_MEM_GRAPH_AUTO_CAPTURE`, `OPENCLAW_MEM_GRAPH_AUTO_CAPTURE_MD`) with validity-aware parsing.
- Added `profile` CLI command for deterministic ops snapshots (`counts`, `importance` label distribution, top tools/kinds, recent rows, embeddings model stats).
- `pack` now supports `--query-en` to add an English assist query lane alongside the main query (useful for bilingual recall).
- `pack --trace` now derives candidate `importance` and `trust` from observation `detail_json` (canonical normalization + `unknown` fallback for malformed/absent values).
- `pack --trace` now includes an `output` receipt block with:
  - `includedCount`, `excludedCount`, `l2IncludedCount`, `citationsCount`
  - `refreshedRecordRefs` (the exact `recordRef`s included in the final bundle for lifecycle/audit hooks)
- Hardened `pack --trace` contract metadata for v1 receipts:
  - added top-level `ts` and `version` (`openclaw_mem`, `schema`)
  - expanded `budgets` with `maxL2Items` and `niceCap`
  - candidate `decision.caps` + candidate citation `url` key (nullable, redaction-safe)
- `triage --mode tasks` task-marker parsing now also accepts full-width hyphen (`－`), en dash (`–`), em dash (`—`), and unicode minus (`−`) separators after `TODO`/`TASK`/`REMINDER`.
- `triage --mode tasks` task-marker detection now normalizes width via NFKC, so full-width prefixes like `ＴＯＤＯ`/`ＴＡＳＫ`/`ＲＥＭＩＮＤＥＲ` are recognized.
- `triage --mode tasks` now also accepts bracket-wrapped task markers (`[TODO] ...`, `(TASK) ...`) using the same deterministic separator rules as plain markers.
- `triage --mode tasks` now accepts markdown list/checklist-prefixed markers (for example `- TODO ...`, `* [ ] TASK: ...`, `+ TODO ...`, `• [x] [REMINDER] ...`) and ordered-list prefixes (`1. ...`, `1) ...`, `(1) ...`, `a. ...`, `a) ...`, `(a) ...`, `iv. ...`, `iv) ...`, `(iv) ...`) while keeping deterministic separator checks.
- `triage --mode tasks` now also accepts markdown blockquote-prefixed markers (`> TODO ...`, `> > [ ] TASK: ...`, compact `>> TODO ...`) and mixed wrapper chains (for example `- > (iv) [ ] TODO: ...`) using the same deterministic separator rules.
- `triage --mode tasks` list/checklist wrapper parsing now also accepts additional unicode checkbox markers `[✓]`, `[✔]`, `[☐]`, `[☑]`, and `[☒]` in addition to `[ ]` and `[x]`.
- `triage --mode tasks` now also accepts compact no-space markdown wrapper chains before task markers (for example `-TODO ...`, `>>TODO ...`, `[x]TODO ...`, `1)TODO ...`, `* (1)TODO ...`) while preserving deterministic marker boundary checks.
- `triage --mode tasks` bracket-wrapped task markers now also accept compact no-space suffix forms (for example `[TODO]buy milk`, `(TASK)review PR`, `【TODO】buy milk`) while preserving non-marker boundary checks (for example `[TODOLIST]...`).
- Roman ordered-list prefixes now require canonical Roman numerals (for example `iv`, `IX`), reducing permissive false positives such as `ic`/`iiv`.
- `profile --json` now classifies malformed `detail_json.importance` payloads as `unknown` (instead of coercing to `ignore`) and keeps `avg_score` based on parseable importance only.
- `parse_importance_score` now rejects boolean `importance.score` values inside object payloads (`{"score": true|false}`), matching top-level bool handling.
- `make_importance` now enforces canonical labels (`ignore`/`nice_to_have`/`must_remember`) by normalizing known aliases and falling back to score-derived labels for unknown overrides.
- Importance label normalization now applies NFKC width-folding before alias/canonical mapping, so full-width variants (for example `ＭＵＳＴ＿ＲＥＭＥＭＢＥＲ`, `ＮＩＣＥ－ＴＯ－ＨＡＶＥ`) parse consistently.

### Docs
- Documented `openclaw-mem-engine` (slot backend) M1 automation (conservative autoRecall + strict autoCapture), and updated docs/website to reflect the new engine + comparison notes.
- Documented Graphic Memory automation knobs + `graph auto-status` inspection flow in `README.md`, `QUICKSTART.md`, and `docs/specs/graphic-memory-auto-capture-auto-recall.md`.
- Removed a contradictory duplicate license footer from `README.md` so the dual-license statement (`MIT OR Apache-2.0`) is defined once and consistently.
- Quickstart sample-ingest step now uses a deterministic `python -c` JSONL writer instead of a heredoc, reducing shell quoting/EOF pitfalls in automation contexts.
- Documented deterministic `triage --mode tasks` marker grammar updates (plain + bracketed markers, optional markdown blockquotes + list/checklist + ordered-list prefixes, accepted separators) in `README.md`, `QUICKSTART.md`, and `docs/upgrade-checklist.md`.
- Expanded triage task-marker docs with compact no-space bracket examples (for example `[TODO]buy milk`, `【TODO】buy milk`) in `README.md`, `QUICKSTART.md`, and `docs/upgrade-checklist.md`.
- Clarified task-marker docs to explicitly include additional markdown bullets (`‣`, `∙`, `·`) alongside `-`, `*`, `+`, and `•`.
- Clarified task-marker docs to explicitly include CJK bracket-wrapped marker forms (for example `【TODO】 ...`) alongside `[TODO] ...` and `(TASK) ...` forms.

### Testing
- Added regression coverage for `graph auto-status` parser wiring and validity-aware env flag reporting.
- Added regression coverage for `pack --trace` output receipts (shape + exclusion counting).
- Added schema checks for trace metadata (`ts`/`version`/budget caps) and candidate decision/citation fields.
- Added `pack --trace` tests for candidate importance/trust extraction from `detail_json`, including invalid-label fallback to `unknown`.
- Added coverage for `profile --json` (importance distribution + embeddings counters + recent rows).
- Added triage regression coverage for full-width hyphen (`－`), en dash (`–`), em dash (`—`), and unicode minus (`−`) task-marker separators.
- Added task-marker regression coverage for full-width marker prefixes (for example `ＴＯＤＯ` / `ＴＡＳＫ`) in both parser-level and triage flows.
- Added regression coverage for bracket-wrapped task markers (`[TODO] ...`, `(TASK) ...`, `【TODO】 ...`) in parser-level and triage flows, including marker-only acceptance and rejection cases for malformed/non-marker bracket prefixes.
- Added regression coverage for markdown wrapper-prefixed task markers: blockquotes (`>` plus compact `>>` forms), list/checklist prefixes (including `+`, `‣`, `∙`, and `·` bullets, plus checked `[✓]`/`[✔]` variants), nested prefix chains, and ordered-list prefixes (including `(1)`, full-width `（１）`, alpha forms like `a)`/`(a)`/`B.`, and Roman forms like `iv)`/`(iv)`), plus invalid Roman rejection cases, in parser-level and triage flows.
- Expanded task-marker regression coverage for compact no-space wrapper chaining (`-TODO`, `>>TODO`, `[x]TODO`, `1)TODO`, `* (1)TODO`) while retaining non-marker boundary rejection cases.
- Added regression coverage for compact no-space bracket-wrapped task markers (`[TODO]text`, `【TODO】text`) in parser-level and triage flows.
- Added regression coverage for malformed importance parsing in `profile --json` and for bool-rejection in `parse_importance_score`.
- Added regression coverage for `make_importance` label canonicalization (alias normalization + invalid-label fallback).
- Added regression coverage for full-width importance labels across parsing, parseability checks, and `make_importance` normalization.

## [1.0.1] - 2026-02-13

### CI / Docs
- Added a repo release checklist and a lockfile freshness guard (`uv lock --check`) to prevent `uv sync --locked` failures.
- Minor docs cleanup (de-emphasized archived v0.5.9 adapter spec; removed redundant note in ecosystem fit).

## [1.0.0] - 2026-02-13

### Release readiness
- Marked Phase 4 baseline as reached for first-stable release grooming.
- Clarified importance grading MVP v1 rollout status: ingest/harvest JSON summaries are shipped (`total_seen`, `graded_filled`, `skipped_existing`, `skipped_disabled`, `scorer_errors`, `label_counts`).
- Added explicit benchmark-plan pointers in docs (`docs/thought-links.md`, `docs/rerank-poc-plan.md`) to guide pre-stable quality checks.

### Docs
- Added `docs/ecosystem-fit.md` to clarify ownership boundaries:
  - `memory-core` / `memory-lancedb` as canonical backend owners
  - `openclaw-mem` as sidecar capture + local recall + observability layer
- Updated `README`, `QUICKSTART`, `docs/auto-capture`, `docs/deployment` with deployment topology guidance and value framing.
- Expanded onboarding docs for freshness operations:
  - documented the ingest-lag issue pattern and split-lane fix (`5m` no-embed ingest + hourly embed/index refresh)
  - added one-screen architecture diagrams in `docs/ecosystem-fit.md` (kept ASCII as canonical)
  - clarified token-overhead tradeoff between OS scheduler vs OpenClaw cron `agentTurn` wrappers.
  - removed Mermaid block from `docs/ecosystem-fit.md` due GitHub rich-render compatibility issues.

### Added
- Importance grading support (MVP v1):
  - canonical `detail_json.importance` object helper + compatibility parser (`openclaw_mem.importance`)
  - deterministic scorer `heuristic-v1` (`openclaw_mem.heuristic_v1`)
  - new documentation: `docs/importance-grading.md`
- Feature-flagged importance autograde on import:
  - enable via `OPENCLAW_MEM_IMPORTANCE_SCORER=heuristic-v1`
  - per-run override via `--importance-scorer {heuristic-v1|off}` for `ingest` / `harvest`

### Changed
- `store` now writes canonical importance objects (method=`manual-via-cli`) instead of legacy numeric-only.
- `triage --mode tasks` now understands canonical importance objects (still accepts legacy numeric values).

### Testing
- Added regression coverage for `heuristic-v1` using a shared JSONL testcase corpus.

## [0.5.9] - 2026-02-08

### Added
- Minimal-risk adapter annotations in capture plugin:
  - backend metadata (`memory_backend`, `memory_backend_ready`, `memory_backend_mode`)
  - memory action tags (`memory_tool`, `memory_operation`) for canonical memory tools.
- New CLI command: `openclaw-mem backend --json` for memory slot/readiness/fallback posture checks.
- New spec doc: `docs/v0.5.9-adapter-spec.md`.

### Changed
- `ingest` now preserves extra JSONL top-level fields by merging them into `detail_json`.
- Plugin config schema extended with `backendMode`, `annotateMemoryTools`, `memoryToolNames`.
- Version bump to `0.5.9` (Python package + plugin manifest).

## [0.5.8] - 2026-02-08

### Changed
- `openclaw-mem` plugin is now capture-only again: removed extension-level registration of `memory_store` / `memory_recall`.
- Explicit memory write/recall remains available via CLI (`openclaw-mem store`, `openclaw-mem hybrid`).
- Updated docs (`README`, `QUICKSTART`, `docs/auto-capture`, `docs/deployment`) to remove plugin-tool guidance.
- Removed temporary tool-exposure fix-plan doc.
- Version bump to `0.5.8` (Python package + plugin manifest).

## [0.5.7] - 2026-02-08

### Fixed
- Plugin tool exposure now follows official OpenClaw extension pattern: `memory_store` and `memory_recall` are registered inside `register()` via `api.registerTool(...)`.
- Fixed extension-side registration path mismatch (capture hook could load while tool registration path diverged from first-party pattern).

### Changed
- Refactored plugin tool handlers to shared CLI launcher (`uv run --python 3.13 -- python -m openclaw_mem ...`) for clearer error handling.
- Added docs note for strict tool policy opt-in (`tools.alsoAllow` for `memory_store` / `memory_recall`).
- Version bump to `0.5.7` (Python package + plugin manifest).

## [0.5.6] - 2026-02-06

### Added
- `openclaw-mem triage --mode tasks`: deterministic scan for newly stored tasks (from `memory_store` / `openclaw-mem store --category task`).
- `openclaw-mem triage` now uses a small state file to **dedupe alerts** (new-only) and avoid repeating the same heartbeat notifications.

### Changed
- `triage --mode heartbeat` now includes: observations scan + cron-errors scan + tasks scan.
- Version bump to `0.5.6`.
