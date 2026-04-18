# Spec — Graphic Memory preflight trigger policy (deterministic, bilingual)

## Status
- Version: v1.1
- Scope: OpenClaw agents using `openclaw-mem` + `openclaw-mem` product integration
- Posture: **soft trigger**, **fail-open**, **low-noise**

## Goal
Make Graphic Memory’s associative retrieval actually **get used** when it helps most (docs / decisions / dependencies / status verification), without adding noise or breaking existing workflows.

Key improvement over v1.0 keyword-only:
- Add a deterministic **Index Probe** stage (semantic-by-retrieval) to improve recall without LLM intent classification.

## Non-goals
- Hard gating (“must run preflight or fail”)
- LLM-based intent classification (kept deterministic + auditable)

---

## Trigger pipeline (Stage 0 → 1 → 2)

### Inputs
- `user_query`: the user’s message (raw text)
- `project_scope`: stable scope tag (e.g. `openclaw-mem`)

### Output
- `triggered: bool`
- `reason: string` (deterministic; emitted to trace only)

---

## Stage 0 — Anti-trigger (fast reject)
Skip trigger evaluation when query is clearly not a retrieval request, e.g.:
- very short ACK: `ok / done / thanks / 👍` (case-insensitive)
- token count < 3

(Keep this list short; we prefer **soft trigger + fail-open** over brittle rejection.)

---

## Stage 1 — Keyword / pattern intent (high precision)
Stage 1 is a **priority signal**, not a hard gate.

Trigger signal if any of the following match (case-insensitive):

### A) “doc / spec / decision” intent
- English: `spec`, `docs`, `documentation`, `roadmap`, `decision`, `tech note`, `design`, `architecture`, `PRD`, `SOP`, `runbook`
- 中文: `文件`, `文檔`, `規格`, `spec`, `PRD`, `roadmap`, `決策`, `紀錄`, `技術筆記`, `架構`, `設計`, `SOP`, `流程`

### B) “where is / find / locate / link” lookup intent
- English: `where is`, `where are`, `find`, `locate`, `which file`, `link to`, `point me to`
- 中文: `在哪`, `哪裡`, `找`, `搜尋`, `定位`, `哪個檔`, `連結`, `指到`, `出處`

### C) Dependency / relationship intent
- English: `dependency`, `depends on`, `related`, `relationship`, `connect`, `tie to`, `how is X related`
- 中文: `依賴`, `關聯`, `之間關係`, `怎麼連`, `串起來`, `相關`, `影響範圍`

### D) Verification / “is this true / confirm status” intent
- English: `confirm`, `verify`, `is it true`, `did we`, `current status`, `latest`, `what changed`, `changelog`
- 中文: `確認`, `驗證`, `是不是真的`, `我們有沒有`, `目前狀態`, `最新`, `改了什麼`, `變更`

### E) Direct references to stable operator artifacts
- `DECISIONS`, `TECH_NOTES`, `PM`, `STATUS`, `INDEX`, `QUICKSTART`, `CHANGELOG`
- `docs/specs/` or `projects/` (path-like anchors)

---

## Stage 2 — Index Probe (semantic-by-retrieval; higher recall)
If Stage 1 misses (or for trace instrumentation), run a lightweight probe against the local index:
- Use SQLite FTS (`observations_fts`) via `graph index` primitives.
- Decision rule is deterministic and tunable.

### Default thresholds (initial; corpus-dependent)
FTS bm25() is **lower = better** (in our corpus it is typically negative). Defaults:
- `T_HIGH = -5.0` (probe strong enough to trigger)
- `T_MARGINAL = -2.0` (weak match; allow breadth rescue)
- `N_MIN = 3` (breadth minimum)
- `PROBE_LIMIT = 5`

### Decision (Stage 1 miss)
- If probe returns 0 rows → skip
- Else if best_score ≤ `T_HIGH` → trigger (`probe_strong`)
- Else if best_score ≤ `T_MARGINAL` AND count(score ≤ `T_MARGINAL`) ≥ `N_MIN` → trigger (`probe_breadth`)
- Else → skip (`probe_weak`)

---

## Immediate usage (spec-level Option A)
When triggered:

```bash
OPENCLAW_MEM_GRAPH_AUTO_RECALL=1 \
openclaw-mem graph preflight "<user_query>" \
  --scope "<project_scope>" \
  --take 12 \
  --budget-tokens 1200
```

Rules:
- Inject **only** `bundle_text`.
- If empty/error: **continue normally** (fail-open).
- Low-noise: don’t mention preflight unless asked.

---

## Productization plan (openclaw-mem)

### CLI surface (default OFF)
- `openclaw-mem pack --use-graph=off|auto|on`
  - `off` (default): existing behavior
  - `auto`: Stage 0/1/2 trigger; only then run preflight
  - `on`: always run preflight (still fail-open; budgeted)

### Knobs
- `--graph-scope <scope>`
- `--graph-budget-tokens 1200`
- `--graph-take 12`
- Probe knobs (auto mode):
  - `--graph-probe on|off`
  - `--graph-probe-limit 5`
  - `--graph-probe-t-high -5.0`
  - `--graph-probe-t-marginal -2.0`
  - `--graph-probe-n-min 3`

### Trace additions (only when `--trace`)
- `trace.extensions.graph.*` (redaction-safe):
  - `triggered`, `trigger_reason`, `stage1_hit`, `stage1_categories`
  - `probe_ran`, `probe_best_score`, `probe_hit_count`, `probe_decision`, `probe_latency_ms`
  - `selected_refs_count`, `budget_tokens`, `fail_open`, `error_first_line` (if any)

Current implementation note:
- short-but-explicit operator artifact refs such as `docs/specs/` may bypass the generic `too_short` anti-trigger in auto mode
- ack-like short queries still stay rejected
- probe receipts now also carry threshold values plus `marginal_count` so breadth-trigger decisions are auditable

Acceptance (MVP):
- OFF = no behavior change.
- AUTO = deterministic + traceable.
- Fail-open never breaks pack.
