# Self-model sidecar soak alert fix — 2026-05-20

## Problem

Telegram DM repeatedly received:

`ALERT [self_model_sidecar_soak_5m] exit=1 ... self_model_sidecar_soak_controller.py line 102`

## Root cause

`latest_receipt(run_dir, prefix="warning")` tried to parse the newest warning receipt. The newest warning file was empty/truncated:

`/root/.openclaw/memory/openclaw-mem/self-model-sidecar/soak/warning-20260519T160001.059105_0000.json` size `0`.

The helper did not skip corrupt JSON, so `json.JSONDecodeError` escaped the controller and made cron return exit 1 every run.

## Fix

`openclaw_mem/continuity_soak.py::latest_receipt` now scans warning receipts from newest to oldest and returns the newest valid JSON receipt, skipping unreadable/corrupt receipts.

Regression test added: `test_latest_receipt_skips_corrupt_tail`.

## Verification

- `uv run pytest -q tests/test_self_model_sidecar.py` → 17 passed
- `uv run python -m compileall -q openclaw_mem/continuity_soak.py tools/self_model_sidecar_soak_controller.py` → passed
- Direct controller smoke → rc=0, stdout `NO_REPLY`, stderr empty
- Cron wrapper smoke → rc=0, stdout/stderr empty
- Next scheduled supercronic run at `2026-05-19T23:50:08Z` succeeded
- No new `self_model_sidecar_soak_5m` alert after the fix; alert tail stops at `2026-05-20 07:46:47 CST`

## Current soak status

The soak status itself is still `warn` for an old receipt gap (`largest_gap_seconds=295500`, coverage ratio `0.641`), but this is now handled silently because the prior valid warning reason is the same. The cron noise was the corrupt receipt parse failure, not a new runtime crash.
