# Using Obsidian with openclaw-mem (optional)

Obsidian is a local-first knowledge base that works on top of a **folder of Markdown files** (a “vault”).

This pairs extremely well with `openclaw-mem`, because `openclaw-mem` is designed to generate:
- durable, auditable memory artifacts (SQLite + exports)
- daily notes and summaries (optional)
- progressive recall outputs you can trace back to source

Think of it as:

- `openclaw-mem` = **memory layer + retrieval + automation primitives**
- Obsidian = **human-facing cockpit** (reading, linking, graph view, manual curation)

---

## What you get (why bother)

### 1) A “second brain” UI for your agent’s memory

- Browse exported memories as normal notes.
- Cross-link them into projects/themes.
- Use Obsidian search + graph view to see what your agent has been doing over time.

### 2) A safe, local-first workflow

- Everything is files on disk.
- Easy backup (git/rsync), easy migration.
- You can start read-only and gradually allow writes.

### 3) Better collaboration between you and the agent

- You curate the “source-of-truth” notes.
- The agent can ingest/cite from those notes (via `openclaw-mem ingest` + `search/timeline/get`).

---

## Recommended adoption approach (roadmap)

### Phase 0 — Read-only vault (1 day)

Goal: get value without risk.

1. Create a vault folder, e.g.:
   - `~/Obsidian/OpenClawVault` (macOS/Linux)
2. Add an `OpenClaw/` subfolder inside the vault.
3. Export a small slice of observations into the vault:

```bash
uv run openclaw-mem export \
  --to ~/Obsidian/OpenClawVault/OpenClaw/observations.md \
  --limit 200 --yes --json
```

4. Open the vault in Obsidian and verify you can search/read the export.

Safety note: In this phase, the agent never writes to the vault.

### Phase 1 — Daily notes + weekly consolidation (2–7 days)

Goal: a stable “memory timeline”.

- Keep `~/.openclaw/memory/` (daily notes + MEMORY.md) under version control or backed up.
- Optionally symlink `~/.openclaw/memory` into your vault as `OpenClaw/memory/`.

If you use AI compression (`openclaw-mem summarize`), treat:
- daily notes (`memory/YYYY-MM-DD.md`) as raw logs
- `MEMORY.md` as curated compressed context

### Phase 2 — Structured notes (Hub & Spoke) (1–2 weeks)

Goal: make the knowledge base “alive”, not a dump.

- Create a few hub notes (MOCs):
  - `OpenClaw/Hub.md`
  - `Projects/<project>.md`
  - `People/<name>.md`
- As you read exports, link the parts that matter.

### Phase 3 — Controlled writes from the agent (optional)

Goal: automation without losing trust.

- Give the agent a dedicated folder like `OpenClaw/Inbox/`.
- Only allow append-only writes initially.
- Use deterministic triage + approval prompts for risky actions.

#### Minimal closed-loop (v0): approve → import

A practical way to turn Obsidian into a *real* learning loop (instead of just a viewer) is:

1. Agent writes proposals into `OpenClaw/Inbox/`.
2. Human approves by adding bullet items into `OpenClaw/Approved/approved_memories.md`.
3. Importer persists approved items into `openclaw-mem` using `openclaw-mem store`.

Reference importer script:
- `scripts/obsidian_approved_import.py`

---

## Practical integration patterns

### Pattern A: Obsidian as viewer; openclaw-mem as runtime store (recommended)

- Keep SQLite as the runtime store.
- Periodically export snapshots into the vault for human review.

### Pattern B: Vault as source-of-truth; openclaw-mem indexes it

- Treat the vault as canonical notes.
- Periodically ingest vault exports (or selected folders) into `openclaw-mem`.

This is powerful, but you must be careful about:
- accidental ingestion of private/secrets
- duplicated or conflicting notes

---

## What you need to start

- Obsidian installed
- A chosen vault folder location
- A backup plan (git, rsync, cloud drive)
- A clear policy on what the agent is allowed to write

---

## Suggested next step

If you want, we can add a tiny helper command to `openclaw-mem` later:
- `openclaw-mem export-obsidian --vault <path>`

…but it’s intentionally not required to get value.
