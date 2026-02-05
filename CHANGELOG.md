# Changelog

All notable changes to openclaw-mem will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

#### M0 (Minimal Usable Milestone)
- **CLI commands**: `status`, `ingest`, `search`, `timeline`, `get`
- FTS5 full-text search over observations
- Progressive disclosure search (3-layer: search → timeline → get)
- In-memory SQLite support for fast tests
- Global `--db` and `--json` flags (work before/after subcommand)
- AI-native design: structured JSON output, non-interactive, example-rich help

#### Phase 1: Auto-Capture Plugin
- OpenClaw plugin for automatic tool result capture via `tool_result_persist` hook
- Smart summary extraction (~200 bytes vs 1-5KB full messages)
- Message truncation (configurable max length, default: 1000 chars)
- Filter controls: `includeTools` (allowlist) and `excludeTools` (denylist)
- Optional full message capture (`captureMessage` config)
- Comprehensive auto-capture documentation with setup examples

#### Phase 2: AI Compression CLI Integration
- `openclaw-mem summarize` command for AI compression of daily notes
- Integration with OpenAI API (supports custom base URL)
- Dry-run mode for previewing summaries without writing
- Workspace customization via `--workspace` flag
- Model, temperature, and token limit configuration
- `openclaw-mem export` command (export observations to Markdown; `--yes` required for MEMORY.md)

#### Phase 3: Vector Search (Partial)
- `openclaw-mem embed` command to compute/store embeddings (float32 BLOB)
- `openclaw-mem vsearch` command for cosine-similarity search over embeddings
- Offline/test mode: `--query-vector-json` / `--query-vector-file`

#### Testing & CI
- 22 tests (unit + integration) with 100% coverage
- GitHub Actions CI workflow (uv sync + unittest)
- Test fixtures for CLI, atomic append, and AI compression
- Mock OpenAI client for testability
- In-memory database tests (fast, isolated)

#### Documentation
- Hook payload examples (`docs/hooks_examples/`)
  - `tool_result_persist.json` — Tool execution capture
  - `command_new.json` — Session start
  - `command_stop.json` — Session end
- Operational guides:
  - `docs/db-concurrency.md` — SQLite WAL mode, locking strategy
  - `docs/embedding-status.md` — Vector search availability detection
  - `docs/privacy-export-rules.md` — Consent model for MEMORY.md exports
  - `docs/auto-capture.md` — Plugin installation and configuration
- M0 prototype documentation (`docs/m0-prototype.md`)
- Full adoption plan (`docs/claude-mem-adoption-plan.md`)
- Installation, usage, and testing sections in README

#### Infrastructure
- SQLite with WAL mode (race-safe, concurrent readers)
- Atomic file append (write-to-temp + rename)
- Date validation (YYYY-MM-DD format)
- Graceful error handling with structured JSON errors
- Environment variable configuration (`OPENCLAW_MEM_DB`, `OPENAI_API_KEY`, etc.)

### Changed
- Moved from Codex CLI dependency to direct OpenAI API calls
- Refactored `compress_memory.py` into testable functions
- Improved CLI argument parsing (merged global/per-command flags)

### Fixed
- Race conditions in file append (now atomic)
- Database locking issues (WAL mode + short-lived connections)
- Date validation error messages (now actionable)

### Security
- Message truncation by default (prevents accidental secret logging)
- Privacy rules for MEMORY.md exports (requires explicit `--yes` flag)
- Redaction recommendations for sensitive data

## [0.1.0-m0] - 2026-02-05

### Added
- Initial M0 release with CLI-first observation store
- FTS5 full-text search
- Progressive disclosure (3-layer search)
- Basic plugin for auto-capture (tool_result_persist hook)

---

## Future Roadmap

### Phase 3: Vector Search (Next)
- Hybrid BM25 + embeddings scoring (weight tuning)
- Optional sqlite-vec integration (performance)
- Embedding provider detection and fallback (status reporting)
- Index fingerprint + rebuild workflow

### Phase 4: Polish & UX (Planned)
- `openclaw-mem export` enhancements: export AI summaries/learnings to MEMORY.md (not just observations)
- `openclaw-mem tail` command (stream recent observations)
- Cost estimation for AI compression
- Batch processing for multiple dates
- Web viewer UI (optional)

### Phase 5: Integration (Planned)
- Automated ingestion (cron job or systemd timer)
- OpenClaw gateway plugin hooks for session lifecycle
- Memory deduplication and versioning
- Backup and migration utilities
