# Roadmap

This roadmap translates design principles from *personal AI infrastructure* into concrete, testable work items for `openclaw-mem`.

Guiding stance: ship early, stay local-first, and keep every change **non-destructive**, **observable**, and **rollbackable**.

## Principles (what we optimize for)

- **Sidecar, not slot owner**: OpenClaw memory backends remain canonical; `openclaw-mem` provides capture + local-first recall + ops.
- **Fail-open by default**: memory helpers should not break ingest or the agent loop.
- **Non-destructive writes**: never overwrite operator-authored fields; only fill missing values.
- **Upgrade-safe**: user-owned data/config is stable across versions.
- **Receipts over vibes**: every automation path should emit a measurable summary.

## Now (next milestones)

### 1) Importance grading rollout (MVP v1)

Status: **in progress**.

- [x] Canonical `detail_json.importance` object + thresholds
- [x] Deterministic `heuristic-v1` + unit tests
- [x] Feature flag for autograde: `OPENCLAW_MEM_IMPORTANCE_SCORER=heuristic-v1`
- [x] Ingest wiring: only fill missing importance; never overwrite; fail-open
- [ ] **E2E safety belt**: prove flag-off = no change; flag-on fills missing; fail-open doesn’t break ingest
- [ ] **Ingest summary (text + JSON)** with at least:
  - `total_seen`, `graded_filled`, `skipped_existing`, `skipped_disabled`, `scorer_errors`, `label_counts`
- [ ] Small before/after benchmark set (operator-rated precision on `must_remember` + spot-check `ignore`)

Acceptance criteria:
- Turning the feature on/off is a one-line env var change.
- E2E tests cover overwrite-prevention and fail-open behavior.
- Each ingest run produces a machine-readable summary suitable for trend tracking.

### 2) Formalize memory tiers (hot / warm / cold)

Goal: turn the implicit pipeline into an explicit policy.

- Hot = observations JSONL (minutes)
- Warm = SQLite ledger (hours → days)
- Cold = durable summaries / curated files (weeks → months)

Deliverables:
- A short spec of promotion rules (what moves up tiers, and why)
- A default operator workflow: `search → timeline → get → store/promote`

Acceptance criteria:
- Operators can explain where a fact lives and how it got there.
- Promotions are auditable and reversible.

## Next (engineering epics)

### 3) User/System separation (upgrade-safe operator state)

Deliverables:
- Clear boundary of **user-owned** vs **system-owned** files/config
- Schema versioning + migration notes (compat layer for old records)

Acceptance criteria:
- Upgrades do not rewrite operator state.
- Old DB/records remain readable.

### 4) Observability & hooks (receipts everywhere)

Deliverables:
- Standardized run summaries for ingest/harvest/triage
- Drift detection for label distribution (e.g., `must_remember` suddenly spikes)

Acceptance criteria:
- Any automated path can be validated via logs + JSON summary.

### 5) Feedback loop (operator corrections → better behavior)

Deliverables:
- Minimal manual override flow (mark/adjust importance)
- Track correction counts + scorer error counts

Acceptance criteria:
- Operators can correct mistakes and see the system behave differently afterward.

## Later (optional, higher ambition)

- Hybrid improvements: rerank / eval harnesses
- Additional scorers (LLM-assisted grading as **opt-in**, with strict cost caps)
- Optional protocol adapters (e.g., MCP-compatible surfaces) **without** losing local-first defaults

## Thought links (design references)

These are projects we referenced and **actually used** to shape features or architecture.

- Daniel Miessler — *Personal AI Infrastructure (PAI)*: <https://github.com/danielmiessler/Personal_AI_Infrastructure>
  - Used as an architectural checklist (memory tiers, hooks, user/system separation, continuous improvement).

- `thedotmack/claude-mem`: <https://github.com/thedotmack/claude-mem>
  - Strong early inspiration for an agent memory layer design; we credit it explicitly (see `ACKNOWLEDGEMENTS.md`).
