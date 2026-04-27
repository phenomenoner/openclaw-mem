# Session-store maintenance hardening receipt — 2026-04-27

## Change

Added backward-compatible hardening for newer OpenClaw session-store maintenance artifacts:

- `episodes extract-sessions` skips transcript-shaped backup/checkpoint files such as `sessions.json.bak.*.jsonl`, `*.checkpoint.*.jsonl`, and `*.bak*.jsonl`.
- Added `openclaw-mem episodes append-session-store-receipt` for low-cardinality session-store lifecycle observability.
- The receipt stores only event name, store basename, and optional numeric `size_bytes` / `backup_count`; it never stores raw session-store or backup contents.
- Updated public docs and agent-memory skill guidance.

## Why now

Recent OpenClaw versions may rotate or back up session-store state beside live runtime files. `openclaw-mem` should keep conversation capture distinct from runtime-state maintenance, while still allowing safe observability receipts when operators want lifecycle visibility.

## Backward compatibility

The hardening is additive and path-name based. Older OpenClaw installations that do not create these artifacts continue to behave as before. Non-JSONL session-store files remain outside the transcript scan and are not read.

## Verification

- QA review/test worker completed; feedback addressed.
- `uv run --python 3.13 --frozen pytest tests/test_episodes_extract_sessions.py tests/test_episodes_ingest.py -q` → 21 passed.
- `uv run --python 3.13 --frozen pytest tests/test_agent_memory_skill_assets.py tests/test_episodes_extract_sessions.py -q` → 14 passed.
- `uv run --python 3.13 --frozen pytest -q` → 545 passed, 71 subtests passed.
- `git diff --check` → clean.

## Rollback

Revert the commit. No schema migration is required.
