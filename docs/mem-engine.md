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
- expose **Proactive Pack** as the public-facing name for bounded pre-reply recall orchestration,
- and actually exploit LanceDB features that the official `memory-lancedb` backend doesn’t surface.

Rollback remains trivial: switch `plugins.slots.memory` back to `memory-lancedb` or `memory-core`.

---

## Why we’re doing this

Observed gap:

- The official `memory-lancedb` plugin uses LanceDB mostly as a basic vector store (`vectorSearch`) and does not expose:
  - full-text search (FTS; BM25 scoring),
  - hybrid fusion/rerank,
  - scope-aware metadata filtering + scalar indexes,
  - index lifecycle/optimize,
  - version tags / easy rollback.

Operator goal (what most users care about):

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

Public-facing framing: when mem-engine injects a bounded recall block during prompt build, treat that surface as **Proactive Pack**, not as a separate hidden memory product.

### Single-write-path posture (important)

When `openclaw-mem-engine` owns `plugins.slots.memory`, treat it as the **only canonical durable-memory write path**.

That means:

- `memory_store` / `memory_forget` / `memory_import` / `memory_docs_ingest` authority lives in the engine lane
- the sidecar remains capture, receipts, governance, and recall support
- graph/docs/synthesis lanes may improve recall or packing, but they do **not** become competing durable-memory writers
- in short, helper lanes do not become competing durable-memory writers
- if `gbrainMirror` is enabled, it is a **write-through mirror / retrieval substrate**, not a second truth owner

Related experimental lane:
- the separate **GBrain sidecar** doc covers read-only GBrain lookup, a restricted helper-job bridge, and a gated refresh canary
- that surface is still experimental and **not enabled by default**
- see [`docs/experimental/gbrain-sidecar/README.md`](experimental/gbrain-sidecar/README.md)

If you need watchdog or advisory-only execution, set `readOnly: true` (or `OPENCLAW_MEM_ENGINE_READONLY=1`).
That forces write-path rejection and disables `autoCapture`, which keeps the ownership boundary honest.

Related boundary: the shipped **verbatim semantic lane** remains a **sidecar retrieval surface** over episodic evidence (`episodes embed` / `episodes search --mode ...`). It is not a new slot-backend memory type and does not change durable-memory write discipline.

---

## M1 automation (what is safe to ship now)

### Proactive Pack (`autoRecall`, conservative)
- Hook: `before_prompt_build` on current OpenClaw, with `before_agent_start` retained as a legacy fallback
- Default: **on** (but gated by heuristics)
- Behavior:
  - optional `autoRecall.routeAuto` hook calls `openclaw-mem route auto --compact` before normal recall and injects a compact synthesis-aware routing hint block
  - dual registration is deduped by run/session key so sequential `before_prompt_build` then legacy `before_agent_start` does not double-inject
  - when route-auto carries `preferredCardRefs` / `coveredRawRefs`, the hook prefers the fresh synthesis card but keeps the covered-raw receipt visible
  - route hook is recommendation-only and fail-open (timeout/runtime failure does not block the turn)
  - skip trivial prompts (greetings/ack/emojis/HEARTBEAT/slash commands)
    - robust to trailing emoji/punctuation (e.g. `ok👍`, `done!!`, `thanks...`)
    - punctuation-only prompts also skip (e.g. `？`, `…`)
  - recall tiers: `must_remember` → `nice_to_have` → (optional) `unknown` fallback
  - cap: <=6 memories
  - escapes memory text to reduce prompt-injection risk
  - emits bounded lifecycle receipt (`openclaw-mem-engine.recall.receipt.v1`) with skip reason / tier counts / top IDs
  - in `receipts.verbosity=high`, injects a compact autoRecall wrapper comment (IDs only; no memory text in receipt)
    - default `low` keeps receipts in logs only (no prompt-side comment)
  - project/repo action guardrail: for ambiguous project references, run the deterministic routing resolver before file-changing work:
    - `openclaw-mem routing resolve "<project task>" --workspace-root <workspace> --json`
    - `openclaw-mem routing eval --probes docs/fixtures/routing-probes.sample.json --workspace-root <workspace> --json`
    - resolver output is advisory and fail-open: `resolved` may proceed after operator review; `ambiguous`, `low_confidence`, or `unresolved` should trigger a clarification or a narrower project map

Boundary rule:
- this is a **Pack runtime mode** that assembles a small pre-reply bundle
- it does **not** create a second durable-memory truth owner
- it should stay bounded by scope policy, receipts, and final context budget

### autoCapture (strict)
- Hook: `agent_end`
- Default: **on** (but strict allowlist)
- Behavior:
  - capture only a small number of items (1–4 per turn)
  - default categories: `preference`, `decision`
  - skip tool outputs; prefer user text; skip secrets-like strings
  - dedupe near-identical items
  - emits bounded lifecycle receipt (`openclaw-mem-engine.autoCapture.receipt.v1`) with extracted/filtered/stored counts

### Rollback
One line:
- set `plugins.slots.memory` back to `memory-lancedb` (or `memory-core`) and restart gateway.

### Governance note (post-Dream-Lite)
Read-only maintenance and recall helpers may surface recommendation packets, but recommendation judgment and any future autonomous-write authority should remain in an explicit governor lane rather than helper/scout lanes.
See: `docs/specs/governed-dreaming-suggestion-write-authority-v0.md`.

### Apply-readiness note
Even after `governor-review`, real mutation should stay behind a separate canary apply contract.
The first acceptable apply-readiness cut is refresh-only, dry-run first, receipt-heavy, and rollbackable.
See: `docs/specs/compiled-synthesis-assist-apply-canary-v0.md`.

### Receipt controls (P0-2)
- `receipts.enabled` (default `true`)
- `receipts.verbosity` (`low` default, `high` optional)
- `receipts.maxItems` (default `3`, hard cap `10`)

Design constraints:
- receipts are bounded/deterministic by default
- no memory text is emitted in receipt payloads by default (IDs + scores only)
- operator-legible explainability is first-class (`whySummary`, `whyTheseIds`, fallback suppression reason)

### Scope policy + context budget knobs (Rollout Step 1/2)

`openclaw-mem-engine` now exposes two rollbackable control planes:

1) **Scope policy** (default-on namespace isolation)
- `scopePolicy.enabled` (default `true`; kill-switch)
- `scopePolicy.defaultScope` (default `"global"`)
- `scopePolicy.fallbackScopes` (default `[]`; ordered allowlist, only consulted if primary scope is insufficient)
- `scopePolicy.fallbackMarker` (default `true`; emit observable fallback marker in logs/receipts)
- `scopePolicy.skipFallbackOnInvalidScope` (default `true`; invalid strict scope tags suppress fallback scopes)
- `scopePolicy.validationMode` (`strict` default; `normalize` / `none` optional)
- `scopePolicy.maxScopeLength` (default `64`)

Write-path hardening:
- scope values are validated/normalized at write-time (`memory_store`, `autoCapture`, `memory_import`)
- invalid strict scopes fall back to `defaultScope` and emit a scope-validation warning receipt/log marker

2) **Final prepend context budget** (hard ceiling at packing tail)
- `budget.enabled` (default `true`; kill-switch)
- `budget.maxChars` (default `1800`)
- `budget.minRecentSlots` (default `1`)
- `budget.overflowAction` (`truncate_oldest` default; `truncate_tail` optional)

Packing semantics:
- budget is enforced at the **very end** of autoRecall packing (`prependContext`) independent of `maxItems`
- if overflow occurs:
  - `truncate_oldest`: drop **oldest-by-createdAt** slots first, while protecting the `minRecentSlots` most-recent slots
  - `truncate_tail`: drop from the **tail of the selected/relevance-ordered list** first (least relevant), still protecting `minRecentSlots`
- if still above cap (e.g. receiptComment itself is large), final tail slicing is applied to guarantee a deterministic hard ceiling
- when truncation happens and `budget.enabled=true`, emit `openclaw-mem-engine:contextBudget` marker (before/after chars + dropped ids/count)

Example config snippet:

```jsonc
{
  "plugins": {
    "entries": {
      "openclaw-mem-engine": {
        "enabled": true,
        "config": {
          "scopePolicy": {
            "enabled": true,
            "defaultScope": "global",
            "fallbackScopes": ["openclaw-mem", "personal"],
            "fallbackMarker": true,
            "skipFallbackOnInvalidScope": true,
            "validationMode": "strict",
            "maxScopeLength": 64
          },
          "budget": {
            "enabled": true,
            "maxChars": 1800,
            "minRecentSlots": 1,
            "overflowAction": "truncate_oldest"
          }
        }
      }
    }
  }
}
```

Rollback (single-line posture):
- disable either feature without code changes:
  - `scopePolicy.enabled = false`
  - `budget.enabled = false`

### Rollout Step 3 — guarded TODO capture (default off)

Step 3 keeps the default behavior unchanged (`autoCapture.captureTodo = false`) and adds explicit TODO guardrails that can be enabled/rolled back via config only.

New knobs under `autoCapture`:
- `captureTodo` (default `false`)
- `maxTodoPerTurn` (default `1`, min `0`, max `3`)
- `todoDedupeWindowHours` (default `24`, min `1`, max `168`)
- `todoStaleTtlDays` (default `7`, min `1`, max `90`)

Guardrail behavior when `captureTodo=true`:
- TODO capture is capped by `maxTodoPerTurn` per agent turn.
- TODO dedupe is **scope-scoped + time-bounded**: only same-scope TODOs within `todoDedupeWindowHours` are considered duplicates.
- TODO injection obeys a deterministic recall-time TTL: TODO memories older than `todoStaleTtlDays` are dropped from autoRecall injection.
- Drops emit bounded markers/receipts (`openclaw-mem-engine:todoGuardrail`, plus `autoCapture` receipt counters).

Operational note (Telegram / injected metadata):
- Some deployments include autoRecall receipts (e.g. `<relevant-memories>…</relevant-memories>`) and code-fenced metadata blocks in the *same* inbound message.
- autoCapture strips these injected artifacts before candidate extraction, and filters tool-like content **per candidate line**, so a real user TODO line (e.g. `TODO: …`) can still be captured.
- Scope tags can be on the same line or on the previous line:
  - `TODO: ...` preceded by `[SCOPE: openclaw-mem]` on its own line is still captured into that scope.
- Keep TODO lines outside code fences for best results.

Recommended enable snippet (Step 3):

```jsonc
{
  "plugins": {
    "entries": {
      "openclaw-mem-engine": {
        "enabled": true,
        "config": {
          "autoCapture": {
            "enabled": true,
            "captureTodo": true,
            "maxTodoPerTurn": 1,
            "todoDedupeWindowHours": 24,
            "todoStaleTtlDays": 7
          },
          "budget": {
            "enabled": true,
            "maxChars": 1800,
            "minRecentSlots": 1,
            "overflowAction": "truncate_oldest"
          }
        }
      }
    }
  }
}
```

Rollback:
- immediate kill switch: `autoCapture.captureTodo = false`

### Rollout Step 4 — deterministic Working Set (canary-gated, frozen)

Step 4 is wired into the prompt-mutation path (`before_prompt_build` primary, `before_agent_start` fallback) behind a rollbackable config gate:
- `workingSet.enabled` (default `false`)
- `workingSet.persist` (default `true`)
- `workingSet.maxChars` / `maxItemsPerSection` / `maxGoalChars` / `maxItemChars`

Current status: **frozen / default-off**. A/B review found no measured reply-quality lift over baseline recall, so Working Set should not be enabled by default or promoted on context-cost reduction alone.

Behavior when enabled:
- synthesize a compact per-scope working state blob from selected scoped memories
  - constraints / decisions / next_actions / open_questions
- suppress raw recall hits already represented in the Working Set
- pin Working Set as the first injected slot before remaining recall results
- optional upsert persistence with deterministic ID `working_set:<scope>`

Receipts:
- recall lifecycle includes optional `workingSet` summary (`generated`, `id`, `chars`, section counts, `consumedCount`, `suppressedRecallCount`, `persisted`)

Rollback:
- `workingSet.enabled = false`

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
   - **FTS (BM25-scored)** path: exact-ish keyword matching for names/paths/ids
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

Status (current):
- shipped as `docsColdLane` in `openclaw-mem-engine` config
- installable tools: `memory_docs_ingest`, `memory_docs_search`
- `memory_recall` + `autoRecall` can consult cold lane only after hot lane is insufficient (`minHotItems`)
- results are marked `source_kind=operator`, `trust_tier=trusted`
- embeddings are optional/fail-open (FTS-only still works)

- Spec: Docs memory hybrid search v0 (maintainer archive; not part of the public evaluator path)
- Ops guide: [mem-engine-admin-ops.md](mem-engine-admin-ops.md#docs-memory-cold-lane-installable)
- Operational hardening note: scoped docs search starvation root cause and verifier (maintainer archive)
- Next design slice: docs cold lane scope pushdown v1 (maintainer archive)
- Stance: **no local LLM**; rerank (if needed) is remote + bounded.

---

## Embeddings hardening (clamp + fail-open)

Embeddings providers enforce an input limit (often expressed as a **max token** count).
If an agent passes a very long string into `memory_store`/`memory_recall`, the provider can return a 400 ("input too long").

`openclaw-mem-engine` hardens this by:
- **clamping** embedding inputs deterministically (head+tail) *before* calling the provider
- **failing open** when embeddings are unavailable/over-limit (tools keep working; results may degrade)

Config knobs (OpenClaw config paths):
- `plugins.entries.openclaw-mem-engine.config.embedding.maxChars` (default: `6000`)
- `plugins.entries.openclaw-mem-engine.config.embedding.headChars` (default: `500`)
- `plugins.entries.openclaw-mem-engine.config.embedding.maxBytes` (optional; UTF-8 cap)

Example (pin defaults explicitly):
```bash
openclaw config set plugins.entries.openclaw-mem-engine.config.embedding.maxChars 6000
openclaw config set plugins.entries.openclaw-mem-engine.config.embedding.headChars 500
# optional extra safety
openclaw config set plugins.entries.openclaw-mem-engine.config.embedding.maxBytes 24000
```

Receipt visibility:
- `memory_store` receipts include: `embeddingSkipped` + `embeddingSkipReason`
- `memory_recall` receipts include skip reasons (e.g. `embedding_input_too_long`) when vector embedding is skipped

Fail-open UX:
- If embeddings are unavailable/over-limit, `memory_recall` will **still return lexical-only (FTS) results** and prepend a ⚠️ warning.
- If embedding is skipped during `memory_store`, the tool still stores the record (zero vector fallback) and returns a ⚠️ warning.

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

#### Governance memory preflight (optional, now hookable)

`openclaw-mem-engine` can now call an operator-configured governance preflight automatically **before** `memory_store` writes.

Purpose:
- move governance to the dangerous moment right before memory becomes system truth
- reduce operator memory burden (the flow asks the governance preflight first)
- keep the lane rollbackable and bounded

Config gate:
- `plugins.entries.openclaw-mem-engine.config.memoryPreflight`

Recommended host posture:
- `enabled: true`
- `failMode: "open"`
- `failOnQueued: false`
- `failOnRejected: false`

That gives an **advisory-first** live lane:
- governance preflight runs automatically
- runtime failure does not brick memory writes
- receipts still expose the preflight verdict

Receipts surface:
- `memory_store.details.receipt.memoryPreflight`
- blocked receipts should carry preflight trace metadata plus the engine `intent_id`, so operator approval reuse can retry the same governed memory intent instead of spawning opaque duplicate review items

Blocking modes:
- `failMode: "closed"` blocks on runtime/subprocess failure
- `failOnQueued: true` blocks if the preflight queues review
- `failOnRejected: true` blocks if the preflight rejects

Rollback:
- disable the config gate, then restart the gateway

#### GBrain write-through mirror (optional)

`openclaw-mem-engine` can also mirror each successful `memory_store` into a dedicated `gbrain` import root.

Purpose:
- let `gbrain` receive a live twin of canonical memory writes
- remove the need for periodic full impose/import just to expose new memories to `gbrain`
- keep ownership clean: engine remains writer-of-record, `gbrain` stays a retrieval substrate

Config gate:
- `plugins.entries.openclaw-mem-engine.config.gbrainMirror`

Recommended host posture:
- `enabled: true`
- `mirrorRoot: "~/.openclaw/memory/gbrain-mirror"`
- `importOnStore: true`
- `timeoutMs: 12000`

Behavior:
- engine stores the canonical row in LanceDB
- plugin writes `mirrorRoot/<memory-id>.md`
- plugin runs `gbrain import <mirrorRoot> --workers 1`
- plugin forwards `OPENAI_API_KEY` from the engine lane into the gbrain subprocess so embeddings do not fail only because the key lived in plugin config
- mirror/import failures are fail-open for canonical memory writes, but they are visible in receipts

Receipts surface:
- `memory_store.details.receipt.gbrainMirror`

Rollback:
- disable the config gate, then restart the gateway

### Importance grading integration

- The **heuristic-v1** scorer (and later scorers) live in the sidecar.
- `memory_recall` defaults to must+nice (`must_remember` + `nice_to_have`), then fail-open includes `unknown`, then `ignore`.
- Engine uses graded fields for filtering defaults and includes `policyTier` in recall receipts.

---

## Sunrise rollout (slow-cook lane + cron safeguard)

We roll this out in **three stages** to keep the system safe and rollbackable.

- **Stage A (background, 0-risk)**: keep `plugins.slots.memory` on `memory-lancedb`.
  - Run periodic **writeback** from sidecar SQLite → LanceDB (metadata governance).
  - Silent-on-success; only notify on anomalies (errors/missing IDs).

- **Stage B (canary, short window)**: off-peak *temporary* slot switch.
  - Backup config → switch slot to `openclaw-mem-engine` → run a small golden-set recall check → rollback.
  - Goal: prove lifecycle receipts (`policyTier` + `ftsTop/vecTop/fusedTop` + tier counts) behave as expected under real traffic.

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
- `memory_recall` now exposes bounded lifecycle receipts (`details.receipt.lifecycle`) with skip reason, per-tier candidate/selected counts, and compact `ftsTop` / `vecTop` / `fusedTop` IDs.

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

Status: **DONE** (proof-first closure slice landed on 2026-04-06; topology unchanged).

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
- Closure packet: `docs/2026-04-06_writeback-recall-policy-loop-closure.md`

### M2 — Ops hardening (index lifecycle + optimize + drift)

Deliverables (coarse):

- scheduled `optimize` with receipts
- index existence + health checks
- drift dashboard: label distribution + “unknown” %

### M3 — Versioning safety net (tags + rollback)

Deliverables (coarse):

- tag versions before large auto-capture or regrading changes
- ability to revert/checkout a tagged version

Spec (v0): `docs/specs/mem-engine-versioning-safety-net-v0.md`

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
