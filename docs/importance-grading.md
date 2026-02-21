# Importance grading (MVP v1)

Status: **PARTIAL** (shipped and usable; rollout / reporting still evolving).

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

### Label semantics (operator intent)
These labels are meant to be used as **triage / recall priorities**, not as “truth.”

- `must_remember`: durable, high-signal items you would regret losing (decisions, stable preferences, key constraints, critical incidents).
- `nice_to_have`: useful context, but not mission-critical (supporting notes, transient-but-helpful facts).
- `ignore`: low-signal noise (routine logs, duplicate status, ephemeral chatter).

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
uv run python -m openclaw_mem store "Prefer tabs over spaces" \
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

Run the scorer regression tests:

```bash
# Option A (recommended): run inside the project env
uv run --python 3.13 -- python -m unittest -q tests/test_heuristic_v1.py

# Option B: system python (no uv)
python3 -m unittest -q tests/test_heuristic_v1.py
```

## Autograde on ingest/harvest (feature-flagged)

You can optionally have `ingest` / `harvest` run `heuristic-v1` and write `detail_json.importance` during import.

- Enable via env var:
  - `OPENCLAW_MEM_IMPORTANCE_SCORER=heuristic-v1`
- Or override per-run:
  - `--importance-scorer {heuristic-v1|off}`

Notes:
- This is designed to be safe + reversible: set the env/flag to `off` to stop grading.
- Existing `detail_json.importance` values are preserved unless a caller explicitly opts into re-grading.

### Run summary output (ops receipt)

When `--json` is enabled, `ingest` and `harvest` also emit a small run summary so cron/ops flows can trend label distribution over time.

Fields:
- `total_seen`: number of observations processed in this run
- `graded_filled`: number of observations where autograde populated missing `detail_json.importance`
- `skipped_existing`: observations that already had `detail_json.importance` (left untouched)
- `skipped_disabled`: observations with missing importance when autograde is disabled
- `scorer_errors`: autograde failures (ingest still succeeds; fail-open)
- `label_counts`: aggregate label distribution for observations that had importance (existing + newly graded)

Example:

```bash
uv run --python 3.13 -- python -m openclaw_mem ingest \
  --file observations.jsonl \
  --importance-scorer heuristic-v1 \
  --json
```

Example JSON output:

```json
{
  "inserted": 3,
  "ids": [101, 102, 103],
  "total_seen": 3,
  "graded_filled": 3,
  "skipped_existing": 0,
  "skipped_disabled": 0,
  "scorer_errors": 0,
  "label_counts": {
    "nice_to_have": 2,
    "must_remember": 1
  }
}
```

### Minimal run summary contract (v0)

To keep scheduled receipts deterministic and redaction-safe, treat `ingest`/`harvest` JSON output as an aggregate-only contract.

Recommended text form (for logs/channels):

```text
harvest-receipt: total_seen=<int>, graded_filled=<int>, skipped_existing=<int>, skipped_disabled=<int>, scorer_errors=<int>, labels=<json>, optional_embedded=<int>
```

Recommended JSON skeleton (subset that should remain stable):

```json
{
  "total_seen": 0,
  "graded_filled": 0,
  "skipped_existing": 0,
  "skipped_disabled": 0,
  "scorer_errors": 0,
  "label_counts": {
    "must_remember": 0,
    "nice_to_have": 0,
    "ignore": 0,
    "unknown": 0
  }
}
```

Keep receipts to counts/ratios only:
- no raw observation content
- no full file paths (prefer labels like `source=harvest-dir` when sharing)
- no raw payload snippets or user traces

