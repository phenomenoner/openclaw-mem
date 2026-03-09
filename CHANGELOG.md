# Changelog

All notable changes to **openclaw-mem** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
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

### Docs
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
- Added `docs/specs/episodic-auto-capture-v0.md` (capture scope, safety posture, config defaults, cron wiring, rollback).
- Updated `README.md`, `docs/auto-capture.md`, and `docs/deployment.md` with a manual-vs-auto episodic guide and verification steps.

### Testing
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
