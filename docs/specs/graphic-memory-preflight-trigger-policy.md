# Spec — Graphic Memory preflight trigger policy (deterministic, bilingual)

## Status
- Version: v0
- Scope: OpenClaw agents using `openclaw-mem` + future `openclaw-mem` product integration
- Posture: **soft trigger**, **fail-open**, **low-noise**

## Goal
Make Graphic Memory’s associative retrieval actually **get used** when it helps most (docs / decisions / dependencies / status verification), without adding noise or breaking existing workflows.

This spec defines a deterministic trigger policy that can be:
1) **Applied immediately** in agent/lane instructions (spec-level Option A), and
2) **Productized** later as a built-in mode of `openclaw-mem pack` / `hybrid`.

## Non-goals
- Hard gating (“must run preflight or fail”) — not for v0.
- LLM-based intent classification — keep it deterministic and auditable.

---

## The trigger (when to run `graph preflight`)

### Inputs
- `user_query`: the user’s current message (raw text)
- `project_scope`: a stable scope tag (e.g. `openclaw-mem`, repo name, or operator-chosen project id)

### Output
- `triggered: bool`
- `reason: string` (deterministic; for `--trace` only)

### Deterministic match rules (OR)
Trigger if **any** of the following matches:

#### A) Explicit “doc / spec / decision” intent
Match if query contains any of these tokens (case-insensitive):
- English: `spec`, `docs`, `documentation`, `roadmap`, `decision`, `tech note`, `design`, `architecture`, `PRD`, `SOP`, `runbook`
- 中文: `文件`, `文檔`, `規格`, `spec`, `PRD`, `roadmap`, `決策`, `紀錄`, `技術筆記`, `架構`, `設計`, `SOP`, `流程`

#### B) “Where is / find / locate / link” lookup intent
Match if query contains patterns like:
- English: `where is`, `where are`, `find`, `locate`, `which file`, `link to`, `point me to`
- 中文: `在哪`, `哪裡`, `找`, `搜尋`, `定位`, `哪個檔`, `連結`, `指到`, `出處`

#### C) Dependency / relationship intent (high ROI for Graphic Memory)
Match if query contains:
- English: `dependency`, `depends on`, `related`, `relationship`, `connect`, `tie to`, `how is X related`
- 中文: `依賴`, `關聯`, `之間關係`, `怎麼連`, `串起來`, `相關`, `影響範圍`

#### D) Verification / “is this true / confirm status” intent
Match if query contains:
- English: `confirm`, `verify`, `is it true`, `did we`, `current status`, `latest`, `what changed`, `changelog`
- 中文: `確認`, `驗證`, `是不是真的`, `我們有沒有`, `目前狀態`, `最新`, `改了什麼`, `變更`

#### E) Direct references to stable operator artifacts
Match if query mentions any of:
- `DECISIONS`, `TECH_NOTES`, `PM`, `STATUS`, `INDEX`, `QUICKSTART`, `CHANGELOG`
- `docs/specs/` or `projects/` (path-like anchors)

### Anti-trigger (don’t run even if something matches)
Do **not** trigger if query is clearly:
- casual chat / emotional support only
- purely generative writing without any retrieval need

(Keep anti-trigger minimal; better to err on “soft trigger + fail-open”.)

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

Injection rules:
- Inject **only** the returned `bundle_text`.
- If output is empty or the command fails: **continue normally** (fail-open).
- Keep it low-noise: do not mention preflight unless asked; optionally keep a trace receipt.

---

## Productization plan (openclaw-mem)

### Proposed CLI surface (default OFF)
- `openclaw-mem pack --use-graph=off|auto|on`
  - `off` (default): existing behavior
  - `auto`: run the deterministic trigger above; only then run preflight
  - `on`: always run preflight (still fail-open; budgeted)
- Knobs:
  - `--graph-budget-tokens 1200`
  - `--graph-take 12`
  - `--graph-scope <scope>` (defaults to pack’s scope)

### Trace contract additions (only when `--trace`)
- `graph.triggered: bool`
- `graph.trigger_reason: string`
- `graph.selected_refs_count: int`
- `graph.budget_tokens: int`
- `graph.budget_used_estimate: int (optional)`
- `graph.fail_open: true` + `graph.error: <redacted first line>` when applicable

Acceptance criteria (MVP):
- No regressions when graph is OFF.
- In `auto` mode, trigger is deterministic and explainable via trace.
- In all modes, graph failures do not break packing.
