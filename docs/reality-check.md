# Reality check & status

This page is intentionally factual.

**Legend**

- **DONE** — works locally and deterministically (no network required unless stated)
- **PARTIAL** — shipped, but optional/experimental and/or depends on external services
- **ROADMAP** — planned; not shipped yet

---

## Reality check (verifiable in ~60s)

### 1) Install deps (from a fresh clone)

```bash
uv sync --locked
uv run --python 3.13 --frozen -- python -m openclaw_mem --help
```

> Note: this repo defines the `openclaw-mem` console entrypoint, so `uv run openclaw-mem ...` is supported after dependency install (`uv sync --locked`).
> The docs use `uv run --python 3.13 --frozen -- python -m openclaw_mem ...` as the most explicit source-checkout form.

### 2) Local DB smoke test (no OpenClaw required)

```bash
DB=/tmp/openclaw-mem-realitycheck.sqlite

uv run --python 3.13 --frozen -- python -m openclaw_mem --db "$DB" --json status

cat > /tmp/openclaw-mem-sample.jsonl <<'JSONL'
{"ts":"2026-02-12T08:10:00Z","kind":"tool","tool_name":"web_search","summary":"searched docs status markers","detail":{"query":"status markers DONE PARTIAL ROADMAP"}}
{"ts":"2026-02-12T08:11:00Z","kind":"note","summary":"Docs updated","detail":{"path":"README.md"}}
JSONL

uv run --python 3.13 --frozen -- python -m openclaw_mem --db "$DB" --json ingest --file /tmp/openclaw-mem-sample.jsonl
uv run --python 3.13 --frozen -- python -m openclaw_mem --db "$DB" --json search "Docs" --limit 5
uv run --python 3.13 --frozen -- python -m openclaw_mem --db "$DB" --json timeline 2 --window 2
uv run --python 3.13 --frozen -- python -m openclaw_mem --db "$DB" --json get 2
uv run --python 3.13 --frozen -- python -m openclaw_mem --db "$DB" --json optimize review --limit 200
```

**Expected output shape (minimal):**

- `status` returns a JSON object containing at least:
  - `db`, `count`, `min_ts`, `max_ts`
  - `embeddings.count` and `embeddings.models`
- `ingest` returns something like:
  - `{ "inserted": 2, "ids": [1,2] }`
- `search` returns a JSON array of compact rows containing at least: `id`, `ts`, `kind`, `summary`, plus `snippet` and `score` (it does **not** include `detail_json`).
- `timeline` and `get` return JSON arrays of full rows containing at least: `id`, `ts`, `kind`, `summary`, and `detail_json`.
- `optimize review` returns a recommendation-only report (`openclaw-mem.optimize.review.v0`) with signal counts and non-destructive recommendations.

### 3) Engine receipt debug smoke (local-only, no memory text)

```bash
node --experimental-transform-types tools/mem-engine-receipts-debug.mjs
```

Expected:
- prints one synthetic recall lifecycle receipt (`openclaw-mem-engine.recall.receipt.v1`)
- prints one synthetic autoCapture lifecycle receipt (`openclaw-mem-engine.autoCapture.receipt.v1`)
- payload contains IDs/scores/counts only (no memory content text)

---

## Status map (operator view)

### Core (local, deterministic) — **DONE**

- SQLite ledger + FTS5
- JSON receipts (`--json`)
- Progressive recall: `ingest → search → timeline → get`
- Export with a safety confirmation step (`export --yes`)
- Deterministic triage for automation (`triage --mode heartbeat|cron-errors|tasks`)

### Quality layers — **PARTIAL**

- Embeddings + vector search (`embed`, `vsearch`) — requires an API key
- Hybrid retrieval (`hybrid`) + optional rerank providers — requires network/provider; still being evaluated
- AI compression (`summarize`) — requires an API key
- Dual-language fields (`--text-en`, EN embedding table) — shipped, still evolving
- Recommendation-only optimization observer (`optimize review`) — shipped in v0.1 scope; proposes only, never mutates stored memories

### OpenClaw integration — **PARTIAL**

- Auto-capture plugin (`extensions/openclaw-mem`) — captures tool results to JSONL
- Backend-aware annotations (records backend + memory tool actions for observability)
- Gateway-assisted semantic recall (Route A): `index` + `semantic` — depends on OpenClaw gateway + `memory_search`

### Near-term roadmap — **ROADMAP**

- Package the project so `openclaw-mem` console scripts work directly via `uv sync` / pip
- Context Packer (`pack`) for bounded, cited context bundles
- Graph semantic memory (typed entities/edges)

### Graphic Memory compiled synthesis — **PARTIAL**

- `graph synth compile` — compile a reusable synthesis card from explicit refs or query-preflight selection
- `graph synth stale` — deterministic stale check (source digest + query-selection drift)
- `graph lint` — deterministic health checks for stale cards / missing source metadata / unreferenced capture rows
- Graph preflight preference for fresh synthesis cards when they cover multiple selected raw refs
- Graph pack preference for fresh synthesis cards when explicit refs are covered by a fresh synthesis card
- Main `pack --use-graph` now records graph-consumption receipts and elides raw L1 lines already covered by preferred synthesis cards in the combined graph-aware bundle
- `cmd_hybrid` now prefers fresh synthesis cards in top results when they cover multiple high-ranked raw hits, and emits graph-consumption receipts on the synthetic result
- `search` now prefers fresh synthesis cards in top results when multiple matched raw hits are covered by the same card, with graph-consumption receipts on the synthetic result
- `graph synth refresh` now replays the old card’s selection, emits a fresh replacement card, and marks the old card as `superseded` with a `superseded_by` receipt
- `graph lint` now reports deterministic coverage pressure / `candidateCardSuggestions` using scope + repeated-keyword clusters, not just scope-only grouping
- `graph synth stale` / `graph lint` now surface deterministic review + contradiction-keyword signals from newly selected refs
- Optional Markdown materialization during compile (`--write-md`)
