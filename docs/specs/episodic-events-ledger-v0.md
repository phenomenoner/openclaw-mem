# Episodic Events Ledger (v0) — append-only session timeline for OpenClaw agents

Status: **IMPLEMENTED (v0)**

Auto-mode addendum: `docs/specs/episodic-auto-capture-v0.md`

Owner: `openclaw-mem` (sidecar / SQLite ledger). Optional read-only projection via `openclaw-mem-engine` can come later.

## Problem
We have durable **semantic** memories (LanceDB via `openclaw-mem-engine`) and operator-authored docs (docs cold lane), but we lack a first-class **episodic** layer:

- “What happened in this session/run?” is currently scattered across tool stdout/stderr, cron run logs, and lifecycle receipts.
- Debugging and audits are painful; summaries are not reproducible because the underlying timeline is not queryable.
- Tool outputs are high-risk (secrets/prompt-injection) and should not be shoved into semantic memory.

## Goals (v0)
1) Append-only event log with a stable schema and deterministic query outputs.
2) **Scope isolation**: no cross-scope leakage by default.
3) **Bounded + redaction-safe**: query results default to summary-only; payload is opt-in and capped.
4) Enable downstream pipelines:
   - session replay
   - episodic → semantic summarization (offline/cron)
   - lifecycle analytics (counts, latency, drift)

## Non-goals (v0)
- A full distributed event system
- Multi-tenant auth (OpenClaw handles that at the app layer; here we store local artifacts)
- Storing large binary artifacts (we store refs/pointers instead)

---

## Data model

### Event types (initial set)
Keep the taxonomy small and OpenClaw-aligned:

- `conversation.user`
- `conversation.assistant`
- `tool.call`
- `tool.result`
- `ops.decision`
- `ops.alert`

(We can add `observation` later if needed, but the above is enough to replay/debug most runs.)

### Event record (logical schema)
Each event is an append-only JSON-like object:

- `event_id` (uuid)
- `ts_ms` (int; event time)
- `scope` (string; must pass the same normalization/validation rules as scopePolicy)
- `session_id` (string; a single run/conversation id; stable for replay)
- `agent_id` (string; logical actor, e.g. `lyria`, `worker`, `cron-lite`)
- `type` (enum; see above)
- `summary` (string; short human-readable description)
- `payload_json` (JSON; optional; bounded; may be redacted)
- `refs_json` (JSON; optional; links to run ids, tool call ids, memory ids, docs recordRefs, file paths)
- `redacted` (bool)
- `schema_version` (string; `openclaw-mem.episodic.v0`)
- `created_at` (UTC ISO string)

### SQLite table (proposed)
Store in the existing `openclaw-mem.sqlite` as a new table.

```sql
CREATE TABLE IF NOT EXISTS episodic_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL,
  ts_ms INTEGER NOT NULL,
  scope TEXT NOT NULL,
  session_id TEXT NOT NULL,
  agent_id TEXT NOT NULL,
  type TEXT NOT NULL,
  summary TEXT NOT NULL,
  payload_json TEXT,
  refs_json TEXT,
  redacted INTEGER NOT NULL DEFAULT 0,
  schema_version TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_episodic_event_id ON episodic_events(event_id);
CREATE INDEX IF NOT EXISTS idx_episodic_scope_ts ON episodic_events(scope, ts_ms);
CREATE INDEX IF NOT EXISTS idx_episodic_session_ts ON episodic_events(session_id, ts_ms);
CREATE INDEX IF NOT EXISTS idx_episodic_scope_type_ts ON episodic_events(scope, type, ts_ms);
```

Notes:
- This is append-only at the application layer; only redaction/retention jobs update/delete rows.
- `payload_json` is intended to be small (default cap suggested: 8KB per event). Large results should be referenced via `refs_json`.

---

## Operator/API surfaces (proposal)

### CLI (openclaw-mem)
Add a new command group:

- `openclaw-mem episodes append ...` (or `episodic append`)
- `openclaw-mem episodes query ...`
- `openclaw-mem episodes search "<query>" ...` (groups matches by `session_id`)
- `openclaw-mem episodes replay <session_id>` (returns a bounded, ordered timeline)
- `openclaw-mem episodes redact --event-id <id> | --session-id <sid> ...`

All commands support `--json` and emit a stable receipt schema.

### Operator usage (v0)

```bash
# append one event
openclaw-mem episodes append \
  --scope openclaw-mem \
  --session-id sess-001 \
  --agent-id lyria \
  --type conversation.user \
  --summary "Asked for status" \
  --payload-json '{"intent":"status"}' \
  --refs-json '{"recordRef":"obs:42"}' \
  --json

# query is scope-bound by default (summary-only)
openclaw-mem episodes query --scope openclaw-mem --session-id sess-001 --limit 50 --json

# include payload only when needed
openclaw-mem episodes query --scope openclaw-mem --session-id sess-001 --include-payload --json

# replay shorthand (ordered timeline)
openclaw-mem episodes replay sess-001 --scope openclaw-mem --json

# transcript recall search (grouped by session)
openclaw-mem episodes search "graph readiness bridge" --scope openclaw-mem --limit 5 --per-session-limit 3 --json

# redact payloads while preserving rows
openclaw-mem episodes redact --session-id sess-001 --scope openclaw-mem --replacement placeholder --json

# retention GC (aggregate receipt only)
openclaw-mem episodes gc --scope openclaw-mem --json
```

### OpenClaw tool surfaces (optional)
If/when we expose this to agents directly, prefer *read-only by default*:

- `memory_episodes_query({ scope, sessionId?, fromTs?, toTs?, types?, limit?, includePayload? })`

Default posture:
- `includePayload=false`
- return: `event_id, ts_ms, type, summary, refs_json (bounded)`

---

## Security / privacy posture

1) **Summary-only default**
- Query returns `summary + refs` only; payload requires explicit `includePayload=true`.

2) **Hard bounds**
- `payload_json` max bytes/chars on ingest.
- `refs_json` also bounded.

3) **Redaction**
- Redaction overwrites `summary` with `[REDACTED]`, clears `refs_json`, and replaces `payload_json` with either `NULL` or a `[REDACTED]` placeholder (per `--replacement`).
- Keep the event row for audit continuity.
- Scope posture: `--event-id` redaction requires `--scope` (or explicit `--global`).

4) **Scope isolation**
- Every query must include a scope (or be explicitly `scope=global`).
- No “fallback to unscoped” behavior.

---

## Retention

Introduce a simple retention policy (v0):

- Default retention: 30 days for `tool.result`, 60 days for `conversation.user`, 90 days for `conversation.assistant`, forever for `ops.decision` (configurable).
- Enforced by a GC command/cron that emits an aggregate-only receipt:
  - deleted counts by type/scope

---

## Integration points (alignment with receipts/ledger)

- Map lifecycle receipts (`autoRecall`, `autoCapture`) into `ops.alert` or a dedicated `ops.receipt` type (optional).
- Map cron run summaries into `ops.alert` events (already aligns with watchdog patterns).
- Link semantic memory records via `refs_json.memory_ids=[...]` when an episodic→semantic summarizer promotes facts.

---

## Acceptance checklist (v0)

- [x] DB migration: table + indexes created (idempotent).
- [x] `episodes append` validates scope/type and enforces payload size caps.
- [x] `episodes query` supports `scope/session_id/from/to/types/limit` and is deterministic.
- [x] `episodes search` supports bounded FTS recall over `search_text` and groups results by `session_id`.
- [x] Summary-only default confirmed by tests.
- [x] Redaction command works (payload removed; redacted flag set).
- [x] Retention GC produces an aggregate receipt.
- [x] Scope isolation tests: scope X cannot query scope Y.

## Rollback
- Feature-flag the command group; disable without schema drop.
- If needed, drop the table (explicit operator action): `DROP TABLE episodic_events;` (not part of normal rollback).
