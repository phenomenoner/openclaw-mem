# Reality check & status

This page answers one question: **what is actually shipped, and how quickly can you verify it yourself?**

**Legend**

- **DONE** — works locally and deterministically (no network required unless stated)
- **PARTIAL** — shipped, but optional/experimental and/or depends on external services
- **ROADMAP** — planned; not shipped yet

---

## Quick reality check (verifiable in ~60s)

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

uv run --python 3.13 --frozen -- python -m openclaw_mem init --db "$DB" --json

cat > /tmp/openclaw-mem-sample.jsonl <<'JSONL'
{"ts":"2026-02-12T08:10:00Z","kind":"tool","tool_name":"web_search","summary":"searched docs status markers","detail":{"query":"status markers DONE PARTIAL ROADMAP"}}
{"ts":"2026-02-12T08:11:00Z","kind":"note","summary":"Docs updated","detail":{"path":"README.md"}}
JSONL

uv run --python 3.13 --frozen -- python -m openclaw_mem --db "$DB" --json ingest --file /tmp/openclaw-mem-sample.jsonl
uv run --python 3.13 --frozen -- python -m openclaw_mem recall "Docs" --db "$DB" --mode auto --json
uv run --python 3.13 --frozen -- python -m openclaw_mem pack --db "$DB" --query "Docs status" --trace --json
uv run --python 3.13 --frozen -- python -m openclaw_mem curate scan --target memory --db "$DB" --json
uv run --python 3.13 --frozen -- python -m openclaw_mem db info --db "$DB" --json
```

**Expected output shape (minimal):**

- `init` returns `openclaw-mem.init.v1` plus config/capability evidence.
- `ingest` returns something like:
  - `{ "inserted": 2, "ids": [1,2] }`
- `recall` reports the selected/fallback lane and returns attributable results.
- `pack` returns bounded items, citations, composite score evidence, and a trace.
- `curate scan` is review-only and emits governed candidates without applying a mutation.
- `db info` reports schema, FTS, taxonomy/lifecycle distributions, embeddings,
  and optional sqlite-vec posture.

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
- Primary `recall` router across lexical/vector/hybrid/graph lanes
- Six-state lifecycle, eight-kind taxonomy, pack quotas, composite scoring,
  citation-only use tracking, and reversible soft archive
- Exact sqlite-vec → NumPy → Python vector fallback chain with explicit receipts
- Deterministic graph-preflight pack integration: `pack --use-graph=off|auto|on` with traceable trigger/probe receipts
- Pack decision surfaces (`trust_policy`, graph `provenance_policy`, `policy_surface`, `lifecycle_shadow`) with bounded trace receipts
- Deterministic triage for automation (`triage --mode heartbeat|cron-errors|tasks`)

### Quality layers — **PARTIAL**

- Embeddings + vector search (`embed`, `vsearch`) — API and optional local
  FastEmbed providers are supported; missing optional providers degrade explicitly
- Hybrid retrieval (`hybrid`) — shipped; optional rerank/network providers remain opt-in
- AI compression (`summarize`) — requires an API key
- Graph query plane (`graph topology-refresh`, `graph query ...`, `graph health`, drift/provenance checks) — shipped foundation; deeper integrations still evolving
- Graph semantic match v0 (`graph match "<idea/query>"`) — shipped local-first idea → project slice with explanation paths; deeper typed graph automation still evolving
- Graph-assisted search first slice (`search --graph --graph-path <graph.json>`) — shipped opt-in; default off, fail-open to lexical-only, deterministic blended ranking with `rank_components` trace
- Graph-aware pack ranking (`pack --graph-aware`) — shipped opt-in trace lane; default off, fail-open, zero-write
- Topology writer (`graph render topology`) — shipped generated review surface (Markdown summary + Mermaid view + drift report); generated docs are review-only, not source of truth
- Graph fact guard pilot (`graph fact propose|guard`) — shipped advisory-only pre-edit guard; proposals require source refs, stale/superseded facts are excluded from current guard truth
- Recommendation-only optimization observers (`optimize review`, `optimize consolidation-review`) — shipped in the current release scope; now include recent-use-aware decay protection plus bounded importance-drift spot checks while still proposing only and never mutating stored memories
- Dual-language fields (`--text-en`, EN embedding table) — shipped, still evolving
- Episodic event capture/ingest/query lane — shipped foundation; operator flows still evolving
- Episodic verbatim semantic lane (`episodes embed`, `episodes search --mode hybrid|vector`) — shipped first production slice; still operator-driven and read-only

### OpenClaw integration — **PARTIAL**

- Auto-capture plugin (`extensions/openclaw-mem`) — captures tool results to JSONL
- Backend-aware annotations (records backend + memory tool actions for observability)
- Gateway-assisted semantic recall (Route A): `index` + `semantic` — depends on OpenClaw gateway + `memory_search`
- Host bridge envelopes (`bridge status|recall|store`) — per-operation versioned JSON envelopes (`openclaw-mem-engine.bridge.<op>.v1`); recall is read-only, store performs a canonical write only with explicit operator approval
- Unified installer/doctor adapters for Claude Code, Codex, OpenClaw, generic,
  Gemini CLI, Cursor, and Windsurf
- MCP `mem_recall`/`mem_pack` equivalence plus read-only graph tools

### Near-term roadmap — **ROADMAP**

- Graph roadmap depth: richer typed-entity wiring + deeper operator queries/autonomy on top of the shipped query plane
- Topology seed automation (`topology-seed`) so curated graph truth is easier to bootstrap and maintain
- Consolidate/promotion/dissent workflows on top of v2 lifecycle and scoring evidence

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
