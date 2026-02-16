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
uv run python -m openclaw_mem --help
```

> Note: this repo defines the `openclaw-mem` console entrypoint, so `uv run openclaw-mem ...` is supported after dependency install (`uv sync --locked`).
> `uv run python -m openclaw_mem ...` remains a reliable fallback while troubleshooting entrypoint resolution.

### 2) Local DB smoke test (no OpenClaw required)

```bash
DB=/tmp/openclaw-mem-realitycheck.sqlite

uv run python -m openclaw_mem --db "$DB" --json status

cat > /tmp/openclaw-mem-sample.jsonl <<'JSONL'
{"ts":"2026-02-12T08:10:00Z","kind":"tool","tool_name":"web_search","summary":"searched docs status markers","detail":{"query":"status markers DONE PARTIAL ROADMAP"}}
{"ts":"2026-02-12T08:11:00Z","kind":"note","summary":"Docs updated","detail":{"path":"README.md"}}
JSONL

uv run python -m openclaw_mem --db "$DB" --json ingest --file /tmp/openclaw-mem-sample.jsonl
uv run python -m openclaw_mem --db "$DB" --json search "Docs" --limit 5
uv run python -m openclaw_mem --db "$DB" --json timeline 2 --window 2
uv run python -m openclaw_mem --db "$DB" --json get 2
```

**Expected output shape (minimal):**

- `status` returns a JSON object containing at least:
  - `db`, `count`, `min_ts`, `max_ts`
  - `embeddings.count` and `embeddings.models`
- `ingest` returns something like:
  - `{ "inserted": 2, "ids": [1,2] }`
- `search` returns a JSON array of compact rows containing at least: `id`, `ts`, `kind`, `summary`, plus `snippet` and `score` (it does **not** include `detail_json`).
- `timeline` and `get` return JSON arrays of full rows containing at least: `id`, `ts`, `kind`, `summary`, and `detail_json`.

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

### OpenClaw integration — **PARTIAL**

- Auto-capture plugin (`extensions/openclaw-mem`) — captures tool results to JSONL
- Backend-aware annotations (records backend + memory tool actions for observability)
- Gateway-assisted semantic recall (Route A): `index` + `semantic` — depends on OpenClaw gateway + `memory_search`

### Near-term roadmap — **ROADMAP**

- Package the project so `openclaw-mem` console scripts work directly via `uv sync` / pip
- Context Packer (`pack`) for bounded, cited context bundles
- Graph semantic memory (typed entities/edges)
