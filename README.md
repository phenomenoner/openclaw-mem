# openclaw-mem

**Local-first long‑term memory layer for OpenClaw agents.**

`openclaw-mem` captures useful observations (what tools ran, what happened, what mattered), stores them in a lightweight local SQLite database, and enables **cheap progressive recall** back into the agent:

1) **Search** (compact hits) → 2) **Timeline** (nearby context) → 3) **Get** (full record)

Optional upgrades add embeddings + hybrid ranking, dual-language assist (zh/en, etc.), gateway-assisted semantic recall, and deterministic triage for heartbeats.

> Pitch (truthful): if your agent is already doing real work, `openclaw-mem` turns that work into a searchable, auditable memory trail—without requiring an external database.

---

## What you get (feature map)

### Core (local, deterministic)

- **Observation store**: SQLite + FTS5
- **Progressive disclosure recall**:
  - `search` → `timeline` → `get`
- **Export**: `export` (with safety confirmation)
- **Auto-ingest helper**: `harvest` (ingest + optional embeddings)

### Optional (higher recall quality)

- **Embeddings**: `embed`, `vsearch`
- **Hybrid retrieval**: `hybrid` (FTS + vector, **RRF** fusion)
- **Optional post-retrieval rerank (opt-in)** on hybrid path:
  - `--rerank-provider jina|cohere`
  - `--rerank-model ... --rerank-topn ...`
  - fail-open fallback to base RRF ranking on provider/network errors
- **Dual-language memory** (original + optional English companion):
  - `store --text-en ...`
  - dedicated EN embedding table (`observation_embeddings_en`)
  - optional EN assist query route in hybrid (`--query-en`)

### Optional (OpenClaw integration)

- **Auto-capture plugin** (`extensions/openclaw-mem`): listens to `tool_result_persist` and writes JSONL for ingestion.
- **Backend adapter annotations (v0.5.9)**:
  - capture layer remains sidecar-only (no tool registration)
  - records memory backend metadata (`memory-core` / `memory-lancedb`) into `detail_json`
  - tracks memory tool actions (`memory_store` / `memory_recall` / `memory_forget` / `memory_search` / `memory_get`) for audit and monitoring
- **Gateway-assisted semantic recall (Route A)**:
  - `index` (build markdown index)
  - `semantic` (use OpenClaw `memory_search` as a black-box semantic retriever)

### Operational (heartbeat-safe)

- **Deterministic triage**: `triage` modes for:
  - `heartbeat`
  - `cron-errors`
  - `tasks`
- Includes dedupe state to avoid repeating the same alert every heartbeat.
- **Importance grading (MVP v1)**: canonical `detail_json.importance` objects + deterministic `heuristic-v1` scorer + regression tests.
  - Notes: `docs/importance-grading.md`

---

## Installation

```bash
git clone https://github.com/phenomenoner/openclaw-mem.git
cd openclaw-mem
uv sync --locked
```

After syncing, you can run either:
- `uv run openclaw-mem ...` (recommended, always uses the project env)
- or `openclaw-mem ...` if the script is on your PATH.

---

## 5-minute tour

```bash
# 1) Create/open DB and show counts
uv run openclaw-mem status --json

# 1.5) Check active OpenClaw memory backend + fallback posture
uv run openclaw-mem backend --json

# 2) Ingest JSONL observations
uv run openclaw-mem ingest --file observations.jsonl --json

# 3) Layer 1 recall (compact)
uv run openclaw-mem search "gateway timeout" --limit 10 --json

# 4) Layer 2 recall (nearby context)
uv run openclaw-mem timeline 42 --window 3 --json

# 5) Layer 3 recall (full rows)
uv run openclaw-mem get 42 --json
```

### Proactive memory (explicit “remember this”)

```bash
uv run openclaw-mem store "Prefer tabs over spaces" \
  --category preference --importance 0.9 --json

uv run openclaw-mem hybrid "tabs or spaces preference" --limit 5 --json
uv run openclaw-mem hybrid "tabs or spaces preference" \
  --rerank-provider jina --rerank-topn 20 --json
```

---

## Typical outcomes (what it enables)

This is what a “serious” always-on agent starts to feel like when memory is stable:

- Wake up to a **daily briefing** (what matters today + what broke overnight)
- Fewer context drops: the agent can **carry threads across days**
- Less busywork: deterministic background scans + human approval only when needed
- A growing, auditable trail you can browse later (and optionally visualize in Obsidian)

## How it fits together (system view)

**Capture → Ingest → Recall**

- **Capture** (optional): the OpenClaw plugin writes append-only JSONL observations.
- **Ingest**: `ingest`/`harvest` imports JSONL into SQLite (WAL-enabled), optionally building embeddings.
- **Recall**:
  - cheap keyword recall via FTS
  - higher quality retrieval via embeddings + hybrid fusion
  - optional gateway semantic route for “black-box” semantic recall

This design is intentionally practical:
- local files you can inspect/backup
- deterministic baseline behavior
- optional AI where it provides leverage (compression/embeddings), not as the only way the system works

### Ecosystem fit with OpenClaw native memory

`openclaw-mem` is intentionally a **sidecar**, not a slot owner:

- `memory-core` owns native baseline tools (`memory_search`, `memory_get`)
- `memory-lancedb` owns official semantic tools (`memory_store`, `memory_recall`, `memory_forget`)
- `openclaw-mem` adds capture, local-first recall, triage, and backend-aware observability

Practical effect for operators:
- you can switch memory slot (`memory-core` ↔ `memory-lancedb`) without rebuilding your memory ledger pipeline
- you keep a stable local audit trail during migrations and incidents
- rollback remains one slot flip away

See detailed deployment patterns:
- `docs/ecosystem-fit.md`

---

## Dual-language memory (zh/en etc.)

```bash
# Store original text + optional English companion
uv run openclaw-mem store "偏好：發布前先跑整合測試" \
  --text-en "Preference: run integration tests before release" \
  --lang zh --category preference --importance 0.9 --json

# Build embeddings (original + English)
uv run openclaw-mem embed --field both --limit 500 --json

# Hybrid recall with optional EN assist query
uv run openclaw-mem hybrid "發布前流程" \
  --query-en "pre-release process" \
  --limit 5 --json
```

Design notes:
- `docs/dual-language-memory-strategy.md`

---

## OpenClaw plugin: auto-capture

The plugin lives at `extensions/openclaw-mem`.

Minimal config fragment for `~/.openclaw/openclaw.json`:

```jsonc
{
  "plugins": {
    "entries": {
      "openclaw-mem": {
        "enabled": true,
        "config": {
          "outputPath": "~/.openclaw/memory/openclaw-mem-observations.jsonl",
          "captureMessage": false,
          "redactSensitive": true,
          "backendMode": "auto",
          "annotateMemoryTools": true
        }
      }
    }
  }
}
```

Notes (important):
- The capture hook listens to **tool results**, not raw inbound chat messages.
- `openclaw-mem` plugin is a **sidecar adapter** (capture + annotations), not the canonical memory backend.
- Canonical memory tools depend on your active memory slot backend (e.g., `memory-core` vs `memory-lancedb`).
- For preferences/tasks that must be remembered reliably, use **explicit** writes via CLI (`openclaw-mem store`).

More detail:
- `docs/auto-capture.md`

---

## Deterministic triage (heartbeat-safe)

```bash
# 0: no new issues, 10: attention needed
uv run openclaw-mem triage --mode heartbeat --json
```

This is designed to be safe for heartbeat automation: fast, local, and deterministic.

---

## Obsidian (optional): turn memory into a “second brain”

If you like the "living knowledge graph" workflow (Hub & Spoke, graph view, daily notes), Obsidian is a great human-facing UI on top of the artifacts `openclaw-mem` produces.

- Guide: `docs/obsidian.md`

## Documentation map

- `QUICKSTART.md` — 5-minute setup
- `docs/importance-grading.md` — importance grading schema + heuristic-v1 + tests
- `docs/auto-capture.md` — plugin setup + troubleshooting
- `docs/deployment.md` — timers/permissions/rotation/monitoring
- `docs/privacy-export-rules.md` — export safety rules
- `docs/db-concurrency.md` — WAL + lock guidance
- `docs/dual-language-memory-strategy.md` — current zh/en memory approach
- `docs/rerank-poc-plan.md` — hybrid post-retrieval rerank POC + A/B evaluation plan
- `docs/obsidian.md` — optional Obsidian adoption guide
- `docs/v0.5.9-adapter-spec.md` — minimal-risk adapter design for `memory-core`/`memory-lancedb`
- `docs/ecosystem-fit.md` — ownership boundaries + deployment patterns (`memory-core`/`memory-lancedb` + `openclaw-mem`)
- `CHANGELOG.md` — notable changes (Keep a Changelog)

---

## Acknowledgements

We are heavily inspired by the architecture ideas shared in **`thedotmack/claude-mem`**.
We did **not** borrow code from that project, but we want to properly credit the contribution of publicly sharing a strong memory-layer design for agents.

- See: `ACKNOWLEDGEMENTS.md`

---

## License

Apache-2.0 (`LICENSE`).
