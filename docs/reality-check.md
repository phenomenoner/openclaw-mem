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
uv run --python 3.13 --frozen -- python -m openclaw_mem --db "$DB" --json optimize policy-loop --review-limit 200 --writeback-limit 100 --lifecycle-limit 100
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
- `optimize policy-loop` returns a read-only rollout report (`openclaw-mem.optimize.policy-loop.v0`) with Stage B/C gate status, writeback linkage, and lifecycle-shadow evidence (no mutations).

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
- Context pack command (`pack`) with fail-open baseline behavior
- Pack decision surfaces (`trust_policy`, graph `provenance_policy`, `policy_surface`, `lifecycle_shadow`) with bounded trace receipts
- Deterministic triage for automation (`triage --mode heartbeat|cron-errors|tasks`)

### Quality layers — **PARTIAL**

- Embeddings + vector search (`embed`, `vsearch`) — requires an API key
- Hybrid retrieval (`hybrid`) + optional rerank providers — requires network/provider; still being evaluated
- AI compression (`summarize`) — requires an API key
- Graph query plane (`graph topology-refresh`, `graph query ...`, drift/provenance checks) — shipped foundation; deeper integrations still evolving
- Recommendation-only optimization observer (`optimize review`) — shipped in the current release scope; proposes only, never mutates stored memories
- Dual-language fields (`--text-en`, EN embedding table) — shipped, still evolving
- Episodic event capture/ingest/query lane — shipped foundation; operator flows still evolving

### OpenClaw integration — **PARTIAL**

- Auto-capture plugin (`extensions/openclaw-mem`) — captures tool results to JSONL
- Backend-aware annotations (records backend + memory tool actions for observability)
- Gateway-assisted semantic recall (Route A): `index` + `semantic` — depends on OpenClaw gateway + `memory_search`

### Near-term roadmap — **ROADMAP**

- Package/distribution ergonomics so `openclaw-mem` install/run flow is cleaner across `uv sync` / pip contexts
- Graph roadmap depth: richer provenance wiring + higher-level operator queries on top of the shipped query plane
- Topology seed automation (`topology-seed`) so curated graph truth is easier to bootstrap and maintain
