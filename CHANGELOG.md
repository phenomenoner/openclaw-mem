# Changelog

All notable changes to **openclaw-mem** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

- (placeholder)

## [0.3.0] - 2026-02-06

### Added

#### Phase 1: Auto-Capture Plugin
- OpenClaw plugin for automatic tool result capture via the `tool_result_persist` hook
- Smart summary extraction (compact ~200 char extract)
- Truncation + filter controls (include/exclude specific tools)
- Optional full message capture (`captureMessage`)
- Auto-capture setup docs and hook payload examples

#### Phase 2: AI Compression (CLI)
- `openclaw-mem summarize` CLI command for daily note compression
- Direct OpenAI API integration via a mockable client abstraction
- Dry-run mode + configurable model/temperature/max tokens
- Workspace targeting via `--workspace`

#### Export
- `openclaw-mem export` to append observations into a Markdown file
- Safety guard: exporting to `MEMORY.md` requires explicit `--yes`

#### Phase 3: Vector Search
- `openclaw-mem embed` command to compute/store embeddings (float32 BLOB + norm)
- `openclaw-mem vsearch` command for cosine-similarity search over stored embeddings
- Offline/test mode for vector search via `--query-vector-json` / `--query-vector-file`

#### Phase 4: Hybrid Search + Proactive Memory Tools
- Reciprocal Rank Fusion (RRF) implementation for robust hybrid ranking (FTS + vector)
- `openclaw-mem hybrid` command (RRF fusion)
- `openclaw-mem store` command (store + embed + append to `memory/YYYY-MM-DD.md`)
- Plugin tools exposed to the agent: `memory_store` and `memory_recall`

#### OpenClaw Integration Defaults
- API key auto-resolution from **either** env **or** `~/.openclaw/openclaw.json`:
  - `agents.defaults.memorySearch.remote.apiKey`

### Changed
- Default summarize model updated to `gpt-5.2`
- Documentation updated to reflect Phase 3/4 shipping status

### Fixed
- Atomic file append (write-to-temp + rename) for corruption-safe writes
- WAL mode + short-lived connections guidance for SQLite concurrency

### Testing
- 26 unit/integration tests passing
- CI: GitHub Actions workflow (uv sync + unittest)

### Security
- Message truncation by default in auto-capture plugin
- Explicit consent model for writing to `MEMORY.md` (`--yes`)

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
