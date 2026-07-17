# openclaw-mem v2.0.0

Release date: 2026-07-17

v2.0.0 is the completed Run A/Run B upgrade: stable core APIs, governed
database evolution, converged agent-facing commands, seven local harness
installers, policy-shared MCP tools, exact local vector acceleration, and a
full taxonomy/lifecycle/scoring/decay system.

## Upgrade posture

The Python distribution remains `openclaw-context-pack`; the CLI remains
`openclaw-mem`. Existing databases and legacy commands are preserved through
explicit compatibility contracts:

- old command families remain callable through `--help-all` with additive
  deprecation guidance
- v1.9.26 and v1.9.31 database fixtures remain readable
- DB migration is explicit, dry-runnable, backup-first, hash-bound, and
  rollbackable
- the default install remains local SQLite-only; sqlite-vec, NumPy, FastEmbed,
  and Qdrant are optional/fail-open according to their receipts

Existing local agents should follow [Upgrade an existing local agent to
openclaw-mem v2](https://phenomenoner.github.io/openclaw-mem/upgrade-checklist/)
before resuming writers.

## Highlights

### Agent-facing workflow

- Primary help now centers `recall`, `store`, `curate`, `sync`, `graph`, and
  `db`.
- `init` creates a stamped database and fill-only configuration without
  overwriting operator choices.
- `install --harness` and `doctor --harness` support Claude Code, Codex,
  OpenClaw, generic hosts, Gemini CLI, Cursor, and Windsurf with dry-run,
  atomic writes, backups, and verification.

### Retrieval and MCP

- Unified fail-open lexical/vector/hybrid/graph recall emits routing and
  fallback evidence.
- MCP adds policy-shared `mem_recall`/`mem_pack` and read-only graph neighbor,
  path, and impact tools.
- Persisted sqlite-vec indexes carry freshness metadata; automatic selection
  falls back to NumPy then Python without hidden writes.

### Memory governance

- Six lifecycle states and eight deterministic bilingual kinds.
- Category-aware pack quotas, composite score evidence, citation-only use
  tracking, protected decay tiers, and reversible soft archive.
- Composite became the default after the 50-case gate preserved Recall@5 at
  1.000 and improved MRR from 0.740 to 0.990 (+33.78%).

### Performance

Final fixed-seed absolute SLO receipts are committed for 10k and 100k rows.

| 100k lane | Target | p95 | Result |
| --- | ---: | ---: | --- |
| stamped connect | <30 ms | 10.754 ms | pass |
| lexical recall | <50 ms | 26.805 ms | pass |
| hybrid recall | <200 ms | 75.397 ms | pass |
| graph-auto pack | <300 ms | 62.160 ms | pass |
| sqlite-vec exact search | <30 ms | 23.030 ms | pass |

Final verification fixed a use-tracking regression in which any observation
UPDATE invalidated the graph-scope cache and forced a 100k-row scope rescan.
Invalidation now occurs only for insert/delete or a real scope change.

## Install v2.0.0

From PyPI:

```bash
python -m pip install --upgrade "openclaw-context-pack==2.0.0"
```

Directly from the GitHub tag:

```bash
python -m pip install --upgrade \
  "openclaw-context-pack @ git+https://github.com/phenomenoner/openclaw-mem.git@v2.0.0"
```

Repository checkout:

```bash
git fetch --tags origin
git checkout v2.0.0
uv sync --locked
```

## Verification

- local v2.0.0 full suite: 1175 passed, 3 skipped, 5 expected compatibility warnings,
  and 87 unittest subtests
- independent Ubuntu GitHub Actions: both push and PR test jobs passed
- surface/alias/MCP/golden slice: 123 passed
- strict MkDocs build and docs/skill tests passed
- wheel and sdist built; both `openclaw-mem` and `openclaw-mem-mcp` started from
  an isolated wheel installation
- tag CI, main CI, GitHub Pages deployment, and trusted PyPI publication passed
- public diff scan found no high-confidence secrets or private absolute paths

The full task ledger, deviations, and Run C entry conditions are in
`RUN-B-REPORT.md`.

## Still gated

- live memory-owner cutover in an operator environment
- public LongMemEval/LoCoMo product claims
- Qdrant L3 promotion beyond the optional read-index/cache posture
