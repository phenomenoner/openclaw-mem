# Upgrade checklist (OpenClaw + openclaw-mem)

This page is a **repeatable, low-drama** checklist for upgrading **OpenClaw** and/or **openclaw-mem**.

Goal: make upgrades **observable, rollbackable, and non-destructive**.

> This checklist intentionally avoids copying sensitive content. Prefer aggregated counts + redacted samples.

---

## Definitions

- **Observation JSONL**: append-only capture log (from OpenClaw plugin) used as ingest source.
- **SQLite DB**: openclaw-mem ledger (FTS + optional embeddings).
- **Triage state**: a small JSON file to dedupe alerts.

---

## Upgrade node map (do these in order)

Think of each node as a “system test point”.

### Node 0 — Data contract / non-destructive guarantee (hard gate)
**What must remain true:**
- `detail_json.importance` is **fill-missing only** (never overwrite existing values).
- Legacy `detail_json.importance` numeric values remain readable.
- No mandatory DB migrations / schema rewrites.

**Why:** if this breaks, upgrades risk corrupting operator state.

---

### Node 1 — Capture still writes JSONL (OpenClaw → JSONL)
**Verify:** observation JSONL continues to grow over time (timestamps advance).

> You can validate this without reading contents: check file size / line count / mtime.

---

### Node 2 — Harvest/ingest works (JSONL → SQLite)
**Verify:**
- `harvest` runs successfully and writes into the SQLite DB.
- Optional archive/rotation doesn’t lose data unexpectedly.

---

### Node 3 — Triage works + semantics unchanged (SQLite → alerts)
**Verify:**
- `triage --mode tasks` runs and outputs JSON.
- `needs_attention` / `found_new` semantics match expectations.
- Exit code behavior (e.g., “needs attention” code) remains handled by the operator/automation.

---

### Node 4 — Retrieval still works (search → timeline → get)
**Verify:**
- keyword search returns results
- timeline/get return full rows

---

### Node 5 — Operator UX + delivery surface works
**Verify (OpenClaw):**
- `/flush` works and sends a brief ACK.
- `/compact` still behaves; no duplicate replies.
- cron delivery/wake behavior is stable (no duplicate notifications).

**Receipt validity rule (operator policy):**
- Node 5 receipts are valid for **7 days**, OR must be re-verified immediately after any:
  - gateway/Telegram config change
  - gateway restart
  - observed duplicate/noisy deliveries

---

## Upgrade gates (when it’s “safe to upgrade”)

- **MVP gate (safe-ish):** Node 0 + 1 + 2 + 3
  - Meaning: you won’t go blind (capture/ingest/triage still work) and data won’t get rewritten.

- **Ops gate (safe to operate):** MVP gate + Node 5
  - Meaning: your day-to-day workflows won’t break or spam.

- **Product gate (full loop):** Ops gate + Node 4
  - Meaning: both automation and humans can reliably recall/debug.

When a gate is reached, it should be called out explicitly in operator reports.

---

## Copy/paste commands (reference)

> This repo is currently **source-checkout first**. Prefer `uv run python -m openclaw_mem ...`.

### 0) Basic local sanity (no OpenClaw required)
```bash
uv sync --locked
DB=/tmp/openclaw-mem-upgradecheck.sqlite

uv run python -m openclaw_mem --db "$DB" --json status
```

### 1) Harvest (production paths are operator-specific)
```bash
export OPENCLAW_MEM_IMPORTANCE_SCORER=heuristic-v1  # optional

uv run python -m openclaw_mem harvest \
  --source ~/.openclaw/memory/openclaw-mem-observations.jsonl \
  --db ~/.openclaw/memory/openclaw-mem.sqlite \
  --archive-dir ~/.openclaw/memory/openclaw-mem/archive \
  --index-to ~/.openclaw/memory/openclaw-mem/observations-index.md \
  --no-embed --json
```

### 2) Triage (tasks)
```bash
uv run python -m openclaw_mem triage \
  --db ~/.openclaw/memory/openclaw-mem.sqlite \
  --mode tasks --tasks-since-minutes 1440 --importance-min 0.7 \
  --state-path ~/.openclaw/memory/openclaw-mem/triage-state.json \
  --json
```

Task extraction is deterministic and picks rows when either:
- `kind == "task"`, or
- `summary` starts with `TODO`, `TASK`, or `REMINDER` (case-insensitive; width-normalized via NFKC, so `ＴＯＤＯ`/`ＴＡＳＫ`/`ＲＥＭＩＮＤＥＲ` are accepted), in plain form (`TODO ...`) or bracketed form (`[TODO] ...`, `(TASK) ...`), with optional leading markdown list/checklist wrappers (`-` / `*` / `+` / `•`, then optional `[ ]` / `[x]`) and optional ordered-list prefixes (`1.` / `1)` / `(1)` / `a.` / `a)`), followed by:
  - `:`, `：`, whitespace, `-`, `－`, `–`, `—`, `−`, or end-of-string.


### 3) Retrieval smoke test
```bash
uv run python -m openclaw_mem --db ~/.openclaw/memory/openclaw-mem.sqlite --json search "timeout" --limit 5
```

---

## What to record as “upgrade receipts” (safe to share)

Prefer these aggregated artifacts after an upgrade:

1) **DB status JSON** (counts + min/max timestamps)
2) **Harvest summary JSON** (inserted/ingested counts + archive path)
3) **Triage JSON** (`needs_attention`, `found_new`, etc.)
4) **Label distribution** (aggregate counts only; no raw text)
5) **Operator UX check**: `/flush` ACK observed; no duplicate spam

---

## Notes / known sharp edges

- cron/runtime cwd matters if openclaw-mem is not packaged: either `cd` into repo root or install as a package/console script.
- Treat real DB snapshots as sensitive by default; do not commit raw row dumps.
