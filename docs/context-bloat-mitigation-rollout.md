# Context bloat mitigation — “down‑N minimal changes” rollout plan (openclaw-mem)

Goal: take the 5 mitigation ideas (Working Set / Hierarchical Summaries / Budgeted Retrieval+Packing / Namespace Isolation / Recency+Deep Recall) from **PARTIAL** → **INSTALLED + ENABLED** via a sequence of *minimal, rollbackable* steps.

Design principles:
- **Safety net first** (hard caps before adding new capture sources)
- **Config toggles first**, then narrow code changes
- Every step has **success criteria** + **rollback/kill switch**

---

## Current baseline on this host (as of 2026-03)

Already installed + enabled:
- Memory slot backend: `openclaw-mem-engine` (hybrid recall on LanceDB)
- Sidecar capture plugin: `openclaw-mem` (writes JSONL observations)
- `openclaw-mem-engine`:
  - `autoRecall.enabled=true` (small recall injection; capped)
  - `autoCapture.enabled=true` (captures preference/decision; TODO capture currently off)
  - **scope inference** from `[ISO:...]` / `[SCOPE:...]`
  - **scope filtering during recall** (autoRecall searches within resolved scope)
- OpenClaw compaction posture:
  - `agents.defaults.compaction.mode = safeguard`
  - pre-compaction `memoryFlush` writes durable notes to `memory/YYYY-MM-DD.md`

Not yet “fully installed + enabled” (relative to the 5-item ideal):
- a true per-thread **Working Set** blob (Goal/Constraints/Decisions/Open questions/Next)
- **hierarchical summaries** (micro/macro) as a first-class recall surface (not just disk files)
- **budgeted packing** across strata (Working Set vs long-term vs receipts)
- scope is supported, but not yet “automatic by default” without tagging; also no controlled fallback rules

---

## Definition of DONE (“installed + enabled”)
We treat an item as DONE when it:
1) runs automatically (hook or cron),
2) is debuggable (receipts / explainability),
3) has a fast kill switch / rollback.

---

## Key failure modes to design around (so we don’t regress)
- **Token/context overrun**: new capture sources expand injection without a ceiling.
- **Wrong-scope recall**: scoped query misses → fallback broadens too much → irrelevant/unsafe memory.
- **Scope poisoning**: memory is written with the wrong scope and then “correctly” recalled later.
- **Todo spam**: noisy TODO extraction floods memory and crowds out signal.

---

## Roadmap: down‑N minimal changes (recommended order)

### Step 0 — Freeze the truth map (docs + baseline snapshot)
**Change**
- Keep this plan doc and link it from `docs/index.md`.
- Record a baseline snapshot (counts by scope/category; typical injected size).

**Why now**: without a shared truth map, “PARTIAL vs DONE” drifts.

**Success**
- doc is discoverable
- baseline numbers exist (even if rough)

**Rollback**: revert doc changes.

---

### Step 1 — Namespace isolation, but *default-on* (scope policy upgrade)
Scope filtering already exists; what’s missing is a **default** and a **safe fallback policy**.

**Minimal change (code + config)**
Add a `namespace` block (names illustrative):
- `defaultScope`: used when neither explicit scope nor `[ISO]/[SCOPE]` is present
- `fallbackScopes`: allowlisted ordered list, consulted only if primary scope returns <limit
- `fallbackLog`: emit a receipt marker whenever fallback happens
- `scopeValidation`: validate scope at write-time (reduce scope poisoning)

Suggested safe defaults (day-1 behavior mostly unchanged):
- `defaultScope = "global"`
- `fallbackScopes = []` (strict by default; operators can opt-in to `['global']` later)

**Success**
- wrong-scope recall rate goes down
- fallback (if enabled) is observable via receipts

**Rollback / kill switch**
- set `fallbackScopes=[]`
- set `defaultScope="global"`

---

### Step 2 — Budgeted retrieval + packing (hard ceiling first)
**Problem**: today we cap by *count* (`maxItems`), not by injected *size*. New features can silently increase payload size.

**Minimal change (engine-side)**
Add a deterministic **max injected chars** ceiling (or token estimate) on the final `prependContext`:
- `budget.enabled=true|false`
- `budget.maxChars` hard ceiling
- `budget.minRecentSlots` (floor so you never drop the most recent essentials)
- `overflowAction` (`truncate_oldest` is safest)

**Success**
- injected context size is stable under stress
- enabling new capture sources can’t blow up context size

**Rollback**: `budget.enabled=false`.

---

### Step 3 — Turn on TODO capture (now protected by budget)
**Change**: enable `autoCapture.captureTodo=true` (plus guardrails).

**Guardrails (recommended knobs)**
- per-turn capture rate limit
- dedupe window
- stale TTL (to prevent ancient TODOs squatting in Working Set)

**Success**
- TODOs become recallable (including in chats that include injected autoRecall receipts/metadata in the same message)
- no runaway growth; injection stays under `budget.maxChars`

**Rollback**: set `captureTodo=false`.

---

### Step 4 — Rolling Working Set (deterministic synthesis + pinned injection)
**Target**: always inject a small, structured state blob (~300–800 tokens) that stabilizes the thread.

**Minimal implementation (no LLM)**
Synthesize a Working Set from *existing captured signal*:
- Goal: latest user request (truncated)
- Constraints: recent preferences + explicit “must/only/never” patterns (heuristic)
- Decisions: recent decisions (must_remember first)
- Next actions: recent TODOs
- Open questions: simple heuristic from user text (`?`) (optional)

Store 1 record per scope (or per session) as a single memory row:
- `category="other"`
- `id="working_set:<scope>"`

**Injection rule**
- on `before_agent_start`: inject Working Set **before** normal autoRecall results

**Success**
- agent stops re-deriving state from long transcript
- “what are we doing?” is always in-context even late in long sessions

**Rollback / kill switch**
- `workingSet.enabled=false`

---

### Step 5 — Hierarchical summarization (micro → macro)
**Micro summaries (automatic, deterministic)**
- every N turns (e.g. 6–10), write a `micro_summary:<scope>:<bucket>` record
- only include: newly added decisions/TODOs/facts
- hard cap `maxOutputChars`

**Macro summaries (cron, optional / derived)**
- macro summaries are produced on a cron schedule and written to a *shadow* slot
- promotion into durable memory remains **explicit + reviewed** (derived-by-default)

**Success**
- recall can hit summaries even when raw items are many
- summaries stay bounded

**Rollback**
- disable micro
- keep macro as disk-only derived artifact

---

### Step 6 — Recency window + on-demand deep recall (make it explicit)
**Current**: small-window autoRecall exists.

**Make it first-class**
- document a “deep recall” operator action (higher limit + broader tiers + optional fallback scopes)
- keep it explicit (only when user asks) to control cost/noise

**Success**
- users can intentionally pay for deeper context when they ask “what did we decide?”

**Rollback**: remove/disable the explicit deep-recall path.

---

## Suggested config sketch (illustrative)
(Names are not finalized; this is the *shape* we want.)

```yaml
namespace:
  defaultScope: global
  fallbackScopes: []          # opt-in to ['global'] only
  scopeValidation: strict
  fallbackLog: true

budget:
  enabled: false              # enable in Step 2
  maxChars: 12000
  minRecentSlots: 3
  overflowAction: truncate_oldest

capture:
  todo:
    enabled: false            # enable in Step 3
    rateLimitPerTurn: 5
    dedupeWindowHours: 24
    staleTtlDays: 7

workingSet:
  enabled: false              # enable in Step 4
  synthesisMode: deterministic
  maxInputChars: 4000

summarization:
  micro:
    enabled: false            # enable in Step 5
    triggerEveryNTurns: 6
    maxOutputChars: 800
  macro:
    enabled: false
    schedule: "0 */4 * * *"   # optional
```

---

## 1-day acceptance check (after each step, and end-to-end)
- **Token audit**: sample active conversations → injected chars ≤ `budget.maxChars`.
- **Scope integrity**: query 3 distinct scopes → no cross-scope leakage; fallback receipts appear only when expected.
- **Working set freshness**: working set updates as conversation evolves.
- **Kill-switch drill**: disable workingSet/todo/budget → effect within 60s.

---

## What this plan deliberately does NOT do (yet)
- no automatic promotion of LLM compression output into durable memories without review
- no graph memory / graphrag wiring (tracked separately in graphic-memory specs)
