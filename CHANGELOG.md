# Changelog

All notable changes to **openclaw-mem** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Added `profile` CLI command for deterministic ops snapshots (`counts`, `importance` label distribution, top tools/kinds, recent rows, embeddings model stats).
- `pack` now supports `--query-en` to add an English assist query lane alongside the main query (useful for bilingual recall).
- `pack --trace` now derives candidate `importance` and `trust` from observation `detail_json` (canonical normalization + `unknown` fallback for malformed/absent values).
- `pack --trace` now includes an `output` receipt block with:
  - `includedCount`, `excludedCount`, `l2IncludedCount`, `citationsCount`
  - `refreshedRecordRefs` (the exact `recordRef`s included in the final bundle for lifecycle/audit hooks)
- Hardened `pack --trace` contract metadata for v0 receipts:
  - added top-level `ts` and `version` (`openclaw_mem`, `schema`)
  - expanded `budgets` with `maxL2Items` and `niceCap`
  - candidate `decision.caps` + candidate citation `url` key (nullable, redaction-safe)
- `triage --mode tasks` task-marker parsing now also accepts full-width hyphen (`－`) and en dash (`–`) separators after `TODO`/`TASK`/`REMINDER`.
- `triage --mode tasks` task-marker detection now normalizes width via NFKC, so full-width prefixes like `ＴＯＤＯ`/`ＴＡＳＫ`/`ＲＥＭＩＮＤＥＲ` are recognized.
- `profile --json` now classifies malformed `detail_json.importance` payloads as `unknown` (instead of coercing to `ignore`) and keeps `avg_score` based on parseable importance only.
- `parse_importance_score` now rejects boolean `importance.score` values inside object payloads (`{"score": true|false}`), matching top-level bool handling.

### Testing
- Added regression coverage for `pack --trace` output receipts (shape + exclusion counting).
- Added schema checks for trace metadata (`ts`/`version`/budget caps) and candidate decision/citation fields.
- Added `pack --trace` tests for candidate importance/trust extraction from `detail_json`, including invalid-label fallback to `unknown`.
- Added coverage for `profile --json` (importance distribution + embeddings counters + recent rows).
- Added triage regression coverage for full-width hyphen (`－`) and en dash (`–`) task-marker separators.
- Added task-marker regression coverage for full-width marker prefixes (for example `ＴＯＤＯ` / `ＴＡＳＫ`) in both parser-level and triage flows.
- Added regression coverage for malformed importance parsing in `profile --json` and for bool-rejection in `parse_importance_score`.

## [1.0.1] - 2026-02-13

### CI / Docs
- Added a repo release checklist and a lockfile freshness guard (`uv lock --check`) to prevent `uv sync --locked` failures.
- Minor docs cleanup (de-emphasized archived v0.5.9 adapter spec; removed redundant note in ecosystem fit).

## [1.0.0] - 2026-02-13

### Release readiness
- Marked Phase 4 baseline as reached for first-stable release grooming (docs alignment pass).
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

## [0.5.5] - 2026-02-06

### Added
- `openclaw-mem triage --mode cron-errors`: deterministic scan of OpenClaw cron job store (`~/.openclaw/cron/jobs.json`) for jobs whose `lastStatus != ok`.
- `openclaw-mem triage --mode heartbeat` now includes both: observations scan + cron error scan.

### Changed
- Version bump to `0.5.5`.

## [0.5.4] - 2026-02-06

### Added
- `openclaw-mem triage`: deterministic local scan over recent observations (for cron/heartbeat), with non-zero exit code when attention is needed.

### Changed
- Version bump to `0.5.4`.
- License: MIT → Apache-2.0.

## [0.5.2] - 2026-02-06

### Changed
- Packaging/version alignment: bump Python package to `0.5.2` (fixes mismatch vs git tags).
- Plugin manifest version aligned to `0.5.2`.

### Docs
- Deployment guidance: recommended `excludeTools` defaults + logrotate examples.
- Privacy export rules checklist updated ("export requires --yes") now marked done.

### Testing
- Unit tests passing (see CI / local run).

## [0.5.1] - 2026-02-06

### Added
- Route A semantic recall: `openclaw-mem index` + `openclaw-mem semantic` using OpenClaw Gateway `/tools/invoke` → `memory_search` (black-box embeddings).

### Testing
- Added Route A tests (snippet→obs id extraction + ranking).

## [0.5.0] - 2026-02-06

### Added
- Gateway routing for `summarize` (`--gateway`, `OPENCLAW_MEM_USE_GATEWAY=1`).
- Auto-ingest workflow: `openclaw-mem harvest`.

## [0.4.1] - 2026-02-06

### Changed
- Packaging/version alignment: bump package version to `0.4.1`.
- Documentation updates (README/CHANGELOG) to reflect that Phase 4 functionality is already shipped.

### Testing
- 26 unit/integration tests passing.

## [0.4.0] - 2026-02-06

### Added
- Phase 4 complete release marker (hybrid RRF search + proactive memory tools).

## [0.3.0] - 2026-02-06

### Added

#### Phase 4: Hybrid Search + Proactive Memory Tools
- Reciprocal Rank Fusion (RRF) implementation for robust hybrid ranking (FTS + vector)
- `openclaw-mem hybrid` command (RRF fusion)
- `openclaw-mem store` command (store + embed + append to `memory/YYYY-MM-DD.md`)
- Plugin tools exposed to the agent: `memory_store` and `memory_recall`

## [0.2.0] - 2026-02-06

### Added
- Phase 3 vector search (`embed` + `vsearch`)
- API key auto-resolution from env or `~/.openclaw/openclaw.json` (`agents.defaults.memorySearch.remote.apiKey`)

## [0.1.0-m0] - 2026-02-05

### Added
- Initial M0 release with CLI-first observation store
- FTS5 full-text search
- Progressive disclosure (3-layer search)
- Basic plugin for auto-capture (tool_result_persist hook)

---

## Future Roadmap

### Next (Optional)
- Weighted hybrid scoring (tuned BM25 + embeddings weights)
- Optional sqlite-vec acceleration
- Vector index fingerprint + rebuild workflow

### Integration (Planned)
- Automated ingestion (cron job or systemd timer)
- OpenClaw gateway plugin hooks for session lifecycle
- Memory deduplication and versioning
- Backup and migration utilities
