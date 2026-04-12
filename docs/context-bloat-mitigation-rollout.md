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
  - `autoCapture.enabled=true` (captures preference/decision; guarded TODO capture is off by default)
  - **scope inference hardening** from `[ISO:...]` / `[SCOPE:...]` (line-anchored, ignores code fences / injected `<relevant-memories>` blocks)
  - **scope filtering during recall** (autoRecall searches within resolved scope)
  - **scope fallback hardening**: invalid scope tags suppress fallback scopes when `scopePolicy.skipFallbackOnInvalidScope=true` (default)
  - recall receipts include `whySummary` / `whyTheseIds` (operator-legible selection reasons)
- OpenClaw compaction posture:
  - `agents.defaults.compaction.mode = safeguard`
  - pre-compaction `memoryFlush` writes durable notes to `memory/YYYY-MM-DD.md`

Not yet “fully installed + enabled” (relative to the 5-item ideal):
- **hierarchical summaries** (micro/macro) as a first-class recall surface (not just disk files)
- **budgeted packing** across strata (Working Set vs long-term vs receipts)
- always-on scope tags are still operator-driven (`[ISO]` / `[SCOPE]`), not inferred from arbitrary prose

Now available for canary rollout:
- deterministic **Working Set** synthesis + pinned injection (`workingSet.enabled`)
- hardened fallback behavior on invalid scopes (`scopePolicy.skipFallbackOnInvalidScope=true`)

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
Add a `scopePolicy` block (shipped names):
- `defaultScope`: used when neither explicit scope nor `[ISO]/[SCOPE]` is present
- `fallbackScopes`: allowlisted ordered list, consulted only if primary scope returns <limit
- `fallbackMarker`: emit a receipt/log marker whenever fallback happens
- `validationMode`: validate scope at write-time (reduce scope poisoning)
- `skipFallbackOnInvalidScope`: if scope tag is invalid under strict validation, suppress fallback scopes

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
**Status**: shipped in engine codepath; rollout is config-gated (`workingSet.enabled`, default `false`).

**Minimal implementation (no LLM)**
Synthesize a Working Set from *existing captured signal*:
- Goal: latest user request (truncated)
- Constraints: recent preferences + explicit “must/only/never” patterns (heuristic)
- Decisions: recent decisions (must_remember first)
- Next actions: recent TODOs
- Open questions: simple heuristic from user text (`?`) (optional)

Store 1 record per scope as a single memory row:
- `category="other"`
- `id="working_set:<scope>"`
- upsert semantics (one active row per scope) when `workingSet.persist=true`

**Injection rule**
- on the prompt-mutation path (`before_prompt_build` primary, `before_agent_start` fallback): inject Working Set **before** normal autoRecall results (pinned first slot)
- treat Working Set as the **backbone lane**; normal autoRecall is the **hot recall lane** and should not waste slots re-injecting the same durable content by default

**Explainability**
- recall receipts carry `workingSet` summary (`generated`, `id`, `chars`, section counts, `persisted`)
- follow-on selection policy and receipt changes are tracked in `docs/specs/auto-recall-activation-vs-retention-v1.md`

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
scopePolicy:
  enabled: true
  defaultScope: global
  fallbackScopes: []
  fallbackMarker: true
  validationMode: strict
  skipFallbackOnInvalidScope: true

budget:
  enabled: false              # enable in Step 2
  maxChars: 1800
  minRecentSlots: 1
  overflowAction: truncate_oldest

autoCapture:
  captureTodo: false          # enable in Step 3
  maxTodoPerTurn: 1
  todoDedupeWindowHours: 24
  todoStaleTtlDays: 7

workingSet:
  enabled: false              # enable in Step 4
  persist: true
  maxChars: 1200
  maxItemsPerSection: 3

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
- **Scope integrity**: query 3 distinct scopes → no cross-scope leakage; fallback/suppressed-fallback receipts appear only when expected.
- **Working set freshness**: working set updates as conversation evolves.
- **Explainability**: recall receipt shows `whySummary` + `whyTheseIds` + `workingSet` in one screen.
- **Kill-switch drill**: disable workingSet/todo/budget → effect within 60s.

---

## What this plan deliberately does NOT do (yet)
- no automatic promotion of LLM compression output into durable memories without review
- no graph memory / graphrag wiring (tracked separately in graphic-memory specs)
