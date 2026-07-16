# OpenClaw-mem Run A Development Handoff

Date: 2026-07-17 (Asia/Taipei)

Status: active development, paused at a clean commit boundary during T09

## 1. Executive summary

This branch implements the 27-task Run A upgrade plan for `openclaw-mem`. The work
starts from upstream `main` at `5bb0b66` (v1.9.32) and preserves the existing CLI,
database, receipt, and fail-open contracts while extracting a stable core library,
adding governed database migrations, improving retrieval performance and bilingual
recall, restructuring operational skills, and closing with full verification.

Current state:

- T00-T08 are complete.
- T09 is in progress and has three completed, independently verified slices.
- The latest implementation checkpoint is `e500975` on branch `feat/v2-run-a`;
  this handoff is committed immediately after it as a documentation-only commit.
- The working tree was clean when this handoff was written.
- No commits have been pushed. No PR, release, PyPI publish, mkdocs deploy, live
  runtime mutation, gateway restart, user configuration change, or cron change has
  been performed.
- The next implementation slice is the remaining episodic Store lane, beginning
  with append/session-store receipt and then search/embed.

## 2. Canonical locations

### Active local repository

```text
D:\Warehouse\Rust-OpenClaw-Core\.agent-harness\workspace\repos\openclaw-mem
```

This is the existing workspace repository selected by CK. Do not download or create
another clone.

### Branch and base

```text
branch: feat/v2-run-a
base:   5bb0b66 (main, v1.9.32 development baseline)
implementation checkpoint: e500975 refactor: move episodic query and replay into core
branch HEAD:               documentation-only handoff commit directly above e500975
```

### Planning sources

```text
D:\Warehouse\Topics\openclaw-mem-upgrade\MASTER-PLAN.md
D:\Warehouse\Topics\openclaw-mem-upgrade\RUNBOOK.md
D:\Warehouse\Topics\openclaw-mem-upgrade\docs\01-current-state.md
D:\Warehouse\Topics\openclaw-mem-upgrade\docs\02-reference-lessons.md
D:\Warehouse\Topics\openclaw-mem-upgrade\docs\03-target-architecture.md
D:\Warehouse\Topics\openclaw-mem-upgrade\docs\04-db-compatibility.md
D:\Warehouse\Topics\openclaw-mem-upgrade\docs\05-performance.md
D:\Warehouse\Topics\openclaw-mem-upgrade\docs\06-graph-upgrade.md
D:\Warehouse\Topics\openclaw-mem-upgrade\docs\07-skills-optimization.md
D:\Warehouse\Topics\openclaw-mem-upgrade\docs\08-backlog.md
D:\Warehouse\Topics\openclaw-mem-upgrade\docs\09-dual-language.md
```

The runbook's original working-directory instruction points to
`D:\Warehouse\Topics\openclaw-mem-upgrade\repo`. CK explicitly replaced that
location with the existing workspace repository above. All other useful runbook
requirements remain guidance: follow them when sound, but adjust when current code
or verification evidence calls for a safer implementation.

### Progress source of truth

```text
D:\Warehouse\Rust-OpenClaw-Core\.agent-harness\workspace\repos\openclaw-mem\PROGRESS-RUN-A.md
```

Read this file plus `git log --oneline -15` before resuming.

## 3. Product intent and architecture

The plan has four primary product goals and one cross-cutting bilingual goal:

1. Maximize capability and retrieval performance while remaining local-first.
2. Consolidate parallel product lanes behind a stable core API instead of deleting
   capabilities.
3. make legacy memory databases explicitly backward-compatible through additive
   schema generations, governed migration, backup, and rollback.
4. Restructure bundled operational skills into discoverable Core, Governance, and
   Labs tiers with executable lint gates.
5. Repair Chinese/English recall through language detection, CJK-aware routing,
   bilingual fallbacks, and measurable retrieval KPIs.

The target is a three-ring product model:

- Ring 0 Core: Store / Pack / Observe and integration APIs.
- Ring 1 Governance: temporal facts, graph, curate, and sync.
- Ring 2 Labs: self-model, dream-lite, gbrain, and other experimental lanes.

The structural strategy is a strangler extraction: move behavior out of the large
CLI into output-free `openclaw_mem.core` functions while preserving every existing
command and flag. CLI, MCP, gateway, and plugin integration should converge on the
stable core API.

Priority when tradeoffs arise:

```text
compatibility > structure > performance > secondary capabilities
```

## 4. Execution contract

Keep these rules for all remaining work:

1. Additive-only database evolution: no table drops, renames, or existing field
   semantic changes, except explicitly governed FTS rebuilds.
2. Preserve the complete CLI command surface. T01 currently locks 253 command paths
   and help-smokes 52 top-level commands.
3. Existing receipt and schema fields may only be extended, not renamed or
   reinterpreted. Golden fixtures remain the compatibility referee.
4. New capability must fail open to the prior behavior when unavailable.
5. Do not push, open a PR, publish, deploy, mutate live OpenClaw/harness state, or
   alter user config/cron without separate explicit authorization.
6. Keep core functions free of `print` and `sys.exit`; they accept connections and
   data/parameters and return structured values. CLI owns formatting and exit codes.
7. Preserve the Store / Pack / Observe ownership split.
8. Use small commits at verified boundaries. A runbook task may use multiple honest
   slice commits when the task is too large for one safe change; mark the task done
   only after all acceptance criteria pass.
9. Preserve unrelated local changes. Do not reset or discard an unfamiliar dirty
   worktree.
10. Apply the completeness-and-test-synthesis gate before any completion claim.
    Active mutation paths require real T3 scenarios including allowed mutation,
    denied mutation, post-state readback, and negative-boundary evidence.

## 5. Run A plan (T00-T27)

### Batch 1: safety net and quick wins

- T00: create branch and progress tracker; establish the fresh test baseline.
- T01: lock the recursive CLI command tree and top-level help surface.
- T02: harden subprocess UTF-8 decoding for Windows cp950 environments.
- T03: add database generation metadata, `PRAGMA user_version`, and `db info`.
- T04: add a migration registry, stamped connect fast path, and future-version guard.
- T05: make qdrant-edge an optional extra with fail-open reporting.
- T06: add per-stage pack timing to trace receipts.
- T07: add a deterministic offline 10k performance suite and baseline report.

### Batch 2: core extraction

- T08: establish `core/db.py`, `core/records.py`, `core/api.py`; decouple MCP DB and
  Store paths from CLI internals.
- T09: move ingest, harvest, store, and all episodic behavior into output-free core
  modules while retaining byte-compatible CLI output.
- T10: move search, vector search, hybrid search, and pack into `core/search.py` and
  `core/pack.py`; eliminate the final MCP import from CLI.
- T11: split the CLI monolith into registry-driven command modules with lazy imports
  while preserving public imports and command paths.

### Batch 3: governed migration

- T12: remove expensive FTS rebuilds from connect; add `db migrate`, `db reindex`,
  backup receipts, dry run, compatibility mode, and rollback.
- T13: generate and test legacy DB fixtures from v1.9.26 and v1.9.31.
- T14: prove zero-write read-only behavior, including WAL/SHM stability.

### Batch 4: retrieval performance and bilingual memory

- T15: add a `VectorIndex` protocol and exact NumPy backend with cache invalidation.
- T16: add governed CJK trigram FTS and query routing.
- T17: add deterministic language detection, bilingual fallback fusion, and mixed
  query rewriting.
- T18: add retrieval KPI receipts and zh/en/mixed golden recall fixtures.
- T19: report embedding integrity in `db info` and doctor.
- T20: optionally add local fastembed provider (`[NET]`; skip honestly if offline).

### Batch 5: Labs and skills

- T21: move Labs implementations under `openclaw_mem/labs` and hide them from default
  help while retaining callable compatibility shims.
- T22: restructure skills into memory/governance/labs tiers with frontmatter and
  shared references.
- T23: harden skill lint for metadata, paths, command truth, size, and duplication.
- T24: add skill lint and recall gates to CI.

### Batch 6: closure

- T25: update CHANGELOG, optional-extra README notes, and DB upgrade checklist.
- T26: run the final full suite, focused gates, perf comparison, CLI smoke chain, and
  governed release check.
- T27: write `RUN-A-REPORT.md` with results, performance, CLI-size change, gates,
  risks, and remaining work. Stop without push or release.

## 6. Completed work and receipts

| Task | Commit | Result and fresh evidence |
| --- | --- | --- |
| T00 | `fc309b0` | Branch/tracker created. Baseline: 789 passed, 3 skipped, 87 subtests; four pre-existing cp950 warnings. |
| T01 | `3175b06` | Locked 253 command paths and 52 top-level help paths; 54 tests passed. |
| T02 | `37fbc19` | Fixed 67 subprocess text-decoding calls; AST guard passed; focused slice 58 passed, 1 skipped. cp950 warnings later disappeared. |
| T03 | `eb03f66` | Added meta/user_version=1 and `db info`; DB/surface and CLI focused gates passed. |
| T04 | `03228ca` | Migration registry, fast path, and downgrade guard. Full suite: 852 passed, 3 skipped, 87 subtests. |
| T05 | `afab25c` | qdrant optional extra and missing-extra contracts; focused gates passed. |
| T06 | `0eac45c` | Five pack stage timings plus total; golden/contracts 11 passed, 10 subtests; JSON contracts 8 passed. |
| T07 | `56e6049` | Deterministic perf suite and 10k baseline. Batch gate: 855 passed, 3 skipped, 87 subtests. |
| T07 repair | `ae81f81` | Stabilized three finite timing mocks after trace expansion. |
| T08 | `584259a` | Stable core DB/records/API modules and MCP decoupling except planned `cmd_pack` bridge. Focused 71 passed; full 857 passed, 3 skipped, 87 subtests. |
| T09 slice 1 | `1557223` | Moved store and ingest behavior into `core/records.py`; regression 191 passed, 26 subtests; precise 15 passed. |
| T09 slice 2 | `c05fd7a` | Moved harvest state transitions and crash recovery into core; regression 194 passed, 26 subtests. |
| T09 slice 3 | `e500975` | Added `core/episodes.py`; moved episodic validation, query, replay, and payload construction. Focused 192 passed, 26 subtests; precise 22 passed; core import isolation passed. |

T07 10k baseline:

```text
ingest:       5653.719 rows/s
search P50:     31.323 ms
search P95:     54.326 ms
vsearch P95:   175.598 ms
pack P95:       38.328 ms
```

The most recent full-suite receipt is from T08. T09 slices have fresh focused and
integration verification but have not yet run the next Batch-level full suite.

## 7. Exact current T09 state

Completed in T09:

- `cmd_store` and `cmd_ingest` core behavior.
- `cmd_harvest`, including orphan-processing recovery, SQLite ingest, index/embed
  fail-open behavior, and archive/delete state transitions.
- Episodic scope/type/timestamp normalization and validation.
- Episodic query and replay row selection and result payloads.
- Core import isolation: importing core does not load the CLI monolith.

Remaining before T09 may be marked done:

- episodic append
- episodic append-session-store-receipt
- episodic search-text construction and lexical/vector search helpers
- episodic embed
- episodic search
- episodic session extraction
- episodic spool ingest
- episodic redact
- episodic garbage collection
- three representative empty-DB `--json` byte-parity comparisons
- final T09 focused/integration gate and full-suite gate

At handoff time, the remaining implementation bodies are still in
`openclaw_mem/cli.py`, chiefly under these symbols:

```text
cmd_episodes_append
cmd_episodes_append_session_store_receipt
_episodic_collect_search_fragments
_episodic_text_fragments_from_json
_episodic_build_search_text
_episodes_search_match_rows
_episodes_vector_rankings
_episodes_fetch_rows_by_ids
_episodes_search_payload
cmd_episodes_embed
cmd_episodes_search
_episodes_extract_sessions_once
cmd_episodes_extract_sessions
_episodes_ingest_once
cmd_episodes_ingest
cmd_episodes_redact
cmd_episodes_gc
```

Recommended slicing:

1. Append + session-store receipt + guards/search-text construction.
2. Lexical/vector search + embed, using dependency injection so existing CLI mocks
   and missing-key fail-open contracts remain valid.
3. Extract + spool ingest and their recovery/idempotency paths.
4. Redact + GC, then parity checks, full T09 verification, progress update, and a
   final task-level commit if needed.

For append, treat this as an active mutation path (verification tier T3): prove a
valid insert and readback; prove duplicate `event_id` does not create a second row;
prove secret/PII/tool-output rejection leaves the DB unchanged; prove core writes no
stdout/stderr; and retain exact CLI error/output behavior.

## 8. Resume procedure

From PowerShell:

```powershell
Set-Location -LiteralPath 'D:\Warehouse\Rust-OpenClaw-Core\.agent-harness\workspace\repos\openclaw-mem'
git status --short --branch
git log --oneline -15
Get-Content -LiteralPath 'PROGRESS-RUN-A.md'
rg -n '^def (_episodes|cmd_episodes)|^def _episodic_|^EPISODIC_|^DEFAULT_EPISODIC' openclaw_mem/cli.py
```

Expected starting state:

```text
## feat/v2-run-a
HEAD is the documentation-only handoff commit directly above e500975
no changed or untracked files
T09 running
```

If the actual state differs, inspect and preserve the changes. Do not blindly reset,
checkout, or stash work that may belong to CK or another agent.

## 9. Verification commands and known environment behavior

Use Python through uv. On this machine, the reliable pytest form is:

```powershell
uv run --frozen python -m pytest tests -q
```

Focused examples:

```powershell
uv run --frozen python -m pytest tests/test_episodes.py tests/test_cli.py tests/test_core_api.py -q
uv run --frozen python -m pytest tests/test_cli_surface_lock.py -q
uv run --frozen python benchmarks/perf/perf_suite.py --rows 10000 --json
git diff --check
```

Do not use plain `uv run pytest` here; the installed environment has previously
required `uv run -- python -m pytest` / `uv run --frozen python -m pytest`.

Full pytest currently takes roughly 4-6 minutes. Do not rerun it blindly after an
interruption: first inspect the last visible receipt and git state.

Before claiming a software task complete, read and apply:

```text
D:\Warehouse\Rust-OpenClaw-Core\.agent-harness\skills\openclaw-imports\workspace\completeness-and-test-synthesis\SKILL.md
```

## 10. Out-of-scope gates

Run A must report but not execute these without CK's explicit decision:

- curate/recall/sync command convergence and deprecation policy
- translation supply chain requiring API key and spend authorization
- public LongMemEval/LoCoMo benchmark and publication posture
- major docs reorganization and v2.0.0 release strategy
- splitting Labs into independent wheels
- push, PR, PyPI publish, mkdocs deploy, version release, or live cutover

Planned follow-ons:

- Run B (convergence): deprecation policy, curate, recall/sync, skill sync, lifecycle,
  and later governance work.
- Run C (capability): translation, sqlite-vec, deeper graph provenance/incremental
  refresh/analyze/jsoncanvas/mem-explore, public benchmark, docs, and v2.0.0.

## 11. Handoff acceptance checklist

The receiving agent should be able to answer yes to all of these before editing:

- I am in the existing workspace repo, not a new clone.
- I am on `feat/v2-run-a` and have inspected the current worktree.
- I read `PROGRESS-RUN-A.md`, this handoff, and the T09/T10 runbook sections.
- I understand that T09 is running, not complete.
- I will preserve CLI/database/receipt compatibility and output-free core boundaries.
- I will test active mutation paths with post-state and denied-path evidence.
- I will not push, release, deploy, or touch live runtime/config/cron.
- I will stop at a clean, verified commit boundary and update the progress tracker.

## 12. Current topology statement

This development work changes only the local `openclaw-mem` repository. Runtime,
gateway, memory-service, scheduled-task, and cron topology have not changed.
