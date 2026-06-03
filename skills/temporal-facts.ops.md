# temporal-facts.ops

Use when operating `openclaw-mem graph fact ...`, the temporal fact materialized view.

## Purpose

Temporal facts provide source-linked current truth, timelines, and ContextPack-compatible evidence packs for one subject at a time.
They are a derived view over Store evidence, not a new source of truth.

## Commands

Inspect the predicate registry:

```bash
openclaw-mem graph fact registry
```

Assert a fact:

```bash
openclaw-mem --db facts.sqlite graph fact assert \
  --subject entity:openclaw-mem \
  --predicate source_of_truth \
  --object "Store records" \
  --valid-from 2026-06-03T00:00:00Z \
  --source-ref doc:docs/temporal-facts.md \
  --assertion-ref receipt:demo \
  --source-root .
```

Read and pack:

```bash
openclaw-mem --db facts.sqlite graph fact current --subject entity:openclaw-mem --source-root .
openclaw-mem --db facts.sqlite graph fact timeline --subject entity:openclaw-mem --source-root .
openclaw-mem --db facts.sqlite graph fact pack --subject entity:openclaw-mem --source-root .
```

Lint and stale detection:

```bash
openclaw-mem --db facts.sqlite graph fact lint --source-root .
openclaw-mem --db facts.sqlite graph fact stale --source-root .
```

Review-only extraction:

```bash
openclaw-mem graph fact propose --text "entity:x status active" --source-ref doc:source.md
openclaw-mem graph fact measure-extraction --corpus corpus.jsonl --golden golden.jsonl
```

## Rules

- Every asserted fact needs at least one resolvable `--source-ref`.
- Keep `assertion_ref` separate from evidence source refs.
- Use controlled predicates only; unknown predicates fail lint.
- For single-valued predicates, use `--supersedes` or `invalidate` instead of overlapping active facts.
- Treat stale facts as evidence, not current truth. Do not pass `--include-stale` unless the caller explicitly wants stale evidence.
- Extraction proposals are review-only. `writes_performed` must stay `false`; no apply lane exists in v0.
- `rebuild --allow-dangling-source` is for fixture/backfill inspection only. Do not use it for operator assertions.
- No Gateway, cron, memory backend, or prompt injection topology changes are implied by this skill.

## Closeout checks

- `uv run pytest tests/test_graph_facts.py`
- `uv run pytest tests/test_graph_facts.py tests/test_graph_query_cli.py tests/test_context_pack_golden.py tests/test_graph_match_cli.py`
- `git diff --check`
- Public docs reviewed: `docs/temporal-facts.md`, README, MkDocs nav, changelog.
