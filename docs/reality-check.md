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
uv run --python 3.13 --frozen -- python -m openclaw_mem --db "$DB" --json optimize consolidation-review --limit 200
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
- `optimize review` returns a recommendation-only report (`openclaw-mem.optimize.review.v0`) with signal counts and non-destructive recommendations, including `signals.recent_use` and `staleness.protected_recent_use` when recent pack-lifecycle evidence exists.
- `optimize consolidation-review` returns a recommendation-only episodic maintenance report (`openclaw-mem.optimize.consolidation-review.v0`) with summary/archive/link candidates, source episode refs, recent-use archive protection, and receipt-first link evidence from lifecycle co-selection plus bounded lexical backfill (cold-start lexical fallback when lifecycle rows are absent).
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
- Deterministic graph-preflight pack integration: `pack --use-graph=off|auto|on` with traceable trigger/probe receipts
- Pack decision surfaces (`trust_policy`, graph `provenance_policy`, `policy_surface`, `lifecycle_shadow`) with bounded trace receipts
- Deterministic triage for automation (`triage --mode heartbeat|cron-errors|tasks`)

### Quality layers — **PARTIAL**

- Embeddings + vector search (`embed`, `vsearch`) — requires an API key
- Hybrid retrieval (`hybrid`) + optional rerank providers — requires network/provider; still being evaluated
- AI compression (`summarize`) — requires an API key
- Graph query plane (`graph topology-refresh`, `graph query ...`, `graph health`, drift/provenance checks) — shipped foundation; deeper integrations still evolving
- Graph semantic match v0 (`graph match "<idea/query>"`) — shipped local-first idea → project slice with explanation paths; deeper typed graph automation still evolving
- Recommendation-only optimization observers (`optimize review`, `optimize consolidation-review`) — shipped in the current release scope; now include recent-use-aware decay protection while still proposing only and never mutating stored memories
- Dual-language fields (`--text-en`, EN embedding table) — shipped, still evolving
- Episodic event capture/ingest/query lane — shipped foundation; operator flows still evolving

### OpenClaw integration — **PARTIAL**

- Auto-capture plugin (`extensions/openclaw-mem`) — captures tool results to JSONL
- Backend-aware annotations (records backend + memory tool actions for observability)
- Gateway-assisted semantic recall (Route A): `index` + `semantic` — depends on OpenClaw gateway + `memory_search`

### Near-term roadmap — **ROADMAP**

- Package/distribution ergonomics so `openclaw-mem` install/run flow is cleaner across `uv sync` / pip contexts
- Graph roadmap depth: richer typed-entity wiring + deeper operator queries/autonomy on top of the shipped query plane
- Topology seed automation (`topology-seed`) so curated graph truth is easier to bootstrap and maintain
