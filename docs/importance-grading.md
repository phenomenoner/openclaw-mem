# Importance grading (MVP v1)

## What this is
`openclaw-mem` supports **importance grading** so downstream workflows can:
- prioritize what gets recalled,
- filter what gets triaged,
- and keep long-term memory useful as volume grows.

This is intentionally designed to be:
- **local-first** (deterministic baseline)
- **auditable** (stored in `detail_json`)
- **backwards compatible** (legacy numeric importance still accepted)

## Canonical storage shape
We store a canonical object at:

- `detail_json.importance`

Canonical object fields:

```json
{
  "score": 0.86,
  "label": "must_remember",
  "rationale": "Why this matters.",
  "method": "manual-via-cli",
  "version": 1,
  "graded_at": "2026-02-11T00:00:00Z"
}
```

### Score → label mapping (MVP v1)
- `score >= 0.80` → `must_remember`
- `score >= 0.50` → `nice_to_have`
- else → `ignore`

### Ungraded items
If `detail_json.importance` is missing, treat it as **unknown**.
By default, do **not** drop/filter ungraded items unless a caller explicitly requests filtering.

## Compatibility rules
`openclaw-mem` consumers should accept both:
- legacy numeric: `importance: 0.86`
- canonical object: `importance: {"score": 0.86, ...}`

See `openclaw_mem.importance.parse_importance_score()`.

## Writing importance
### Manual (via CLI)
`openclaw-mem store` writes the canonical importance object.

Example:

```bash
uv run openclaw-mem store "Prefer tabs over spaces" \
  --category preference \
  --importance 0.9 \
  --json
```

## Deterministic heuristic (heuristic-v1)
A deterministic scorer exists at:
- `openclaw_mem/heuristic_v1.py`

It produces the canonical object (`method=heuristic-v1`).

### Regression test corpus
A shared JSONL testcase corpus is stored under:
- `tests/data/HEURISTIC_TESTCASES.jsonl`

Run:

```bash
python3 -m unittest -q tests/test_heuristic_v1.py
```

## Roadmap (next)
- Wire `heuristic-v1` into the capture/ingest path behind a **feature flag** (safe, reversible).
- Evaluate before/after recall quality using a small benchmark set.
