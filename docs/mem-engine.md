# OpenClaw Mem Engine (slot backend) — Design + Roadmap

> Working name: **openclaw-mem-engine**
>
> Scope: an **optional** OpenClaw *memory slot backend plugin* shipped alongside `openclaw-mem`.

## TL;DR (big picture)

`openclaw-mem` stays the **sidecar** (capture, governance, observability, grading, receipts).

`openclaw-mem-engine` becomes an optional **slot owner** (replaces `memory-lancedb` when enabled) so we can:

- do **hybrid recall** (FTS + vector) with **scopes & metadata filters**,
- make recall behavior **auditable + tunable** (receipts, knobs, policies),
- add **safe M1 automation**: conservative `autoRecall` + strict `autoCapture` (configurable),
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
- exposes operator/admin tools for parity workflows:
  - `memory_list`
  - `memory_stats`
  - `memory_export`
  - `memory_import`
- CLI compatibility layer:
  - `openclaw memory list|stats|export|import` (when plugin CLI wiring is available)
  - fallback: `openclaw ltm list|stats|export|import`

- uses LanceDB as the online store for fast retrieval & hybrid search.

Key stance: **sidecar governs; engine serves**.

---

## M1 automation (what is safe to ship now)

### autoRecall (conservative)
- Hook: `before_agent_start`
- Default: **on** (but gated by heuristics)
- Behavior:
  - skip trivial prompts (greetings/emojis/HEARTBEAT/slash commands)
  - recall tiers: `must_remember` → `nice_to_have` → (optional) `unknown` fallback
  - cap: <=5 memories
  - escapes memory text to reduce prompt-injection risk

### autoCapture (strict)
- Hook: `agent_end`
- Default: **on** (but strict allowlist)
- Behavior:
  - capture only a small number of items (1–3 per turn)
  - default categories: `preference`, `decision`
  - skip tool outputs; prefer user text; skip secrets-like strings
  - dedupe near-identical items

### Rollback
One line:
- set `plugins.slots.memory` back to `memory-lancedb` (or `memory-core`) and restart gateway.

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
   - `importance_label` filter (default policy): prefer `must_remember + nice_to_have`, then fallback to `unknown`, then `ignore` if still empty.
   - recency bias (soft)
   - trust gating (prefer trusted; allow untrusted when recall would be empty)

4) **Return**
   - bounded list (K)
   - include lightweight explanations: score components + why it passed filters
   - return **structured JSON objects** with stable ids + governance metadata so a packer can wrap results into an injection-ready ContextPack (see `docs/context-pack.md`)

### Why hybrid is MVP-critical

- Pure vector fails on:
  - paths, error codes, commit hashes
  - short identifiers
  - partial quotes
- Pure FTS fails on:
  - paraphrases / concept-level asks

Hybrid is the minimum that makes “concept→decisions/preferences” feel reliable.

### Docs memory (decisions/roadmaps/specs) as a cold lane

Operators feel recall failure most painfully on: “we already decided this.”

So the engine path should be able to **optionally** search an operator-authored docs corpus (DECISIONS / roadmaps / specs) using the same hybrid recipe (FTS + embeddings) and return bounded citations.

- Spec: [Docs memory (hybrid search v0) →](specs/docs-memory-hybrid-search-v0.md)
- Stance: **no local LLM**; rerank (if needed) is remote + bounded.

---

## Write path + governance writeback

### `memory_store`

- Engine writes the primary record to LanceDB.
- Sidecar may later write back computed governance fields:
  - `importance` / `importance_label`
  - `scope`
  - `trust_tier`
  - `category`
  - additional provenance
- Command used for writeback: `openclaw-mem writeback-lancedb --db <sqlite> --lancedb <path> --table <name> [--limit N] [--batch N] [--dry-run] [--force] [--force-fields <fields>]`
  - `--force`/`--overwrite` (default off): allow overwriting existing values when incoming values are present.
  - `--force-fields` (comma-separated): restrict overwrite to selected fields (default safe subset: `importance,importance_label,scope,category`; `trust_tier` must be explicit).
- Writeback receipts should report: `forceOverwrite`, `forceFields`, `updated`, `skipped`, `overwritten`, `overwrittenFields`, and missing IDs.

### Importance grading integration

- The **heuristic-v1** scorer (and later scorers) live in the sidecar.
- `memory_recall` defaults to must+nice (`must_remember` + `nice_to_have`), then fail-open includes `unknown`, then `ignore`.
- Engine uses graded fields for filtering defaults and includes `policyTier` in recall receipts.

---

## Sunrise rollout (slow-cook lane + cron “日出條款”)

We roll this out in **three stages** to keep the system safe and rollbackable.

- **Stage A (background, 0-risk)**: keep `plugins.slots.memory` on `memory-lancedb`.
  - Run periodic **writeback** from sidecar SQLite → LanceDB (metadata governance).
  - Silent-on-success; only notify on anomalies (errors/missing IDs).

- **Stage B (canary, short window)**: off-peak *temporary* slot switch.
  - Backup config → switch slot to `openclaw-mem-engine` → run a small golden-set recall check → rollback.
  - Goal: prove `policyTier` + `ftsTop/vecTop` behave as expected under real traffic.

- **Stage C (live)**: switch default slot to `openclaw-mem-engine`.
  - Keep an auto-downgrade path (switch back to `memory-lancedb`) if recall error-rate/latency spikes.

Recommended cron alignment (Asia/Taipei):
- Importance grading slow-cook runs `0 */4 * * *`.
- Stage A writeback runs at **`20 */4 * * *`** (20 minutes after) to avoid overlap.

## Indexing & performance (making LanceDB “actually fast”)

We should treat index lifecycle as an operator concern with receipts.

- Build indices:
  - vector index (`createIndex("vector", …)`)
  - FTS index on `text`
  - scalar indices on `scope`, `importance_label`, `category`, maybe `createdAt`

- Maintenance:
  - run `optimize()` periodically (or on thresholds)
  - expose “index status” in JSON receipts

## Admin ops (P0-1 shipped)

Admin surfaces are now implemented in the engine path with receipts:

- list: filter by `scope` / `category`, bounded by `limit`
- stats: counts by scope/category + size/age summaries
- export: deterministic ordering + default text redaction
- import: append mode + dedupe (`none|id|id_text`) + dry-run validation

Each operation emits receipt/debug fields including:

- applied filters
- returned/imported counts
- backend context (`dbPath`, `tableName`, latency)

See [Engine admin ops (P0-1)](mem-engine-admin-ops.md) for examples.

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
- `memory_recall` receipts now include compact `ftsTop` / `vecTop` arrays (top candidate hits from each channel before fusion) for audit/debugging.

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

### M1.5 — Sidecar writeback + policy-tiered recall defaults

Goal: close the loop between graded SQLite ledger artifacts and runtime recall behavior.

Deliverables:

- Sidecar command for bounded, dry-run safe metadata writeback into LanceDB:
  - `openclaw-mem writeback-lancedb --db <sqlite> --lancedb <path> --table <name> [--limit N] [--batch N] [--dry-run] [--force] [--force-fields <fields>]`
  - fields: `importance`, `importance_label`, `scope`, `trust_tier` (if available), `category`
- `memory_recall` default policy sequence:
  1. `must_remember + nice_to_have`
  2. fallback `unknown`
  3. fallback `ignore`
- Recall receipts include which policy tier was selected (e.g., `must+nice`, `must+nice+unknown`, `must+nice+unknown+ignore`).

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
