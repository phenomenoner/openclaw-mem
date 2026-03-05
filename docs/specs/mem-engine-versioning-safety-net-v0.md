# Mem Engine Versioning Safety Net (M3) — Dataset Snapshots + Tags (v0)

Status: **DRAFT**

Owner: `openclaw-mem-engine` (slot backend) + operator tooling in `openclaw-mem`.

## Problem
Today we can roll back **behavior** by switching `plugins.slots.memory` back to `memory-lancedb` or `memory-core`.

But we cannot roll back **data/index state** for the engine’s LanceDB dataset:

- No “tag this dataset state before a risky change” action
- No “list tags/snapshots” discovery
- No “checkout a tagged snapshot” path
- No receipts that let ops prove what changed

This matters most before changes like:
- enabling more aggressive auto-capture rules
- running regrading or mass writeback
- reindex/optimize operations

## Goals (v0)
1) **Operator-grade safety net**: make it cheap to capture a recoverable dataset snapshot before risky changes.
2) **Rollbackable by design**: restore the memory dataset to a known-good state without manual surgery.
3) **Observable**: every action emits a small, redaction-safe receipt (counts/paths only).
4) **Local-first**: no external services required.

## Non-goals (v0)
- LanceDB-native time-travel / MVCC assumptions (if it exists, we don’t rely on it yet)
- Deduplicated incremental snapshots
- Cross-machine replication
- UI

## Proposed design: filesystem snapshots + manifest (minimal magic)

### Key stance
Treat the LanceDB dataset directory as an **artifact** that can be snapshotted and switched by changing `dbPath`.

### What we snapshot
- `dbPath` directory used by `openclaw-mem-engine` (default: `~/.openclaw/memory/lancedb`)
- Optional: per-table metadata files (if separated in future)

### Where snapshots live
- Default snapshots directory (configurable):
  - `~/.openclaw/memory/lancedb-snapshots/`

Each snapshot is:
- A directory copy OR a `.tar.zst` archive (implementation choice)
- With a **manifest JSON** next to it

### Manifest schema (v0)
Filename:
- `manifest.json` inside the snapshot folder, or `snapshot.<tag>.manifest.json`

Fields:
```jsonc
{
  "kind": "openclaw-mem-engine.dataset-snapshot.v0",
  "tag": "pre-autocapture-v2",
  "createdAt": "2026-03-05T00:00:00Z",
  "source": {
    "dbPath": "~/.openclaw/memory/lancedb",
    "table": "memories"
  },
  "artifact": {
    "format": "dir" ,
    "path": "~/.openclaw/memory/lancedb-snapshots/pre-autocapture-v2/"
  },
  "reason": "Before enabling autoCapture captureTodo",
  "stats": {
    "rowCount": 1234,
    "oldestCreatedAtMs": 0,
    "newestCreatedAtMs": 0
  },
  "notes": {
    "openclawVersion": "2026.3.2",
    "openclawMemVersion": "(optional)",
    "engineTableSchemaHash": "(optional)"
  }
}
```

## Operator surfaces (CLI/tools) — proposal

### Commands (suggested)
- `openclaw-mem engine snapshot create --tag <tag> [--reason <text>] [--db-path <path>] [--snapshots-dir <path>]`
- `openclaw-mem engine snapshot list [--json]`
- `openclaw-mem engine snapshot checkout --tag <tag> [--set-config] [--restart-gateway]`
- `openclaw-mem engine snapshot delete --tag <tag> --yes`

(Exact wiring can be either in `openclaw-mem` python CLI, or a small TS tool inside the engine plugin; preference: python CLI for file ops + determinism.)

### Receipt contract (v0)
All commands should return a stable, bounded JSON:

- `create` receipt includes:
  - tag, createdAt, source dbPath, snapshot artifact path, file count/bytes (optional), rowCount (if cheap)
- `checkout` receipt includes:
  - previous dbPath, new dbPath, whether config was updated, whether gateway restart was requested

No raw memory text.

## Safety / constraints
- Must validate tag names (`[a-zA-Z0-9._-]{1,64}`) and prevent path traversal.
- Default posture: **fail-closed** for dangerous actions (delete, checkout with overwrite).
- Snapshots are sensitive by default (can contain private memory). Never auto-publish.

## Acceptance checklist (v0)
- [ ] Create snapshot with tag; manifest written; receipt emitted.
- [ ] List shows snapshots deterministically (by createdAt desc).
- [ ] Checkout switches engine dbPath to the snapshot and the system remains functional.
- [ ] Rollback instructions are one-screen copy/paste.
- [ ] Basic tests cover tag validation + path traversal prevention.

## Rollout plan
1) Ship CLI + tests (feature-flagged).
2) Document operator workflow: “before risky change → snapshot create”.
3) Add one optional cron reminder (weekly) to ensure snapshots dir exists + disk is healthy (silent on green).
