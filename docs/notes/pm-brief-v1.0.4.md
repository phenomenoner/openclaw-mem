# PM Brief — openclaw-mem v1.0.4 prep

## What changed
- Bumped release version to **1.0.4** and aligned version declarations:
  - `pyproject.toml`
  - `openclaw_mem/__init__.py`
  - `extensions/openclaw-mem/openclaw.plugin.json`
- Fixed flaky contract test dependency on host cron state:
  - `tests/test_json_contracts.py::test_triage_json_contract_v0`
  - writes a temp `jobs.json` fixture (`{"jobs": []}`) in the test tempdir
  - passes `--cron-jobs-path <fixture>` to CLI
- Updated `CHANGELOG.md` [Unreleased] with v1.0.4 items:
  - embedding clamp controls in `openclaw-mem-engine` (`maxChars` / `headChars` / `maxBytes`)
  - recall/store fail-open behavior when embedding is skipped (provider missing/unavailable or input too long)
  - warning emission on degraded recall/store quality
  - expanded/clarified config knobs for autoRecall/autoCapture/receipts handling
  - test hermeticity fix above

## Why
- Prevent release drift and unstable test behavior across dev boxes by removing implicit reads from `~/.openclaw/cron/jobs.json`.
- Preserve recall availability even under embedding failures by keeping lexical fallback path active.
- Give operators explicit control and guardrails over embedding input trimming so recall can be tuned without code changes.
- Make degradation visible with warnings instead of silent quality loss.

## Risks / rollback
- **Risk:** clamp defaults may remove too much context for some prompts and lower recall quality.
  - **Rollback:** revert the version bump commit, or set `embedding.maxChars`/`embedding.headChars`/`embedding.maxBytes` to safer values in plugin config.
- **Risk:** fail-open behavior changes the shape of diagnostics (`missing/ fallback` reasons) and may surface more warnings.
  - **Rollback:** narrow warnings/notifications or temporarily route downstream filtering to ignore warning-only messages.

## What NOT to duplicate
- Do **not** keep tests coupled to host filesystem state (`~/.openclaw/cron/jobs.json`, etc.)—always inject fixtures.
- Do **not** touch `extensions/openclaw-mem-engine` plugin version (`openclaw.plugin.json`) unless explicitly planning an engine-specific semver change.
- Do **not** duplicate embedding clamp/warning logic in multiple places; keep it centralized in the existing clamp utility + plugin config plumbing.
