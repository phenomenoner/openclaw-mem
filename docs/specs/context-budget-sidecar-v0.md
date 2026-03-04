# Context Budget Sidecar (v0) — tool output offload + compaction continuity

Status: **DESIGN + v0 implementation planned**

## 0) One-liner
Make OpenClaw cheaper and more reliable by moving large, low-leverage payloads **off-prompt**, keeping only a **handle + bounded summary**, and supporting **checkpoint packs** that preserve continuity across compaction.

## 1) Problem
In long-running agent systems, cost and latency explode because the runtime keeps injecting:
- long session history,
- large tool outputs (browser snapshots, logs, HTML/PDF),
- and heavy workspace files.

The failure mode is predictable:
- prompt grows → tokens grow → tool calls slow down → compaction triggers unpredictably → agent “forgets”.

## 2) Product stance (openclaw-mem fit)
`openclaw-mem` acts as a **side-car**:
- storage (raw artifacts + metadata)
- retrieval (budgeted expansion)
- governance (retention/redaction)

We do **not** replace OpenClaw’s orchestrator. We supply a stable, auditable “context substrate”.

## 3) Non-goals (v0)
- No automatic OpenClaw core middleware changes required.
- No perfect lossy compression claims.
- No guaranteed semantic summarization without an LLM.

## 4) Interfaces (stable contracts we can ship now)

### 4.1 Artifact handle
A handle is the only thing allowed to enter the prompt by default (plus an optional tiny preview).

**v0 handle format (self-describing, collision-proof):**
- `ocm_artifact:v1:sha256:<64-hex>`

Notes:
- Content-addressed by full SHA-256 (no truncation).
- No timestamps embedded (avoid leaking timing).
- Handle parsing rules must be strict (ASCII, max length, lowercase hex).

### 4.2 Sidecar JSON receipts
All commands should support JSON output for deterministic automation.

#### `artifact.stash.v1` output
```json
{
  "schema": "openclaw-mem.artifact.stash.v1",
  "handle": "ocm_artifact:...",
  "sha256": "...",
  "bytes": 12345,
  "createdAt": "2026-03-04T00:00:00Z",
  "kind": "tool_output",
  "meta": {"tool": "exec", "sessionKey": "..."}
}
```

#### `artifact.fetch.v1` output
```json
{
  "schema": "openclaw-mem.artifact.fetch.v1",
  "handle": "ocm_artifact:...",
  "selector": {"mode": "headtail", "maxChars": 8000},
  "text": "..."
}
```

## 5) Today-doable (v0) implementation plan (no upstream required)

### 5.1 CLI surface
Add a new command group:
- `openclaw-mem artifact stash`
- `openclaw-mem artifact fetch`
- `openclaw-mem artifact peek` (tiny preview + metadata)
- (optional) `openclaw-mem artifact list`
- (optional) `openclaw-mem artifact rm/gc`

### 5.2 Storage layout
Default under OpenClaw state dir:
- `${OPENCLAW_STATE_DIR:-~/.openclaw}/memory/openclaw-mem/artifacts/`

v0 storage is content-addressed:
- `artifacts/blobs/sha256/ab/cd/<fullhex>.txt` or `.txt.gz` (raw payload)
- `artifacts/meta/sha256/ab/cd/<fullhex>.json` (metadata)

Safety requirements:
- Create files with strict permissions (0600 where applicable).
- Metadata must not duplicate full raw content.

### 5.3 Budgeted retrieval (deterministic)
`fetch` must be bounded without needing an LLM.

Default selector:
- `mode=headtail`
- `maxChars` cap

Optional selectors (future):
- `grep` (regex)
- `range` (line/window)
- `jsonpath` (for JSON tool outputs)

### 5.4 How we will “use it” immediately
Adopt a workflow rule:
- If a tool output is big, **stash** it and keep only `handle + short preview` in the prompt.
- When detail is needed, **fetch** a bounded snippet by handle.

This can be done manually or via wrapper scripts (no OpenClaw changes required).

## 6) Mid-term integration plan (upstream hooks; we leave interfaces ready)

### 6.1 Tool-output middleware hook (OpenClaw)
When OpenClaw gains a hook surface (e.g. via context plugins), the ideal flow is:
- tool returns raw payload
- middleware stashes raw → returns handle + summary
- context keeps only handle + summary

### 6.2 Soft compaction / checkpoint hook
On `/compact`:
- pre-hook: build a `checkpoint` artifact (sealed summary + index)
- post-hook: inject checkpoint bundle_text + retrieval hints

This avoids the “delete sessions/*.jsonl” anti-pattern while keeping budgets bounded.

## 7) Risks + mitigations
- **Leakage**: artifacts may contain secrets → default storage is local; add redaction rules + explicit export policy.
- **Infinite self-ingest**: don’t auto-stash injected context blocks; tag and ignore.
- **DB bloat**: store raw as files; keep only metadata in SQLite.

## 8) Acceptance checks (what we measure)
- For heavy tool workflows: input tokens per turn stay within a tight band.
- Fetch always obeys caps (never emits unbounded payloads).
- Handles are stable + auditable (full sha256, strict parse rules).
- Artifacts written with safe permissions (no world-readable dumps).

## 9) Related docs
- Thought-links: `docs/thought-links.md`
- Context packing: `docs/context-pack.md`
- Privacy: `docs/privacy-export-rules.md`
