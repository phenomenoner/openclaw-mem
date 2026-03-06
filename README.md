# openclaw-mem

**Local-first memory sidecar + optional hybrid memory engine for OpenClaw agents.**

`openclaw-mem` has two parts:

- **Sidecar (always-on)**: capture + governance + receipts, stored locally in SQLite.
- **Engine (optional)**: `openclaw-mem-engine` — an OpenClaw *memory slot backend* that can do hybrid recall (FTS; BM25-scored + vector) and safe M1 autoRecall/autoCapture.

The sidecar captures useful observations (what tools ran, what happened, what mattered), stores them in a lightweight local SQLite database, and enables **cheap progressive recall** back into the agent:

1) **Search** (compact hits) → 2) **Timeline** (nearby context) → 3) **Get** (full record)

It can run purely as a sidecar (no slot changes), **or** you can switch the OpenClaw memory slot to `openclaw-mem-engine` when you want hybrid recall + controlled automation.

Optional layers add embeddings + hybrid ranking, dual-language fields, gateway-assisted semantic recall, and heartbeat-safe triage.

> Pitch (truthful): if your agent is already doing real work, `openclaw-mem` turns that work into a searchable, auditable memory trail—without requiring an external database.

---

## License

Dual-licensed: **MIT OR Apache-2.0**. See `LICENSE`, `LICENSE-MIT`, and `LICENSE-APACHE`.

## Reality check (verifiable)

See: `docs/reality-check.md` (commands + expected JSON shapes).

```bash
uv sync --locked
DB=/tmp/openclaw-mem.sqlite

uv run --python 3.13 --frozen -- python -m openclaw_mem --db "$DB" --json status
uv run --python 3.13 --frozen -- python -m openclaw_mem --db "$DB" --json ingest --file /tmp/sample.jsonl
uv run --python 3.13 --frozen -- python -m openclaw_mem --db "$DB" --json search "Docs" --limit 5
uv run --python 3.13 --frozen -- python -m openclaw_mem --db "$DB" --json episodes append --scope demo --session-id s1 --agent-id demo --type ops.alert --summary "hello" 
uv run --python 3.13 --frozen -- python -m openclaw_mem --db "$DB" --json episodes query --scope demo --session-id s1
```

Expected output (minimal): `status` prints a JSON object with `count/min_ts/max_ts`, and `ingest` prints `{inserted, ids}`.

## Quick links
- Docs site: https://phenomenoner.github.io/openclaw-mem/
- Releases: https://github.com/phenomenoner/openclaw-mem/releases
- Engine: `docs/mem-engine.md` (what it is + how to enable + knobs)
- Sidecar capture plugin: `docs/auto-capture.md`
- Ecosystem fit / comparisons: `docs/ecosystem-fit.md`

## What’s new (v1.0.4, since v1.0.1)
- **More reliable mem-engine in real chats**: long prompts + embedding hiccups are less likely to break memory flows (fail-open + lexical fallback + warnings).
- **Embedding clamp knobs** (`embedding.maxChars/headChars/maxBytes`) to control how long prompts are trimmed before embedding.
- Release notes: https://github.com/phenomenoner/openclaw-mem/releases/tag/v1.0.4

## Status map (DONE / PARTIAL / ROADMAP)

- **DONE**: local SQLite ledger + FTS5; `ingest/search/timeline/get`; deterministic `triage`; **episodic events ledger** (`episodes append/query/replay/redact/gc`).
- **PARTIAL**: embeddings/hybrid/rerank; AI compression (LLM-assisted, hard caps + rollback; see `docs/ai-compression.md`); dual-language fields.
- **PARTIAL**: OpenClaw plugin capture + backend annotations; Route A semantic recall (`index`, `semantic`).
- **PARTIAL (dev)**: Context Packer (`pack`) with redaction-safe `--trace` receipts (exists, not yet auto-wired; see `docs/automation-status.md`).
- **ROADMAP**: lifecycle manager (ref/last_used_at decay + archive-first); packaging/console scripts; graph semantic memory.
  - Spec (dev): `docs/specs/graphic-memory-graphrag-lite-prd.md`
  - v0 automation knobs (dev): `docs/specs/graphic-memory-auto-capture-auto-recall.md`

---

## What you get (feature map)

### Core (local, deterministic) — **DONE**

- **Observation store**: SQLite + FTS5
- **Progressive disclosure recall**:
  - `search` → `timeline` → `get`
- **Episodic events ledger (v0)**: append-only session timeline
  - `episodes append/query/replay/redact/gc`
  - query is **summary-only by default**; payload opt-in via `--include-payload`
- **Context Packer (dev)**: `pack` builds a compact, cited bundle (summary-only). Use `--no-json` for plain-text payloads, or `--trace --json` for redaction-safe `openclaw-mem.pack.trace.v1` receipts that list refreshed `recordRef`s.
- **Export**: `export` (with safety confirmation)
- **Auto-ingest helper**: `harvest` (ingest + optional embeddings)

### Optional (higher recall quality) — **PARTIAL**

- **Embeddings**: `embed`, `vsearch`
- **Hybrid retrieval**: `hybrid` (lexical FTS (BM25-scored) + vector, **RRF** fusion)
- **Optional post-retrieval rerank (opt-in)** on hybrid path:
  - `--rerank-provider jina|cohere`
  - `--rerank-model ... --rerank-topn ...`
  - fail-open fallback to base RRF ranking on provider/network errors
- **Dual-language memory** (original + optional English companion):
  - `store --text-en ...`
  - dedicated EN embedding table (`observation_embeddings_en`)
  - optional EN assist query route in hybrid (`--query-en`)

### Optional (OpenClaw integration) — **PARTIAL**

- **Auto-capture plugin** (`extensions/openclaw-mem`): writes observation JSONL and (optionally) episodic JSONL (`conversation.user` / `conversation.assistant` / `tool.call` / `tool.result` / `ops.alert`) for ingest.
- **Backend adapter annotations (v0.5.9)**:
  - capture layer remains sidecar-only (no tool registration)
  - records memory backend metadata (`memory-core` / `memory-lancedb`) into `detail_json`
  - tracks memory tool actions (`memory_store` / `memory_recall` / `memory_forget` / `memory_search` / `memory_get`) for audit and monitoring
- **Gateway-assisted semantic recall (Route A)**:
  - `index` (build markdown index)
  - `semantic` (use OpenClaw `memory_search` as a black-box semantic retriever)

### Operational (heartbeat-safe) — **DONE/PARTIAL (first-stable baseline reached)**

Automation truth (dev):
- See `docs/automation-status.md` (what is automatic vs cron vs not yet wired).

- **Deterministic triage (DONE)**: `triage` modes for:
  - `heartbeat`
  - `cron-errors`
  - `tasks`
- `triage --mode tasks` extraction is deterministic:
  - matches `kind == "task"`, or
  - `summary` starts with `TODO` / `TASK` / `REMINDER` (case-insensitive; NFKC width-normalized so full-width forms are accepted), in plain form (`TODO ...`) or bracketed form (`[TODO] ...`, `(TASK) ...`, `【TODO】 ...`, `〔TODO〕 ...`, `<TODO> ...`, `＜TODO＞ ...`), with optional leading markdown wrappers: blockquotes (`>`; spaced `> > ...` and compact `>> ...`/`>>...` forms), list/checklist wrappers (`-` / `*` / `+` / `•` / `‣` / `∙` / `·`, then optional `[ ]` / `[x]` / `[✓]` / `[✔]`), and ordered-list prefixes (`1.` / `1)` / `(1)` / `a.` / `a)` / `(a)` / `iv.` / `iv)` / `(iv)`; Roman forms are canonical). Compact no-space wrapper chaining is also accepted (for example `-TODO ...`, `[x]TODO ...`, `1)TODO ...`, `[TODO]buy milk`, `【TODO】buy milk`, `<TODO>buy milk`, `＜TODO＞buy milk`), followed by `:`, `：`, whitespace, `-`, `－`, `–`, `—`, `−`, or end-of-string.

  - Note: also accepts additional bullet glyphs like ▪ ◦ ・ – — − and checkbox glyphs like [☐]/[☑]/[☒] (see QUICKSTART.md for the full list).
  - Example formats: `TODO: rotate runbook`, `【TODO】 rotate runbook`, `<TODO> rotate runbook`, `＜TODO＞rotate runbook`, `task- check alerts`, `(TASK): review PR`, `- [ ] TODO file patch`, `> TODO follow up with vendor`, `>>[x]TODO: compact wrappers`.
  - Example run:

    ```bash
    uv run --python 3.13 --frozen -- python -m openclaw_mem triage --mode tasks --tasks-since-minutes 1440 --importance-min 0.7 --json
    ```
- Includes dedupe state to avoid repeating the same alert every heartbeat.
- **Ops profile surface (DONE)**: `profile --json` for quick state snapshots (counts, importance labels, top tools/kinds, recent rows, embedding stats).
- **Importance grading (MVP v1 baseline shipped)**: canonical `detail_json.importance` objects + deterministic `heuristic-v1` scorer + regression tests.
  - Enable autograde on `ingest`/`harvest`: `OPENCLAW_MEM_IMPORTANCE_SCORER=heuristic-v1` (or `--importance-scorer {heuristic-v1|off}`)
  - Ingest/harvest JSON receipts include grading counters + `label_counts` for ops trend tracking.
  - Notes: `docs/importance-grading.md`
  - Canonical ingest/harvest receipt contract (aggregate-only): `docs/importance-grading.md`

- **Autograde switch (copy/paste)**:
  ```bash
  # Enable heuristic autograde for ingest/harvest
  OPENCLAW_MEM_IMPORTANCE_SCORER=heuristic-v1 uv run --python 3.13 --frozen -- python -m openclaw_mem harvest --file /tmp/incoming.jsonl --json --no-embed

  # Run a one-off no-autograde harvest (kill-switch)
  OPENCLAW_MEM_IMPORTANCE_SCORER=off uv run --python 3.13 --frozen -- python -m openclaw_mem harvest --file /tmp/incoming.jsonl --json --no-embed

  # Force CLI-only kill switch (per command)
  uv run --python 3.13 --frozen -- python -m openclaw_mem harvest --file /tmp/incoming.jsonl --json --no-embed --importance-scorer off
  ```

- **Lifecycle manager (ROADMAP)**: ref/last_used_at-based decay + archive-first retention.
  - Notes: `docs/notes/lifecycle-ref-decay.md`

### Model/config defaults (centralized; env overrides)
To avoid scattered hardcodes, model/base URL defaults are centralized and can be overridden via env:
- `OPENCLAW_MEM_OPENAI_BASE_URL` (default: `https://api.openai.com/v1`)
- `OPENCLAW_MEM_EMBED_MODEL` (default: `text-embedding-3-small`)
- `OPENCLAW_MEM_SUMMARY_MODEL` (default: `gpt-5.2`)
- `OPENCLAW_MEM_RERANK_MODEL` (default: `jina-reranker-v2-base-multilingual`)

Notes:
- If you switch embedding models, `vsearch` will warn when the requested model has no stored embeddings and will show available model names.

---

## Installation

```bash
git clone https://github.com/phenomenoner/openclaw-mem.git
cd openclaw-mem
uv sync --locked
```

After syncing, run from this source checkout with:
- `uv run --python 3.13 --frozen -- python -m openclaw_mem ...` (recommended)

If you have a packaged install that provides a console script, you can also use:
- `openclaw-mem ...`

---

## 5-minute tour

```bash
# 1) Create/open DB and show counts
uv run --python 3.13 --frozen -- python -m openclaw_mem status --json

# 1.5) Snapshot ops profile (counts, importance labels, top tools, recent rows)
uv run --python 3.13 --frozen -- python -m openclaw_mem profile --json --recent-limit 15

# 1.6) Check active OpenClaw memory backend + fallback posture
uv run --python 3.13 --frozen -- python -m openclaw_mem backend --json

# 2) Ingest JSONL observations
uv run --python 3.13 --frozen -- python -m openclaw_mem ingest --file observations.jsonl --json

# 3) Layer 1 recall (compact)
uv run --python 3.13 --frozen -- python -m openclaw_mem search "gateway timeout" --limit 10 --json

# 4) Layer 2 recall (nearby context)
uv run --python 3.13 --frozen -- python -m openclaw_mem timeline 42 --window 3 --json

# 5) Layer 3 recall (full rows)
uv run --python 3.13 --frozen -- python -m openclaw_mem get 42 --json

# 6) (Dev) Build a compact, cited context bundle
uv run --python 3.13 --frozen -- python -m openclaw_mem pack --query "gateway timeout" --limit 12 --budget-tokens 1200 --trace --json
# With --trace, this returns a redaction-safe `openclaw-mem.pack.trace.v1` receipt plus the packed `bundle_text` and citations.
# `--query-en` can be used when you want an English retrieval lane in addition to the main query.

# 6a) Optional: skip JSON wrapper for pure L1 text payload
uv run --python 3.13 --frozen -- python -m openclaw_mem pack --query "gateway timeout" --no-json
```

### Proactive memory (explicit “remember this”)

```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem store "Prefer tabs over spaces" \
  --category preference --importance 0.9 --json

uv run --python 3.13 --frozen -- python -m openclaw_mem hybrid "tabs or spaces preference" --limit 5 --json
uv run --python 3.13 --frozen -- python -m openclaw_mem hybrid "tabs or spaces preference" \
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
uv run --python 3.13 --frozen -- python -m openclaw_mem store "<original non-English text>" \
  --text-en "Preference: run integration tests before release" \
  --lang zh --category preference --importance 0.9 --json

# Build embeddings (original + English)
uv run --python 3.13 --frozen -- python -m openclaw_mem embed --field both --limit 500 --json

# Hybrid recall with optional EN assist query
uv run --python 3.13 --frozen -- python -m openclaw_mem hybrid "<original query>" \
  --query-en "pre-release process" \
  --limit 5 --json
```

Design notes:
- `docs/dual-language-memory-strategy.md`

---

## OpenClaw plugin: auto-capture (manual vs auto mode)

The plugin lives at `extensions/openclaw-mem`.

### Manual mode (default behavior)

Use CLI directly:

```bash
openclaw-mem episodes append ...
openclaw-mem episodes query ...
openclaw-mem episodes replay <session_id> ...
```

### Auto mode (episodic ledger)

Enable plugin episodic capture + schedule conversation extractor + ingest jobs:

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
          "annotateMemoryTools": true,
          "episodes": {
            "enabled": true,
            "outputPath": "~/.openclaw/memory/openclaw-mem-episodes.jsonl",
            "scope": "global",
            "captureToolCall": true,
            "captureToolResult": true,
            "captureOpsAlert": true,
            "payloadCapBytes": 2048,
            "refsCapBytes": 1024,
            "maxSummaryLength": 220
          }
        }
      }
    }
  }
}
```

Run extractor + ingest every 1–5 minutes:

```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem episodes extract-sessions \
  --sessions-root ~/.openclaw/sessions \
  --file ~/.openclaw/memory/openclaw-mem-episodes.jsonl \
  --state ~/.openclaw/memory/openclaw-mem/episodes-extract-state.json \
  --payload-cap-bytes 4096 \
  --json

uv run --python 3.13 --frozen -- python -m openclaw_mem episodes ingest \
  --file ~/.openclaw/memory/openclaw-mem-episodes.jsonl \
  --state ~/.openclaw/memory/openclaw-mem/episodes-ingest-state.json \
  --conversation-payload-cap-bytes 4096 \
  --json
```

Safety posture:
- summary-first (query/replay payload is opt-in via `--include-payload`)
- secret redaction always on for episodic auto mode
- PII-lite redaction (email/phone) at capture + ingest second-pass
- if secret-like/tool-dump content remains unsafe, ingest stores `payload=null` and `redacted=1`
- conversation payload default 4KB (configurable), ingest hard ceiling 8KB
- no raw stdout/stderr persisted by default

Verification (quick):

```bash
# Run extractor + ingest once
uv run --python 3.13 --frozen -- python -m openclaw_mem episodes extract-sessions --sessions-root ~/.openclaw/sessions --file ~/.openclaw/memory/openclaw-mem-episodes.jsonl --state ~/.openclaw/memory/openclaw-mem/episodes-extract-state.json --json
uv run --python 3.13 --frozen -- python -m openclaw_mem episodes ingest --file ~/.openclaw/memory/openclaw-mem-episodes.jsonl --state ~/.openclaw/memory/openclaw-mem/episodes-ingest-state.json --json

# Summary-only query/replay by default
uv run --python 3.13 --frozen -- python -m openclaw_mem episodes query --global --limit 20 --json
uv run --python 3.13 --frozen -- python -m openclaw_mem episodes replay <session_id> --global --json

# Payload is explicit opt-in
uv run --python 3.13 --frozen -- python -m openclaw_mem episodes replay <session_id> --global --include-payload --json
```

Notes (important):
- If your OpenClaw uses a non-default state dir (e.g. `OPENCLAW_STATE_DIR=/some/dir`), place spool/state files under that directory.
- Scope derivation in auto conversation capture: leading `[SCOPE: x]` tag; otherwise `global`.
- The capture hook is sidecar-only (does not own memory slot backend).
- For explicit durable preference/task memory, continue to use `openclaw-mem store`.

Rollback:
1. set `plugins.entries.openclaw-mem.config.episodes.enabled=false`
2. disable episodic ingest/extractor cron jobs
3. restart OpenClaw gateway

More detail:
- `docs/auto-capture.md`
- `docs/specs/episodic-auto-capture-v0.md`

---

## Deterministic triage (heartbeat-safe)

```bash
# 0: no new issues, 10: attention needed
uv run --python 3.13 --frozen -- python -m openclaw_mem triage --mode heartbeat --json
```

This is designed to be safe for heartbeat automation: fast, local, and deterministic.

---

## Graphic Memory v0 automation knobs (optional, dev)

Graphic Memory automation toggles are opt-in (default OFF):

- `OPENCLAW_MEM_GRAPH_AUTO_RECALL=1` for deterministic preflight recall packs (`graph preflight`)
- `OPENCLAW_MEM_GRAPH_AUTO_CAPTURE=1` for recurring git commit capture (`graph capture-git`)
- `OPENCLAW_MEM_GRAPH_AUTO_CAPTURE_MD=1` for markdown heading indexing (`graph capture-md`)

Inspect effective toggle state:

```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem graph auto-status --json
```

Automation examples:

```bash
OPENCLAW_MEM_GRAPH_AUTO_RECALL=1 uv run --python 3.13 --frozen -- python -m openclaw_mem graph preflight "slow-cook benchmark drift" --scope openclaw-mem --take 12 --budget-tokens 1200

OPENCLAW_MEM_GRAPH_AUTO_CAPTURE=1 uv run --python 3.13 --frozen -- python -m openclaw_mem graph capture-git --repo /root/.openclaw/workspace/openclaw-mem-dev --since 24 --max-commits 50 --json

OPENCLAW_MEM_GRAPH_AUTO_CAPTURE_MD=1 uv run --python 3.13 --frozen -- python -m openclaw_mem graph capture-md --path /root/.openclaw/workspace/lyria-working-ledger --include .md --since-hours 24 --json
```

Design notes: `docs/specs/graphic-memory-auto-capture-auto-recall.md`

## Obsidian (optional): turn memory into a “second brain”

If you like the "living knowledge graph" workflow (Hub & Spoke, graph view, daily notes), Obsidian is a great human-facing UI on top of the artifacts `openclaw-mem` produces.

- Guide: `docs/obsidian.md`

## First-stable release baseline

- **Phase 4 baseline is reached** in the playbook path (progressive recall + hybrid + proactive store + sidecar capture/ops loop).
- Current grooming focus is release hygiene: align docs/changelog and keep benchmark/eval plans explicit before the first stable tag.
- Benchmark pointers:
  - `docs/thought-links.md` (design constraints from references)
  - `docs/rerank-poc-plan.md` (A/B evaluation plan for retrieval quality)

---

## Documentation map

- `QUICKSTART.md` — 5-minute setup
- `docs/reality-check.md` — verifiable commands + feature status (DONE / PARTIAL / ROADMAP)
- `docs/importance-grading.md` — importance grading schema + heuristic-v1 + tests
- `docs/context-engineering-lessons.md` — local-first context engineering patterns (Manus-aligned)
- `docs/roadmap.md` — engineering roadmap (epics + acceptance criteria)
- `docs/auto-capture.md` — plugin setup + troubleshooting
- `docs/deployment.md` — timers/permissions/rotation/monitoring
- `docs/privacy-export-rules.md` — export safety rules
- `docs/db-concurrency.md` — WAL + lock guidance
- `docs/dual-language-memory-strategy.md` — current zh/en memory approach
- `docs/rerank-poc-plan.md` — hybrid post-retrieval rerank POC + A/B evaluation plan
- `docs/obsidian.md` — optional Obsidian adoption guide
- `docs/v0.5.9-adapter-spec.md` — minimal-risk adapter design for `memory-core`/`memory-lancedb`
- `docs/ecosystem-fit.md` — ownership boundaries + deployment patterns (`memory-core`/`memory-lancedb` + `openclaw-mem`)
- `docs/specs/graphic-memory-auto-capture-auto-recall.md` — Graphic Memory auto-recall/auto-capture knobs (dev)
- `docs/specs/episodic-events-ledger-v0.md` — episodic data model + manual APIs
- `docs/specs/episodic-auto-capture-v0.md` — episodic auto-mode (plugin spool + ingest)
- `CHANGELOG.md` — notable changes (Keep a Changelog)

---

## Acknowledgements

We are heavily inspired by the architecture ideas shared in **`thedotmack/claude-mem`**.
We did **not** borrow code from that project, but we want to properly credit the contribution of publicly sharing a strong memory-layer design for agents.

- See: `ACKNOWLEDGEMENTS.md`

---
