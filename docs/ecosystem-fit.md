# Ecosystem Fit: `openclaw-mem` + OpenClaw Native Memory

This page explains how `openclaw-mem` fits with OpenClaw’s native memory stack today, and how the optional **openclaw-mem-engine** slot backend would fit without creating ownership conflicts.

## Who owns what

- `memory-core` (OpenClaw native)
  - canonical tools: `memory_search`, `memory_get`
  - role: reliable baseline recall over stored memory files

- `memory-lancedb` (OpenClaw official plugin)
  - canonical tools: `memory_store`, `memory_recall`, `memory_forget`
  - role: semantic long-term memory backend with embedding-based recall

- `openclaw-mem` (this project)
  - role: sidecar capture + local memory operations + observability
  - default posture: **sidecar-only**

- `openclaw-mem-engine` (optional)
  - role: alternative memory slot backend (replaces `memory-lancedb` when enabled)
  - goal: hybrid recall (FTS + vector) + scopes + auditable policies + safe M1 automation (autoRecall/autoCapture)
  - rollback: one-line slot switch
  - does **not** replace the sidecar ledger (SQLite remains for audit/ops)
  - (when enabled) it **does** own the canonical backend tools for the active slot

## Why this split is useful

- Cleaner upgrades: backend changes (`memory-core` ↔ `memory-lancedb`) do not require reworking your capture pipeline.
- Faster rollback: one slot switch can return you to baseline while capture/audit keeps running.
- Better observability: tool outcomes and backend annotations are preserved in JSONL/SQLite for troubleshooting.
- Lower operating cost: progressive recall (`search → timeline → get`) keeps most lookups local and cheap.

## Comparison: `openclaw-mem-engine` vs `win4r/memory-lancedb-pro`

We track completeness against <https://github.com/win4r/memory-lancedb-pro> at the level of **comparable operator-facing capabilities** (not identical UI).

| Capability (comparable) | memory-lancedb-pro | openclaw-mem-engine (ours) |
|---|---:|---:|
| Local-first LanceDB backend | ✅ | ✅ |
| Canonical memory tools (`store/recall/forget`) | ✅ | ✅ |
| Hybrid recall (FTS + vector) | ✅ | ✅ |
| Scope-aware filtering | ✅ | ✅ |
| Policy tiers (must/nice/unknown fallback) | ✅ | ✅ |
| Receipts/debug top-hits (auditable) | ✅ (varies) | ✅ (`ftsTop` / `vecTop` / `policyTier`) |
| Admin ops (list/stats/export/import) | ✅ | ✅ (tool + CLI parity layer, sanitized deterministic export, import dedupe/dry-run) |
| AutoRecall hook (conservative) | ✅ | ✅ (M1: skip trivial prompts, cap K, escape injection) |
| AutoCapture hook (strict) | ✅ | ✅ (M1: category allowlist + secret-skip + dedupe + caps) |
| One-line rollback | ➖ | ✅ (`plugins.slots.memory` switch) |

Deferred (we intentionally keep out of M1):
- UI-heavy memory management screens
- aggressive auto-capture of everything (risk: noise + privacy)
- mandatory rerankers (we keep deterministic fusion first)

## Recommended deployment patterns

### Pattern A — Stable default
Use when reliability is top priority.

- active slot: `memory-core`
- `openclaw-mem`: enabled (capture + ingest + local recall)

Expected value:
- deterministic baseline
- minimal external dependency risk
- full audit trail for later analysis

### Pattern B — Semantic-first
Use when semantic recall quality is the priority.

- active slot: `memory-lancedb`
- keep `memory-core` entry enabled for rollback
- `openclaw-mem`: enabled with backend annotations (`backendMode=auto`)

Expected value:
- official semantic tools + sidecar observability
- quick diagnostics when embedding/runtime issues appear

### Pattern C — Controlled migration
Use when moving from `memory-core` to `memory-lancedb` in production.

- keep both entries enabled
- switch only `plugins.slots.memory`
- run smoke tests: store/recall/forget
- rollback by switching slot back to `memory-core` if needed

Expected value:
- reduced blast radius
- no data-plane blind spots during migration

## Add-on value users can expect from `openclaw-mem`

- A practical memory ledger (what happened, when, by which tool) you can inspect anytime.
- Local-first recall paths that keep routine retrievals fast and inexpensive.
- Backend-aware annotations that make failures easier to root-cause.
- Deterministic triage for heartbeat/ops workflows, so important issues surface early.

In short: OpenClaw backends provide the canonical memory APIs; `openclaw-mem` makes the memory system easier to operate, audit, and trust over time.

## Field issue: ingestion lag (and the practical fix)

### What can go wrong

If harvest runs too infrequently, captured events can pile up in JSONL before they reach SQLite.
In one real run we observed:

- ingest lag: ~118 minutes
- pending captured rows: 89

That is enough to make “what happened just now?” recall feel stale.

### Minimal-risk solution (always-fresh profile)

Use a split pipeline:

1. **Fast lane (freshness first)**
   - every 5 minutes
   - `harvest --no-embed --no-update-index`
   - keeps DB close to real-time with low local workload

2. **Slow lane (quality refresh)**
   - every hour (or slower, depending on budget)
   - `harvest --embed --update-index`
   - refreshes semantic quality without blocking freshness

3. **Optional overhead check**
   - run a 12h token/cost report from `memory/usage-ledger.jsonl`
   - include model breakdown so ops can see exactly what the scheduler costs

### Cost note

- Lowest-cost setup is OS-level scheduler (systemd/cron) for harvest commands.
- OpenClaw cron `agentTurn` works and is convenient, but still spends model tokens on each run wrapper.

## Upstream ops insight: heartbeat token sink and context control

From recent OpenClaw cost/tuning threads, one pattern repeated across operators:

- **Native heartbeat can become a token sink** when each cycle carries heavy active-session context.
- A practical mitigation is to use a **lightweight isolated heartbeat** for health checks and keep healthy runs silent (`NO_REPLY`).

How this affects `openclaw-mem` users:

1. Keep `openclaw-mem` ingest/report jobs isolated and silent on success.
2. Avoid adding extra high-frequency cron loops when an existing heartbeat cadence can carry health checks.
3. Keep auditability in sidecar storage, but keep routine scheduler chatter out of interactive transcripts.

Longer-term architecture direction (upstream):
- A first-class context-provider slot would complement this sidecar model by letting operators control prompt payload directly, while retaining full transcript persistence for audit/replay.

## One-screen architecture diagram

### ASCII

```text
                         (canonical memory slot)
                 +--------------------------------------+
                 |  memory-core  OR  memory-lancedb     |
                 |  tools: search/get OR store/recall   |
                 +-------------------+------------------+
                                     ^
                                     | native memory APIs
+---------------------+              |
|  OpenClaw Sessions  |--------------+
|  (main + cron)      |
+----------+----------+
           |
           | tool_result_persist
           v
+------------------------------+
| openclaw-mem capture plugin  |
| (sidecar, no slot ownership) |
+---------------+--------------+
                |
                | append-only JSONL
                v
+------------------------------+
| openclaw-mem-observations    |
| .jsonl                       |
+----------+-------------------+
           |
           | harvest (fast lane): --no-embed --no-update-index (5m)
           v
+------------------------------+         +---------------------------+
| openclaw-mem.sqlite (FTS)    |<------->| embed/index (slow lane)   |
| recall: search→timeline→get  |         | hourly / budgeted         |
+----------+-------------------+         +---------------------------+
           |
           | ops visibility
           v
+------------------------------+
| usage-ledger + 12h overhead  |
| report (tokens/cost/models)  |
+------------------------------+
```
