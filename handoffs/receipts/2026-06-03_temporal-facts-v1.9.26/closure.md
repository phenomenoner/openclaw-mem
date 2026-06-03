# Temporal facts v1.9.26 closure

## Goal

Implement Phase 0 through Phase 6 of the temporal fact materialized view, with public-facing docs/skill hygiene, independent second-brain review, tests, commit/push, and final tag.

## Completed phases

- Phase 0: fact schema, controlled predicate registry, interval semantics, stable id fixtures.
- Phase 1: deterministic `openclaw_mem.graph.facts` core with source resolver, lint, derived SQLite view, rebuild.
- Phase 2: `openclaw-mem graph fact assert|current|timeline|lint`.
- Phase 3: `graph fact pack` with ContextPack-compatible output and trace.
- Phase 4: source-hash staleness detection and stale exclusion from current truth by default.
- Phase 5: explicit `graph fact route` helper with visible fact-pack receipt.
- Phase 6: review-only `graph fact propose` and `measure-extraction`; no apply lane.

## Independent review

- Claude review: `claude-phase-review.md`
- Resolution: `claude-finding-resolution.md`
- Fixed before release: duplicate-source confidence inflation, assert-time single-value overlap, structured evidence refs in packs, empty proposal input, docs for rebuild fixture exception.

## Verifiers

- `uv run pytest tests/test_graph_facts.py` -> 7 passed
- `uv run pytest tests/test_graph_facts.py tests/test_graph_query_cli.py tests/test_context_pack_golden.py tests/test_graph_match_cli.py` -> 28 passed
- `uv run pytest` -> 712 passed
- `uv run python -m py_compile openclaw_mem/graph/facts.py openclaw_mem/cli.py tests/test_graph_facts.py` -> passed
- `git diff --cached --check` -> passed
- `uv run --extra docs mkdocs build --strict` -> passed
- `uv run openclaw-mem governed release-check --repo-root . --expected-version 1.9.26 --docs-glob docs/temporal-facts.md --no-require-receipt --json` -> ok
- `uv run openclaw-mem status --json` -> version `1.9.26`
- CLI smoke: assert + pack emitted a ContextPack with `evidenceSourceRefs`

## Topology

No Gateway config, cron topology, memory backend, prompt-injection path, model routing, or external service topology changed.

## Rollback

- Revert the release commit.
- Drop the additive `graph fact` CLI namespace.
- Delete/rebuild derived `graph_facts` tables if needed.
- Store source evidence and Observe receipts are untouched by rollback.

## Known v0 limits

- Extraction is heuristic and review-only.
- No multi-hop inference.
- No automatic prompt injection.
- `rebuild --allow-dangling-source` is a fixture/backfill escape hatch, not a normal assertion path.
