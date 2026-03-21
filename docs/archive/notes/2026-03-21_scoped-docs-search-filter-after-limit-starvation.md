# Scoped docs search starvation — root cause, first fix, and verifier (2026-03-21)

Status: **implemented and live-verified**

## Why this note exists

`docsColdLane` scoped retrieval was behaving inconsistently:
- docs ingest had already succeeded
- SQLite rows for `steamer-card-engine` docs existed
- `scopeMap.steamer` already included `steamer-card-engine`
- `matchesScope()` correctly accepted `repo === prefix`
- yet some `memory_docs_search(..., scope="steamer")` queries still missed card-engine docs

This note records the real root cause, the honest first fix, and the live verifier receipt.

## Root cause

The miss was **not** a scope-map failure.

The miss was a retrieval-pipeline bug in `docsColdLane.js`:
1. call `openclaw-mem docs search` with `--limit = boundedLimit`
2. receive a small global top-N candidate set
3. apply `matchesScope()` afterward in the plugin
4. slice again to the requested limit

That means scope filtering happened **after** candidate truncation.
If scoped docs did not make the global top-N, they were already gone before the scope filter ran.

Verdict:
- this was **filter-after-limit starvation**
- symptom class: false scoped 0-hit / query-sensitive scoped miss
- real boundary: scope existed in policy, but not strongly enough in candidate selection

## First honest fix (Slice 1)

Implemented in `openclaw-mem` commit:
- `ef614f4` — `mem-engine: overfetch scoped docs candidates`

Behavior change:
- when a strict docs scope is present, `docsSearchWithCli()` now over-fetches a bounded candidate pool before applying scope filtering
- the widened pool is applied consistently to:
  - `--limit`
  - `--fts-k`
  - `--vec-k`

This keeps the fix bounded:
- no schema migration
- no CLI contract change yet
- no scope semantics moved into the search backend yet
- rollback is a simple revert of one repo commit

## Observability added

The fix also added bounded counters so scoped misses stop looking like black magic:
- `rawCandidates`
- `scopedCandidates`
- existing `filteredByScope`

Interpretation:
- `rawCandidates == 0` → query/index issue
- `rawCandidates > 0 && scopedCandidates == 0` → scope starvation or wrong scope mapping
- `filteredByScope` high → global candidates still dominated by out-of-scope rows

## Verifier receipts

### Function-level verifier
Direct function-level proof against live SQLite after the repo patch showed scoped searches widening the candidate pool:
- `rawCandidates=25`
- `scopedCandidates=15/19/23`
- returned hits included `steamer-card-engine`

### Live runtime verifier
A no-op gateway reload was executed via `config.patch` using a fresh config hash.
Expected receipt was observed:
- `restart.ok=true`
- `signal=SIGUSR1`
- `reason=config.patch`

After reload, active runtime verification passed:
- `memory_docs_search(query="This repo now owns the Steamer card-engine product surfaces", scope="steamer")`
- returned hits from:
  - `steamer-card-engine/docs/PLAYBOOK_OWNERSHIP_ABSORPTION_V1.md`

Interpretation:
- the fix was not only repo-local
- the active OpenClaw runtime successfully served scoped card-engine docs after reload

## Tradeoff

This first fix is **correct enough** and low-risk, but it is still a compensating layer.
The plugin is still over-fetching globally, then filtering by scope.

That means:
- quality is much better
- scope behavior is more stable
- but the clean architectural boundary still has not moved into the CLI/search engine itself

## Next honest step

The proper next slice is **scope pushdown**:
- resolve scope to a repo allowlist in the plugin
- pass that allowlist into `openclaw-mem docs search`
- filter at SQL/query time for FTS/vector candidate generation
- keep plugin-side `matchesScope()` as defense-in-depth until the pushed-down path is proven

See:
- `docs/specs/docs-cold-lane-scope-pushdown-v1.md`

## Topology / WAL note

- Retrieval behavior changed: **yes**
- Runtime/system shape changed: **no**
- This was a retrieval-contract hardening pass, not a topology/system-shape change.
