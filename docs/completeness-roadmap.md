# Completeness roadmap (vs memory-lancedb-pro)

Goal: keep `openclaw-mem` **comparable in completeness** to `win4r/memory-lancedb-pro` at the level of *operator-facing* capabilities (not necessarily identical UI).

Reference project: <https://github.com/win4r/memory-lancedb-pro>

## Current baseline (shipped)
- ✅ Hybrid recall (FTS + vector) in `openclaw-mem-engine`
- ✅ Scope-aware filtering + policy tiers (must → nice → optional unknown)
- ✅ M1 automation:
  - ✅ Proactive Pack / autoRecall (conservative, skip trivial prompts, capped, escaped)
  - ✅ autoCapture (strict allowlist, secret-skip, dedupe, capped)
- ✅ Deterministic, rollbackable ops posture (slot switch + per-feature disable)

## Gap backlog (fill-in plan)

### P0 — Operator parity (must be comparable)
1) ✅ **Admin surfaces (comparable)**
   - Shipped in `openclaw-mem-engine`:
     - list memories (scope/category/limit filters)
     - stats (counts by scope/category + size/age summaries)
     - export (sanitized deterministic JSONL/JSON)
     - import (append + dedupe + dry-run)
   - Surfaces:
     - tool API: `memory_list`, `memory_stats`, `memory_export`, `memory_import`
     - CLI: `openclaw memory <list|stats|export|import>` when plugin CLI is loaded
     - fallback namespace: `openclaw ltm <list|stats|export|import>`
   - Acceptance met: operator can audit counts by scope/category and export a sanitized snapshot with receipts.

2) ✅ **Receipts/debug transparency for recall lifecycle (P0-2)**
   - Shipped bounded lifecycle receipt (`openclaw-mem-engine.recall.receipt.v1`) for:
     - manual `memory_recall` tool results (`details.receipt.lifecycle`)
     - `autoRecall` hook logs + optional injection wrapper comment (`receipts.verbosity=high`)
   - Includes: skip status/reason, tiers searched, tier counts (candidates/selected), `ftsTop` / `vecTop` / `fusedTop` (IDs + scores only), final injected count
   - Explicit rejection reasons now emitted: `trivial_prompt`, `no_query`, `no_results_must`, `no_results_nice`, `provider_unavailable`, `budget_cap`
   - Config knobs: `receipts.enabled`, `receipts.verbosity`, `receipts.maxItems` (default: enabled + low + 3)
   - Acceptance met: recall path is auditable without exposing memory text in receipts by default.

3) ✅ **Namespace & scope hygiene**
   - Shipped hardening:
     - line-anchored scope tag parsing (`[ISO]` / `[SCOPE]`) that ignores code fences + injected `<relevant-memories>` blocks
     - `scopePolicy.skipFallbackOnInvalidScope=true` (default) to suppress fallback on invalid strict scopes
     - explicit `scopeFallbackSuppressed` marker for operator debugging
   - Acceptance met: same user runs 2 projects; recall doesn’t cross unless explicitly allowed

4) ✅ **Step4 rollout wiring: deterministic Working Set + operator receipts**
   - Added config-gated Working Set (`workingSet.enabled`, default off for canary)
   - Deterministic synthesis from recent per-scope preference/decision/todo rows + prompt questions
   - Pinned injection before normal recall slots; optional upsert persistence (`working_set:<scope>`)
   - Recall receipts now include `workingSet` summary + `whySummary` / `whyTheseIds`

### P1 — Quality parity (makes it feel “pro”)
4) **Fusion/ranking improvements (still deterministic)**
   - Calibrate hybrid fusion weights; add optional recency boost
   - Acceptance: recall quality improves on benchmark + no large regressions

5) **Retention/TTL policy (opt-in)**
   - Optional TTL/decay for low-importance captures
   - Acceptance: DB growth bounded without losing must_remember

6) **Safety hardening**
   - Stronger secret detector + PII heuristics; capture redaction rules
   - Shipped (2026-04-27): deterministic high-risk token coverage widened for `sk-proj`, `github_pat`, AWS secret-access-key assignments, and long Bearer auth values across mem-engine autoCapture + episodic helper guards.
   - Shipped (2026-04-27, follow-up): shared synthetic golden corpus `tests/data/SECRET_DETECTOR_GOLDEN.v1.json` now drives mem-engine source-contract checks, episodic guard tests, and sidecar/plugin redaction coverage from one source of truth.
  - Shipped (2026-04-27, follow-up): sidecar/plugin tool-result summary runtime behavior is now covered by a bounded black-box Node test (`extensions/openclaw-mem/toolResultSummary.test.mjs`) wired through `tests/test_plugin_episodic_summary_runtime.py`.
  - Shipped (2026-04-27, follow-up): `tool_result_persist` now has an end-to-end fake-API plugin harness runtime check (`extensions/openclaw-mem/toolResultPersistE2E.test.mjs`) asserting emitted episodic `tool.result` JSONL lines stay redacted/non-leaking while preserving benign text.
   - Verification surface:
     - `tests/test_episodes_extract_sessions.py`
     - `tests/test_episodic_secret_detection.py`
     - `tests/test_mem_engine_auto_capture_tool_output.py`
     - `tests/test_plugin_episodic_spool.py`
     - `extensions/openclaw-mem-engine/secretDetectorGolden.test.mjs`
    - `extensions/openclaw-mem/toolResultSummary.test.mjs`
    - `extensions/openclaw-mem/toolResultPersistE2E.test.mjs`
    - `tests/test_plugin_episodic_summary_runtime.py`
   - Suggested focused verification commands:
     - `python3 -m pytest tests/test_episodes_extract_sessions.py tests/test_episodic_secret_detection.py tests/test_mem_engine_auto_capture_tool_output.py tests/test_plugin_episodic_spool.py tests/test_plugin_episodic_summary_runtime.py -q`
     - `node --test extensions/openclaw-mem-engine/secretDetectorGolden.test.mjs`
    - `node --test extensions/openclaw-mem/toolResultSummary.test.mjs`
    - `node --experimental-strip-types --test extensions/openclaw-mem/toolResultPersistE2E.test.mjs`
   - Acceptance: no obvious secrets captured in test corpus

### P2 — UX/Website completeness (nice, but helps adoption)
7) **Docs polish (README/About/website)**
   - One killer demo flow, before/after, architecture diagram

8) **Operator runbooks**
   - Upgrade, rollback, incident playbook, troubleshooting

## Execution protocol
- We fill this backlog via **single-agent hacking mode** runs (one worker), each run:
  - updates docs (what changed + how to verify)
  - ships code + tests
  - logs Decision/Tech Note if it changes ops posture

## Next slice (recommended)
P1-5 (fusion/ranking improvements) is the active next slice, then lifecycle MVP archive-first.

Current first cut:
- Add a deterministic golden fixture for quota-based recall selection.
- Keep base rank-fusion behavior unchanged; use the record timestamp only as a deterministic tie-break inside fallback overflow selection.
- Add opt-in lifecycle writeback for records selected into the final pack: refresh `detail_json.lifecycle.last_used_at` / `used_count`, preserve `archived_at`, and never hard-delete.
- Verify with focused engine and lifecycle tests before broader rollout or default changes.
