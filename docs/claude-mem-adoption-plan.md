# claude-mem → OpenClaw Memory Management Adoption Plan

## Executive summary
OpenClaw already ships with a **native memory search subsystem** (SQLite + sqlite-vec, hybrid BM25+vector) and **hook/plugin architecture**. This makes adopting claude-mem’s core patterns feasible **without introducing ChromaDB**. Recommendation: **Adopt the progressive disclosure search model + automatic observation capture + AI compression**, but **adapt** implementation to OpenClaw’s plugin + hook system and reuse the built‑in memory search (memory-core) and storage. Skip the local web viewer for v1; make it CLI-first as requested.

---

## 1) Evaluation: Adopt / Adapt / Skip

| Concept | Decision | Rationale | OpenClaw mapping |
|---|---|---|---|
| Observation capture (PostToolUse hooks) | **Adapt** | OpenClaw has hooks and plugin tool-result hooks, not claude-mem’s exact lifecycle. Use `tool_result_persist` + command hooks. | Plugin tool hook (`tool_result_persist`) + hooks (`command:*`, `agent:bootstrap`) to record observations. |
| AI compression of observations | **Adopt** | Core value-add: compress high-volume tool logs into durable learnings. | New plugin service: summarize observation batches into “learning records,” append to `memory/YYYY-MM-DD.md`, optionally update `MEMORY.md`. |
| SQLite + FTS5 for storage | **Adopt** | Lightweight, stable, and already used in OpenClaw memory search store. | Add a dedicated `openclaw-mem.sqlite` for observations + summaries; reuse sqlite-vec when available. |
| ChromaDB for vector search | **Skip** | Explicit constraint: prefer OpenClaw’s native vector DB. | Use OpenClaw’s `memorySearch` subsystem (sqlite-vec + JS fallback). |
| Progressive disclosure search (3-layer) | **Adopt** | Token-efficiency is non‑negotiable; proven pattern. | Implement `search → timeline → get_observations` in CLI and plugin API. |
| Session lifecycle hooks | **Adapt** | OpenClaw has command hooks now; session:start/end are “future events.” | Use `command:new`, `command:reset`, `command:stop`, `agent:bootstrap` until session events land. |
| Worker service (HTTP API) | **Skip (v1)** | Overkill for CLI-first. Can add later if UI is built. | Keep as local library + CLI commands. |
| Viewer UI | **Skip (v1)** | Nice-to-have; not required by CK. | Defer; maybe a simple `openclaw-mem tail` later. |
| mem-search skill | **Adapt** | OpenClaw skill system is markdown-based; for CLI-based search, use plugin CLI. | Provide a skill wrapper that calls `openclaw-mem search`. |

---

## 2) OpenClaw constraints & native capabilities (facts)

**From OpenClaw docs:**
- OpenClaw memory is Markdown in workspace (`memory/YYYY-MM-DD.md`, `MEMORY.md`).
- Native semantic search exists via `memorySearch` (sqlite-vec + BM25 fallback). Indexed store lives in `~/.openclaw/memory/<agentId>.sqlite`.
- `openclaw memory` CLI exists for status/index/search.
- Hooks exist for `command:new`, `command:reset`, `command:stop`, `agent:bootstrap`, `gateway:startup`.
- `tool_result_persist` plugin hook can intercept tool results before transcript persistence.

**Assumptions (documented):**
- Plugin APIs can write workspace files and create local SQLite stores.
- Tool-result hook can be used as a “PostToolUse” capture analog.
- If session start/end events are added later, we will map to them directly.

---

## 3) Proposed architecture (text diagram)

```
┌────────────────────────────────────────────────────────────────┐
│ OpenClaw Gateway                                               │
│                                                                │
│  Hooks (command:new/reset/stop, agent:bootstrap)               │
│          │                                                     │
│          ▼                                                     │
│  openclaw-mem plugin (in-process)                              │
│    - observation collector                                     │
│    - batch summarizer (LLM)                                    │
│    - storage (SQLite + FTS5 + sqlite-vec)                       │
│    - CLI commands (openclaw-mem)                               │
│    - optional skill wrapper                                    │
│          │                                                     │
│          ├── tool_result_persist hook (captures tool outputs)  │
│          ├── writes raw observations → openclaw-mem.sqlite      │
│          ├── writes learnings → memory/YYYY-MM-DD.md            │
│          └── (optional) merges to MEMORY.md                     │
│                                                                │
│  Native memorySearch                                           │
│    - semantic search over MEMORY.md + memory/*.md              │
│    - sqlite-vec / JS fallback                                  │
└────────────────────────────────────────────────────────────────┘

CLI user flow:
openclaw-mem search → (1) compact search results
                    → (2) timeline around hits
                    → (3) get_observations for final IDs

Storage:
- openclaw-mem.sqlite: observations + summaries + index metadata
- Existing memory/*.md + MEMORY.md remain source of truth
```

---

## 4) Data model (SQLite)

**Tables (v1):**
- `sessions`:
  - `id`, `agent_id`, `channel`, `started_at`, `ended_at`, `metadata_json`
- `observations`:
  - `id`, `session_id`, `timestamp`, `kind` (tool/user/assistant/system),
    `summary`, `detail_json`, `token_est`, `tool_name`, `tool_status`
- `summaries`:
  - `id`, `session_id`, `created_at`, `type` (batch/final), `summary_md`,
    `learnings_json`, `source_observation_ids`
- `fts_observations` (FTS5 over `summary`, `tool_name`, `detail_json`)
- `vec_observations` (sqlite-vec virtual table; optional)
- `index_meta`:
  - embedder model/provider fingerprint, chunking params, last_reindex

**Notes:**
- Use **FTS5 + vector hybrid** like OpenClaw’s memorySearch. FTS5 is stable; vector optional.
- When sqlite-vec isn’t available, fallback to JS vector search (OpenClaw already supports this).  

---

## 5) Progressive disclosure search (CLI design)

**Layer 1 — `search`** (compact index)
- Returns top N hits with tiny summaries, IDs, timestamps, session, tool name.
- Target ~50–100 tokens per hit.

**Layer 2 — `timeline`**
- Given hit IDs, returns a chronological view (windowed context, e.g., ±5 obs).

**Layer 3 — `get_observations`**
- Given final IDs, return full JSON details + raw tool output pointers.

**Result:** ~10x token savings vs. “full dump” on first query.

---

## 6) CLI interface design (openclaw-mem)

### Global
```
openclaw-mem [--agent <id>] [--db <path>] [--config <path>] [--json]
```

### Commands
- `status` — show store stats, embedding availability, last index time.
- `index` — rebuild/reindex the observation store.
- `search <query>` — Layer 1 search.
  - flags: `--limit`, `--text-weight`, `--vector-weight`, `--since`, `--until`
- `timeline <ids...>` — Layer 2 context window.
  - flags: `--window <n>`
- `get <ids...>` — Layer 3 full details.
- `ingest` — manual import of logs/markdown to observations.
- `summarize` — run AI compression on pending observation batches.
- `export` — export summaries to Markdown (daily or full).
- `config` — print merged config, or set via `--set key=value`.

### Example
```
openclaw-mem search "oauth bug" --limit 20
openclaw-mem timeline 23 41 57 --window 4
openclaw-mem get 23 41 57
openclaw-mem summarize --session latest
```

---

## 7) Integration points with existing memory system

1. **Write learnings to `memory/YYYY-MM-DD.md`**
   - Append a “claude-mem summaries” block after each batch or at `/stop`.
   - Keep raw observation store in SQLite; only distilled summaries go into Markdown.

2. **Optional periodic distillation to `MEMORY.md`**
   - Only in main/private session (match OpenClaw policy).
   - Triggered by manual `openclaw-mem export --to MEMORY.md` or a `command:reset` hook.

3. **Reuse native `memorySearch` for recall**
   - Since memory files are updated, OpenClaw’s built‑in semantic search picks up learnings.

4. **No replacement of existing memory**
   - Do not remove or bypass daily/long-term Markdown files.

---

## 8) Phased implementation plan (milestones)

### Phase 0 — Discovery/Bootstrap (1–2 days)
- Confirm plugin API surface for tool-result hook and workspace IO.
- Prototype minimal SQLite store + CLI skeleton.
- Config shape and default paths.

### Phase 1 — Observation Capture (3–5 days)
- Implement plugin hook `tool_result_persist` to log tool outputs.
- Add `command:*` hooks to bracket sessions.
- Store raw observations in SQLite.
- Provide `openclaw-mem status` + `openclaw-mem search` (FTS only).

### Phase 2 — AI Compression (3–5 days)
- Batch summarizer: chunk observations by session/time window.
- Generate compact summaries + structured learnings.
- Append summaries to `memory/YYYY-MM-DD.md`.
- Add CLI `summarize`, `export`.

### Phase 3 — Vector + Hybrid Search (2–4 days)
- Enable embeddings (OpenClaw `memorySearch` provider config).
- sqlite-vec integration for observations.
- Add hybrid scoring (vector + BM25).

### Phase 4 — Progressive Disclosure UX (2–3 days)
- Implement `timeline` and `get` commands.
- Tooling to convert search results into context blocks for agent injection.

### Phase 5 — Polish + Optional Skill Wrapper (2–3 days)
- Add skill wrapper or macro to call `openclaw-mem search`.
- Add docs, error handling, config examples.
- Optional: `openclaw-mem tail` (stream recent observations).

---

## 9) Config sketch (OpenClaw + plugin)

```json5
plugins: {
  slots: { memory: "memory-core" },
  entries: {
    "openclaw-mem": {
      enabled: true,
      config: {
        dbPath: "~/.openclaw/memory/openclaw-mem.sqlite",
        capture: { tools: true, assistant: true, user: true },
        summarize: {
          batchSize: 50,
          maxTokens: 1000,
          model: "gpt-4.1-mini"
        },
        search: { vectorWeight: 0.7, textWeight: 0.3 }
      }
    }
  }
}
```

---

## 10) Risks & mitigations

- **No session:start/end hooks yet** → use command hooks for now; adopt session hooks when released.
- **Tool-result hook only sees tools** → add optional capture of assistant/user messages by parsing session transcripts post‑hoc.
- **Embedding availability** → rely on OpenClaw memorySearch provider config; fallback to FTS5 only.
- **Token bloat** → enforce batch size + progressive disclosure.

---

## Recommendation
Proceed with a **CLI-first OpenClaw memory plugin** that **captures tool observations, compresses with AI, and writes learnings into existing Markdown memory files**. Use OpenClaw’s native vector search (sqlite-vec + hybrid scoring) rather than external ChromaDB. Defer UI and worker service until CLI workflows are validated.

---

## 11) Proactive memory tools: `memory_store` + `memory_recall`

In addition to automatic observation capture and AI compression, `openclaw-mem` will expose two **proactive tools** that the agent can call explicitly during a session:

### `memory_store`
Save a specific fact, preference, or decision into long-term memory.

| Parameter | Type | Description |
|-----------|------|-------------|
| `text` | string | The information to remember (10–500 chars) |
| `importance` | number (0–1) | Importance weight (default: 0.7) |
| `category` | enum | `preference` / `fact` / `decision` / `entity` / `other` |

**Behaviour:**
- Embeds `text` via the configured embedding provider.
- Deduplicates against existing observations (cosine sim > 0.95 → skip).
- Writes to the SQLite observation store **and** appends a tagged entry to `memory/YYYY-MM-DD.md`.
- Picked up by native `memorySearch` on next query.

### `memory_recall`
Retrieve the most relevant stored memories for a given query.

| Parameter | Type | Description |
|-----------|------|-------------|
| `query` | string | Natural-language search query |
| `limit` | number | Max results (default: 5) |

**Behaviour:**
- Runs hybrid search (vector + BM25) over the observation store.
- Returns results in **progressive disclosure format**: compact summaries first, full details available via IDs.
- Filters by relevance score (configurable min threshold).

### Integration with auto-capture
- `memory_store` is the **explicit** path (user says "remember this" → agent calls the tool).
- Auto-capture via hooks is the **implicit** path (everything is logged; AI compression extracts learnings automatically).
- Both paths write to the same store; deduplication prevents conflicts.
- The agent should prefer `memory_store` only for user-stated preferences or decisions. Let auto-capture handle the rest.

### When to use
- User says "remember …", "prefer …", "always …", "never …" → call `memory_store`.
- Agent needs past context mid-session (e.g. "what did we decide about X?") → call `memory_recall`.
- Routine session work → let auto-capture + AI compression handle it silently.
