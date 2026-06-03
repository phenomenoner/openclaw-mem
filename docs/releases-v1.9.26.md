# openclaw-mem v1.9.26

v1.9.26 ships the temporal fact materialized view.

## Added

- `openclaw-mem graph fact registry`
- `openclaw-mem graph fact assert`
- `openclaw-mem graph fact current`
- `openclaw-mem graph fact timeline`
- `openclaw-mem graph fact lint`
- `openclaw-mem graph fact pack`
- `openclaw-mem graph fact stale`
- `openclaw-mem graph fact invalidate`
- `openclaw-mem graph fact route`
- `openclaw-mem graph fact propose`
- `openclaw-mem graph fact measure-extraction`
- `openclaw-mem graph fact rebuild`

## Safety

- Facts require resolvable source refs before assertion.
- Assertion receipts are kept separate from evidence source refs.
- Single-valued predicates fail lint on unresolved overlapping current truth.
- Source-hash drift marks facts stale; stale facts are excluded from current truth unless explicitly requested.
- Extraction assist is review-only and writes nothing.

## Topology

No Gateway config, cron topology, memory backend, prompt injection, or runtime model routing changed in this release.

## Verification

- `uv run pytest tests/test_graph_facts.py`
- `uv run pytest tests/test_graph_facts.py tests/test_graph_query_cli.py tests/test_context_pack_golden.py tests/test_graph_match_cli.py`
- `uv run python -m py_compile openclaw_mem/graph/facts.py openclaw_mem/cli.py tests/test_graph_facts.py`
- `git diff --check`
