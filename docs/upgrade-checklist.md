# Upgrade checklist (OpenClaw + openclaw-mem)

This page is a **repeatable, low-drama** checklist for upgrading **OpenClaw** and/or **openclaw-mem**.

Goal: make upgrades **observable, rollbackable, and non-destructive**.

> This checklist intentionally avoids copying sensitive content. Prefer aggregated counts + redacted samples.

---

## Definitions

- **Observation JSONL**: append-only capture log (from OpenClaw plugin) used as ingest source.
- **SQLite DB**: openclaw-mem ledger (FTS + optional embeddings).
- **Migration receipt**: hash-bound record of the source DB, backup, schema
  transition, invariants, and rollback inputs.
- **Triage state**: a small JSON file to dedupe alerts.

---

## Upgrade node map (do these in order)

Think of each node as a “system test point”.

### Node 0 — Data contract / non-destructive guarantee (hard gate)
**What must remain true:**
- `detail_json.importance` is **fill-missing only** (never overwrite existing values).
- Legacy `detail_json.importance` numeric values remain readable.
- Read-only commands do not migrate or create `-wal` / `-shm` sidecars.
- An expensive schema rewrite runs only through explicit `db migrate`; dry-run
  is zero-write, the write path creates a backup, and rollback requires the
  matching receipt.

**Why:** if this breaks, upgrades risk corrupting operator state.

### Node 0a — Inspect, preview, migrate, and retain rollback proof

Run this node before starting a newer writer against an existing DB. Replace the
paths with operator-controlled locations; do not commit the DB, backup, or
receipt because metadata can still be sensitive.

```bash
DB=/path/to/openclaw-mem.sqlite
RECEIPT=/safe/operator/path/openclaw-mem-migration.json

openclaw-mem db info --db "$DB" --json
openclaw-mem db migrate --db "$DB" --dry-run --json
openclaw-mem db migrate --db "$DB" --receipt-out "$RECEIPT" --json
openclaw-mem db info --db "$DB" --json
openclaw-mem doctor --db "$DB" --json
```

Hard gates after migration:

- `db info` reports the current supported schema and no future-version error.
- Source row-count invariants in the migration receipt pass.
- The receipt and its referenced backup exist outside the repository.
- `doctor` has no fatal DB or embedding-integrity error; warn-only missing
  optional embeddings are acceptable when that lane is unused.
- A representative search and pack smoke returns the expected known records.

If post-migration validation fails, stop writers and use the exact receipt:

```bash
openclaw-mem db rollback --db "$DB" --receipt "$RECEIPT" --json
openclaw-mem db info --db "$DB" --json
```

Rollback preserves the displaced migrated DB with a `.rolledback` suffix. Do
not delete either copy until the operator has revalidated retrieval.

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

**Current baseline status (this workspace):**
- **PASS / standing baseline** — closed as a routine chase item on `2026-03-10` (Asia/Taipei)
- Baseline receipt: `lyria-working-ledger` D28 (`commit 8255c8c`) — `/flush` ACK observed; no duplicate visible replies
- Latest explicit verification before closure: `last_verified=2026-03-06` (Asia/Taipei)

**Verify (OpenClaw):**
- `/flush` works and sends a brief ACK.
- `/compact` still behaves; no duplicate replies.
- cron delivery/wake behavior is stable (no duplicate notifications).

**Operator policy (current):**
- Node 5 is treated as a **standing PASS baseline**, not a calendar-driven re-verify item.
- Re-verify **only** after a material messaging-surface change or an actual symptom, for example:
  - gateway/Telegram config change
  - gateway restart / reload that may affect delivery behavior
  - delivery routing / retry behavior change
  - observed duplicate/noisy deliveries

---

## Upgrade gates (when it’s “safe to upgrade”)

- **MVP gate (safe-ish):** Node 0 + 1 + 2 + 3
  - Meaning: the schema transition is backed up and verified, and capture,
    ingest, and triage still work without silent rewriting.

- **Ops gate (safe to operate):** MVP gate + Node 5
  - Meaning: your day-to-day workflows won’t break or spam.

- **Product gate (full loop):** Ops gate + Node 4
  - Meaning: both automation and humans can reliably recall/debug.

When a gate is reached, it should be called out explicitly in operator reports.

---

## Copy/paste commands (reference)

> This repo is currently **source-checkout first**. Prefer `uv run --python 3.13 --frozen -- python -m openclaw_mem ...`.

### 0) Basic local sanity (no OpenClaw required)
```bash
uv sync --locked
DB=/tmp/openclaw-mem-upgradecheck.sqlite

uv run --python 3.13 --frozen -- python -m openclaw_mem --db "$DB" --json status
```

### 1) Harvest (production paths are operator-specific)
```bash
export OPENCLAW_MEM_IMPORTANCE_SCORER=heuristic-v1  # optional (alias: heuristic_v1)

uv run --python 3.13 --frozen -- python -m openclaw_mem harvest \
  --source ~/.openclaw/memory/openclaw-mem-observations.jsonl \
  --db ~/.openclaw/memory/openclaw-mem.sqlite \
  --archive-dir ~/.openclaw/memory/openclaw-mem/archive \
  --index-to ~/.openclaw/memory/openclaw-mem/observations-index.md \
  --no-embed --json
```

### 2) Triage (tasks)
```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem triage \
  --db ~/.openclaw/memory/openclaw-mem.sqlite \
  --mode tasks --tasks-since-minutes 1440 --importance-min 0.7 \
  --state-path ~/.openclaw/memory/openclaw-mem/triage-state.json \
  --json
```

Task extraction is deterministic and picks rows when either:
- `kind == "task"`, or
- `summary` starts with `TODO`, `TASK`, or `REMINDER` (case-insensitive; width-normalized via NFKC, so `ＴＯＤＯ`/`ＴＡＳＫ`/`ＲＥＭＩＮＤＥＲ` are accepted), in plain form (`TODO ...`) or bracketed form (`[TODO] ...`, `(TASK) ...`, `【TODO】 ...`, `〔TODO〕 ...`, `{TODO} ...`, `｛TODO｝ ...`, `［TODO］ ...`, `「TODO」 ...`, `『TODO』 ...`, `《TODO》 ...`, `«TODO» ...`, `〈TODO〉 ...`, `〖TODO〗 ...`, `〘TODO〙 ...`, `‹TODO› ...`, `<TODO> ...`, `＜TODO＞ ...`), with optional leading markdown wrappers: blockquotes (`>`; spaced `> > ...` and compact `>> ...`/`>>...` forms), list/checklist wrappers (`-` / `*` / `+` / `•` / `‣` / `▪` / `∙` / `·` / `◦` / `●` / `○` / `・` / `–` / `—` / `−`, then optional `[ ]` / `[x]` / `[✓]` / `[✔]` / `[☐]` / `[☑]` / `[☒]` / `[✅]`), and ordered-list prefixes (`1.` / `1)` / `(1)` / `a.` / `a)` / `(a)` / `iv.` / `iv)` / `(iv)`; Roman forms are canonical). Compact no-space wrapper chaining is also accepted (for example `-TODO ...`, `[x]TODO ...`, `1)TODO ...`, `[TODO]buy milk`, `【TODO】buy milk`, `〔TODO〕buy milk`, `{TODO}buy milk`, `｛TODO｝buy milk`, `［TODO］buy milk`, `「TODO」buy milk`, `『TODO』buy milk`, `《TODO》buy milk`, `«TODO»buy milk`, `〈TODO〉buy milk`, `〖TODO〗buy milk`, `〘TODO〙buy milk`, `‹TODO›buy milk`, `<TODO>buy milk`, `＜TODO＞buy milk`), followed by:
  - `:`, `：`, `;`, `；`, whitespace, `-`, `.`, `。`, `－`, `–`, `—`, `−`, or end-of-string.
  - Example formats: `TODO`, `TODO: rotate runbook`, `{TODO}: rotate runbook`, `｛TODO｝: rotate runbook`, `［TODO］ rotate runbook`, `【TODO】 rotate runbook`, `「TODO」 rotate runbook`, `『TODO』 rotate runbook`, `《TODO》 rotate runbook`, `«TODO» rotate runbook`, `〈TODO〉 rotate runbook`, `〖TODO〗 rotate runbook`, `〘TODO〙 rotate runbook`, `‹TODO› rotate runbook`, `<TODO> rotate runbook`, `＜TODO＞rotate runbook`, `task- check alerts`, `(TASK): review PR`, `- [ ] TODO file patch`, `> TODO follow up with vendor`, `>>[x]TODO: compact wrappers`, `TODO; rotate runbook`, `TASK；follow up on release checklist`.
  - Example run:

    ```bash
    uv run --python 3.13 --frozen -- python -m openclaw_mem triage --mode tasks --tasks-since-minutes 1440 --importance-min 0.7 --json
    ```


### 3) Retrieval smoke test
```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem --db ~/.openclaw/memory/openclaw-mem.sqlite --json search "timeout" --limit 5
```

---

## What to record as “upgrade receipts” (safe to share)

Prefer these aggregated artifacts after an upgrade:

1) **DB info + migration receipt** (schema, aggregate counts, backup/hash proof)
2) **Harvest summary JSON** (inserted/ingested counts + archive path)
3) **Triage JSON** (`needs_attention`, `found_new`, etc.)
4) **Label distribution** (aggregate counts only; no raw text)
5) **Operator UX check**: `/flush` ACK observed; no duplicate spam

---

## Notes / known sharp edges

- cron/runtime cwd matters if openclaw-mem is not packaged: either `cd` into repo root or install as a package/console script.
- Treat real DB snapshots as sensitive by default; do not commit raw row dumps.
