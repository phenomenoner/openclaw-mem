# Ecosystem Fit: `openclaw-mem` + OpenClaw Native Memory

This page explains how `openclaw-mem` fits with OpenClaw’s native memory stack without ownership conflicts.

## Who owns what

- `memory-core` (OpenClaw native)
  - canonical tools: `memory_search`, `memory_get`
  - role: reliable baseline recall over stored memory files

- `memory-lancedb` (OpenClaw official plugin)
  - canonical tools: `memory_store`, `memory_recall`, `memory_forget`
  - role: semantic long-term memory backend with embedding-based recall

- `openclaw-mem` (this project)
  - role: sidecar capture + local memory operations + observability
  - does **not** replace memory slot ownership
  - does **not** re-register canonical backend tools

## Why this split is useful

- Cleaner upgrades: backend changes (`memory-core` ↔ `memory-lancedb`) do not require reworking your capture pipeline.
- Faster rollback: one slot switch can return you to baseline while capture/audit keeps running.
- Better observability: tool outcomes and backend annotations are preserved in JSONL/SQLite for troubleshooting.
- Lower operating cost: progressive recall (`search → timeline → get`) keeps most lookups local and cheap.

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
