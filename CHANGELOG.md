# Changelog

All notable changes to **openclaw-mem** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
