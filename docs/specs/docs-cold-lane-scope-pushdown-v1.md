# Docs cold lane — scope pushdown v1

Status: **planned**

## Purpose

Slice 1 fixed scoped docs misses by widening the candidate pool before plugin-side scope filtering.
That was the right emergency hardening cut.

Slice 2 moves the boundary to the cleaner place:
- **scope should influence candidate generation, not only post-hoc filtering**

The goal is to make scoped docs retrieval behave like a true scoped query path instead of a global search with a late scope sieve.

## Whole-picture promise

When an operator asks inside a scope such as `steamer`, the docs search path should:
- generate candidates from the relevant repo set first
- keep receipts explaining which scope pushdown was applied
- reduce false 0-hit misses caused by out-of-scope global competition

Fake progress would be:
- adding more overfetch heuristics without moving the boundary
- teaching the CLI raw scope semantics and duplicating policy logic
- removing plugin-side safety filters before pushdown is proven

## Design verdict

Preferred architecture:
- keep **scope policy resolution in the plugin**
- push a **resolved repo allowlist** into the CLI/search path
- keep plugin-side `matchesScope()` as a safety net for the first rollout

This keeps responsibilities clean:
- plugin = policy plane
- CLI/search = data plane

## First implementation cut

Add a bounded CLI contract for repo pushdown:

```text
openclaw-mem docs search <query> --scope-repos <repo> [<repo> ...]
```

Meaning:
- when present, only chunks from the listed repos are eligible candidates
- this is an exact repo allowlist, not a fuzzy token filter

## Why repo allowlist pushdown first

The plugin already knows how to resolve scope to concrete repo targets from:
- `scopeMappingStrategy`
- `scopeMap`
- fallback short-scope key rules

So the smallest honest cut is:
1. resolve scope in plugin
2. derive repo allowlist
3. pass repo allowlist to CLI
4. let FTS/vector queries filter with exact `repo IN (...)`

This avoids teaching the CLI about high-level scope semantics.

## Boundary rules

### In scope for v1
- exact repo pushdown only
- support the common scope-mapping cases:
  - `map`
  - `repo_prefix`
- plugin still performs residual `matchesScope()` filtering after CLI returns rows
- receipts/log markers become explicit about pushdown usage

### Explicitly deferred
- path-level pushdown for `path_prefix`
- removing plugin-side residual filtering
- dynamic/learned overfetch tuning
- scope-aware reranking
- index partitioning by scope/repo
- changing the chunk schema

## Proposed plugin behavior

When scope is present:
- compute `pushdownRepos`
- if non-empty, pass them into CLI
- still apply `matchesScope()` afterward

Resolution rules:
- `none` → no pushdown
- `repo_prefix` → use `shortScopeKey(scope)` as repo allowlist
- `map` → use the repo-capable entries from `scopeMap[scope]` and fallback `scopeMap[shortKey]`
- `path_prefix` → defer pushdown, keep client-side filter only

## Proposed CLI behavior

Add `--scope-repos` to `docs search`.

### FTS path
Apply repo allowlist in SQL via the joined relational table, not inside FTS token syntax.
Preferred shape:
- `... WHERE docs_chunks_fts MATCH ? AND c.repo IN (?, ?, ...)`

### Vector path
Apply repo allowlist in the vector candidate query via join to `docs_chunks`:
- `... JOIN docs_chunks c ON c.id = e.chunk_rowid WHERE c.repo IN (?, ?, ...)`

Reason:
- exact repo equality is safer than FTS token tricks for repo names with punctuation/hyphens
- existing relational indexes can help

## Receipts / trace additions

Add these fields to plugin receipts and CLI trace output:
- `pushdownRepos`
- `pushdownApplied`
- `rawCandidates`
- `scopedCandidates`
- `filteredByScope`

Healthy expectation after v1 lands:
- `filteredByScope` trends toward `0`
- `rawCandidates` becomes the candidate set **after** repo pushdown
- if `filteredByScope` stays high, repo allowlist derivation is incomplete

## Verifier plan

### Unit / fixture level
1. ingest docs for three repos with overlapping terms
2. search with `--scope-repos repo-a repo-b`
3. assert only `repo-a` / `repo-b` rows are returned
4. assert omitted `--scope-repos` still returns all repos normally
5. assert residual plugin-side filtering removes nothing unexpected for the pushdown case

### Integration / plugin level
1. `scope=steamer` query that previously depended on overfetch
2. confirm returned hits include `steamer-card-engine`
3. inspect receipt/log fields:
   - `pushdownApplied=true`
   - `pushdownRepos` includes `StrategyExecuter_Steamer-Antigravity`, `steamer-card-engine`
   - `filteredByScope` is `0` or materially lower than Slice 1 baseline

### Regression posture
- unscoped search must behave the same
- scopes without repo pushdown (`path_prefix`) must remain fail-open via existing plugin filter

## Rollback trigger

Rollback if any are true:
- CLI pushdown returns fewer in-scope hits than the Slice 1 overfetch path on the verifier set
- `filteredByScope` remains high because pushdown repo derivation is incomplete or wrong
- unscoped search quality or behavior regresses
- repo allowlist handling introduces query failures or malformed SQL parameterization

Rollback action:
- revert CLI/plugin pushdown commit(s)
- keep Slice 1 overfetch behavior in place

## Recommended sequencing

1. add CLI `--scope-repos`
2. implement exact repo filtering in FTS + vector candidate queries
3. wire plugin `pushdownRepos`
4. keep plugin residual `matchesScope()` filter on
5. verify `filteredByScope` collapses toward zero
6. only then consider removing or shrinking scoped overfetch

## Closure note

This slice should be treated as a **retrieval-contract hardening** change.
It improves scoped recall quality and observability, but does not alter runtime/system topology.
