# OpenClaw Mem Engine (slot backend) — Design + Roadmap

> Working name: **openclaw-mem-engine**
>
> Scope: an **optional** OpenClaw *memory slot backend plugin* shipped alongside `openclaw-mem`.

## TL;DR (big picture)

`openclaw-mem` stays the **sidecar** (capture, governance, observability, grading, receipts).

`openclaw-mem-engine` becomes an optional **slot owner** (replaces `memory-lancedb` when enabled) so we can:

- do **hybrid recall** (FTS/BM25 + vector) with **scopes & metadata filters**,
- make recall behavior **auditable + tunable** (receipts, knobs, policies),
- and actually exploit LanceDB features that the official `memory-lancedb` backend doesn’t surface.

Rollback remains trivial: switch `plugins.slots.memory` back to `memory-lancedb` or `memory-core`.

---

## Why we’re doing this

Observed gap:

- The official `memory-lancedb` plugin uses LanceDB mostly as a basic vector store (`vectorSearch`) and does not expose:
  - full-text (BM25) search,
  - hybrid fusion/rerank,
  - scope-aware metadata filtering + scalar indexes,
  - index lifecycle/optimize,
  - version tags / easy rollback.

Operator goal (what CK cares about):

- **“Concept/goal → the right decisions/preferences/projects”** should be reliably retrievable.
- Retrieval must be **controllable** (scope, importance, recency) and **explainable** (why these results).

---

## Product shape (two planes)

### Plane A — Mem Ops (sidecar, always-on)

Owned by `openclaw-mem`:

- capture (tool outcomes, optional message events)
- ingestion into SQLite ledger
- importance grading + drift detection
- provenance / trust tiers
- receipts & dashboards
- (future) context packing / graph view

### Plane B — Mem Engine (slot backend, optional)

Owned by `openclaw-mem-engine`:

- implements OpenClaw canonical memory tools for the active slot:
  - `memory_store`
  - `memory_recall`
  - `memory_forget`
  - (optional) `memory_stats` / `memory_count`

- uses LanceDB as the online store for fast retrieval & hybrid search.

Key stance: **sidecar governs; engine serves**.

---

## Architecture overview

```text
                     +------------------------------+
                     |  OpenClaw Agent / Sessions   |
                     +---------------+--------------+
                                     |
                                     | memory_store / memory_recall
                                     v
                     +------------------------------+
                     |   openclaw-mem-engine slot   |
                     |   (LanceDB hybrid backend)   |
                     +---------------+--------------+
                                     |
                                     | reads/writes
                                     v
                     +------------------------------+
                     | LanceDB table: memories      |
                     |  - vector + FTS + metadata   |
                     +---------------+--------------+
                                     ^
                                     |
                writeback annotations|  (importance/trust/provenance)
                                     |
                     +---------------+--------------+
                     | openclaw-mem (sidecar ops)   |
                     |  - capture JSONL             |
                     |  - ingest SQLite             |
                     |  - grade importance          |
                     |  - receipts & drift checks   |
                     +------------------------------+
```

> Decision (confirmed): **LanceDB is the source of truth for the engine path**.
> Sidecar may maintain its SQLite ledger for auditability and long-horizon analysis.

---

## Data model (what we store)

Minimum viable schema for LanceDB `memories` table:

- `id` (uuid)
- `text` (string)
- `vector` (float[]) — embedding of `text` (or of a normalized form)
- `createdAt` (ms)

Governance metadata (needed for “concept→right stuff”):

- `category` (`preference|decision|fact|entity|other`)
- `importance` (0..1)
- `importance_label` (`must_remember|nice_to_have|ignore|unknown`)
- `scope` (string; e.g. `openclaw-mem`, `finlife`, `personal`, …)
- `trust_tier` (`trusted|untrusted|quarantined`)
- `source_kind` (`operator|tool|web|import|system`)
- `source_ref` (optional; tool name, URL, transcript id, etc.)
- `lang` (optional; `zh|en|…`)

Notes:

- “importance unknown” stays **fail-open**: we don’t auto-filter unknown unless an explicit query policy requests it.
- Keep schema additive: new columns should be optional and backfillable.

---

## Retrieval design (the part you’ll feel)

### Query pipeline

1) **Parse intent**
   - detect optional scope hints (explicit param, or inferred from tags)
   - choose policy defaults (limit, min score, recency window)

2) **Hybrid retrieval**
   - **FTS/BM25** path: exact-ish keyword matching for names/paths/ids
   - **Vector** path: semantic similarity
   - Fuse results with a deterministic strategy (e.g., RRF), optionally rerank.

3) **Metadata filtering** (before or during query)
   - `scope` filter (most important)
   - `importance_label` filter (e.g., prefer must/nice)
   - recency bias (soft)
   - trust gating (prefer trusted; allow untrusted when recall would be empty)

4) **Return**
   - bounded list (K)
   - include lightweight explanations: score components + why it passed filters

### Why hybrid is MVP-critical

- Pure vector fails on:
  - paths, error codes, commit hashes
  - short identifiers
  - partial quotes
- Pure FTS fails on:
  - paraphrases / concept-level asks

Hybrid is the minimum that makes “concept→decisions/preferences” feel reliable.

---

## Write path + governance writeback

### `memory_store`

- Engine writes the primary record to LanceDB.
- Sidecar may later write back computed governance fields:
  - `importance` / `importance_label`
  - `trust_tier`
  - additional provenance

### Importance grading integration

- The **heuristic-v1** scorer (and later scorers) live in the sidecar.
- Engine uses the graded fields for filtering defaults.

---

## Indexing & performance (making LanceDB “actually fast”)

We should treat index lifecycle as an operator concern with receipts.

- Build indices:
  - vector index (`createIndex("vector", …)`)
  - FTS index on `text`
  - scalar indices on `scope`, `importance_label`, `category`, maybe `createdAt`

- Maintenance:
  - run `optimize()` periodically (or on thresholds)
  - expose “index status” in JSON receipts

---

## Roadmap (detailed early milestones, coarse later)

### M0 — Engine skeleton (slot switch + basic tools)

Goal: *we can replace the slot without breaking workflows*.

Deliverables:

- New OpenClaw extension/plugin: `openclaw-mem-engine`
- Config switch:
  - `plugins.slots.memory = "openclaw-mem-engine"`
  - rollback: switch back to `memory-lancedb` / `memory-core`
- Tools implemented:
  - `memory_store(text, importance?, category?, scope?, …)`
  - `memory_recall(query, limit?, scope?, …)`
  - `memory_forget(id)`
- JSON receipts for every tool call (at least: counts, filters applied, latency ms)

Definition of done:

- Smoke test:
  - store → recall → forget works end-to-end
  - empty recall returns empty (no errors)
- Fail-open behavior:
  - embedding provider errors do not crash the agent loop (tool returns a compact error + suggestion)

### M1 — Hybrid + scopes MVP (the “you will feel it” milestone)

Goal: make concept/goal queries consistently pull the right decisions/preferences.

Deliverables:

- FTS index on `text` + vector search on `vector`
- Hybrid fusion (deterministic; RRF baseline)
- Metadata filters:
  - `scope` (hard)
  - `importance_label` (soft default: prefer must/nice)
  - `trust_tier` (soft default: prefer trusted)
- Basic scalar indexes for filter columns
- Eval harness (offline):
  - a small golden set of queries → expected memory ids/texts
  - measures: hit@k, qualitative “wrong-scope” rate, latency

Definition of done:

- For a golden set of “concept→decision/preference” queries, hybrid beats vector-only baseline.
- Query results show scope & importance in the returned payload (auditable).

### M1.5 — Retrieval quality layer (optional, fail-open)

Goal: raise precision on long/ambiguous queries **without** making ops brittle.

Inspiration (external): `win4r/memory-lancedb-pro`.

Deliverables:

- Optional **cross-encoder rerank** (e.g., Jina or any OpenAI-compatible rerank endpoint)
  - strict timeout (e.g., 3–5s)
  - **fail-open** fallback: keep fused order if reranker fails
- Optional scoring refinements (cheap, deterministic):
  - recency boost / time decay
  - length normalization (avoid long entries dominating)
  - hard minimum score threshold
- Optional **diversity** (MMR-style) to reduce near-duplicate hits
- Optional **adaptive retrieval** heuristic (skip memory lookup for greetings/acks/emoji; force for “remember/previously/decision” intents)
- Receipts:
  - show which stages ran (fts/vector/fuse/rerank/diversify)
  - include rerank provider + fallback reason when applicable

Definition of done:

- Every optional layer is gated by config and can be turned off with a single change.
- With all optional layers OFF, M1 behavior remains unchanged.
- With layers ON, golden-set precision improves measurably (and latency stays within a defined budget).

### M1.6 — Lifecycle hooks + management surface (optional)

Goal: match the “it just works” feel of a full memory backend **without** collapsing our split (sidecar governs; engine serves).

Inspiration (external): `win4r/memory-lancedb-pro`.

Deliverables:

- **Auto-recall hook** (`before_agent_start`):
  - run retrieval only when `adaptive_retrieval` says it’s worth it
  - inject a bounded block (top-K) with an explicit marker (so capture can ignore it)
  - include lightweight receipts (count + scope/trust filters)
- **Auto-capture hook** (if we add it at all):
  - default OFF; must be deduped + fail-open
  - recommended posture: keep durable capture in the sidecar; engine hook only forwards *candidates*
- **Management CLI / tools** (operator loop):
  - `memory_stats` (counts, label dist, scopes, recent)
  - `memory_list` (paged)
  - `export/import` (JSONL)
  - `reembed` (batch) with receipts + rate limits
  - `migrate` helpers (from built-in `memory-lancedb` table)

Definition of done:

- Hooks are **toggleable** and safe-by-default (OFF unless explicitly enabled).
- Injected context is clearly marked and can be excluded from capture (anti-echo).
- Management operations emit trend-friendly receipts and never dump secrets.

### M2 — Ops hardening (index lifecycle + optimize + drift)

Deliverables (coarse):

- scheduled `optimize` with receipts
- index existence + health checks
- drift dashboard: label distribution + “unknown” %

### M3 — Versioning safety net (tags + rollback)

Deliverables (coarse):

- tag versions before large auto-capture or regrading changes
- ability to revert/checkout a tagged version

### M4 — Multimodal (optional)

Deliverables (coarse):

- add `media_refs` + `media_kind` metadata
- define embedding strategy per modality

---

## Risks & mitigations

- **Complexity creep**: keep engine MVP small; push governance logic into sidecar.
- **Recall noise**: default to scope-aware retrieval; only broaden when empty.
- **Migration risk**: slot switch rollback is the safety valve; keep it one-line.
- **Native deps**: LanceDB has native bindings; pin versions and test on target OS/arch.

---

## Open questions (to settle while implementing M0/M1)

1) Scope source-of-truth:
   - explicit tool params vs inferred from chat tags vs both
2) How we expose explanations without bloating context
3) Default trust policy when everything is untrusted
4) Storage path + backup policy for LanceDB data
