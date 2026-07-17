# OpenClaw-mem Pack CCR Handoff

Status: implementation complete locally, staged-only. Live cutover is intentionally deferred.

## Scope

- Implement the reviewed Pack CCR design from Phase 0 through Phase 4 in the `openclaw-mem` repo.
- Keep live prompt packing disabled unless an operator explicitly enables it.
- Do not restart or cut over the live `.agent-harness` gateway in this workflow.

## Progress

- Branch: `codex/openclaw-mem-pack-ccr`
- Workspace: `<openclaw-mem-worktree>`
- Harness spike archived for later reference:
  - `<operator-archive>/openclaw-mem-pack-harness-spike.patch`
  - `<operator-archive>/openclaw-mem-pack-harness-spike-files/`
- Phase 0-2 core artifact module: implemented in `openclaw_mem/pack_artifacts.py` with tests in `tests/test_pack_artifacts.py`.
  - RED: `uv run -- python -m unittest tests.test_pack_artifacts -q` failed with `ModuleNotFoundError: No module named 'openclaw_mem.pack_artifacts'`.
  - GREEN: `uv run -- python -m unittest tests.test_pack_artifacts -q` passed, 14 tests after spec-review and code-review fixes for disabled pass-through, complete marker escaping, duplicate byte accounting, canary observe status, no store-before-safe-pack, non-shrinking rejection, and malformed observe receipt numbers.
- Phase 3 CLI integration: implemented as explicit opt-in `pack --pack-artifacts on`; default `pack` output remains unchanged and packed text is exposed as `bundle_text_packed`.
  - RED: focused CLI test failed on unrecognized `--pack-artifacts` flags.
  - GREEN: `uv run -- python -m unittest tests.test_cli.TestCliM0.test_pack_falls_back_to_fts_when_no_api_key tests.test_cli.TestCliM0.test_pack_artifacts_opt_in_exposes_packed_prompt_text_and_exact_retrieval tests.test_cli.TestParserContracts -q` passed, 4 tests.
- Phase 4 observe/control: implemented through `collect_observe_report(...)`, strategy disable config, canary receipt accounting, and read-only `pack-artifacts-observe`.
  - RED: observe CLI test failed because `pack-artifacts-observe` was not a parser choice.
  - GREEN: `uv run -- python -m unittest tests.test_cli.TestCliM0.test_pack_artifacts_observe_cli_reports_disabled_and_retrieval_counts -q` passed.
- Review follow-up fixes:
  - `pack-artifacts-observe` now uses the no-DB dispatcher path, so receipt observation is read-only and does not create the default memory DB.
  - `pack_candidate(...)` previews strategy output before storing raw bytes, rejects unsafe/non-shrinking output, and only stores accepted artifacts.
  - Strategy summaries cap copied field/line/snippet text to avoid preserving large raw chunks.
  - Pack artifact numeric CLI flags reject zero/negative values.
  - `artifact_sidecar` gained a Windows-safe fallback for POSIX-only `os.fchmod`, required by full-suite validation on this host.
  - Repo-generated agent memory skill docs were refreshed with `scripts/generate_agent_memory_skill_assets.py`.
- Validation:
  - `uv run -- python -m unittest tests.test_pack_artifacts -q` passed, 14 tests.
  - `uv run -- python -m unittest tests.test_cli -q` passed, 146 tests.
  - `uv run -- python -m unittest tests.test_artifact_sidecar tests.test_artifact_cli tests.test_pack_artifacts tests.test_cli -q` passed, 166 tests.
  - `$env:PYTHONUTF8='1'; $env:UV_LINK_MODE='copy'; uv run --python 3.13 -- python -m unittest discover -s tests -p "test_*.py" -q` passed, 656 tests, 2 skipped.
  - `git diff --check` passed.

## Decisions

- TTL default: session-scoped by default; 24 hours only for explicitly pinned/operator-approved debug artifacts.
- Store: separate SQLite Pack artifact store, not the main observations DB.
- Retrieval surface: OpenClaw-mem Python API first, CLI integration next.
- Token counts: deterministic character-based estimate for v1 receipts unless a tokenizer is already available.
- Lossy transforms: disabled for v1.

## Deferred Live Cutover Recommendation

- Enable Pack only through an explicit operator flag/config after staged validation.
- Start with JSON/tool-output candidates only.
- Keep `bounded-lossy`, query-filtered retrieval, diff/doc outline strategies, broad live-zone detection, and automatic canvas injection disabled.
- Do not promote memory ownership or restart the live gateway as part of Pack enablement unless separately approved.
- Keep the artifact store under a separate `memory/pack-artifacts` path and include it in backup planning before enabling live prompt use.

## Post-Cutover Test Items

- `healthz --harness-home .\.agent-harness --require-writable-state`
- `enable-check --harness-home .\.agent-harness`
- `memory-service-status --harness-home .\.agent-harness`
- `memory-read-path-smoke --harness-home .\.agent-harness`
- OpenClaw-mem Pack observe/report shows nonzero pack receipt counters after a controlled opt-in test turn.
- Retrieve a known full-hash marker and compare exact raw bytes.
- Disable a strategy and confirm Pack falls back to pass-through.
- Confirm stable prompt prefix/system sections remain byte-equivalent before and after opt-in packing.
