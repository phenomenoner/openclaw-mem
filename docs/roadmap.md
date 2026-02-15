# Roadmap

This roadmap translates design principles from *personal AI infrastructure* into concrete, testable work items for `openclaw-mem`.

Guiding stance: ship early, stay local-first, and keep every change **non-destructive**, **observable**, and **rollbackable**.

Status tags used here: **DONE / PARTIAL / ROADMAP**.

## Principles (what we optimize for)

- **Sidecar, not slot owner**: OpenClaw memory backends remain canonical; `openclaw-mem` provides capture + local-first recall + ops.
- **Fail-open by default**: memory helpers should not break ingest or the agent loop.
- **Non-destructive writes**: never overwrite operator-authored fields; only fill missing values.
- **Upgrade-safe**: user-owned data/config is stable across versions.
- **Receipts over vibes**: every automation path should emit a measurable summary.
- **Trust-aware by design**: treat skill/web/tool outputs as *untrusted by default* until promoted by an explicit policy; preserve provenance so packing/retrieval can make safer choices.

## Now (next milestones)

### 1) Importance grading rollout (MVP v1)

Status: **PARTIAL** (baseline shipped; benchmark pass pending).

- [x] Canonical `detail_json.importance` object + thresholds
- [x] Deterministic `heuristic-v1` + unit tests
- [x] Feature flag for autograde: `OPENCLAW_MEM_IMPORTANCE_SCORER=heuristic-v1`
- [x] Ingest wiring: only fill missing importance; never overwrite; fail-open
- [x] CLI override: `--importance-scorer {heuristic-v1|off}` for `ingest`/`harvest` (env fallback remains)
- [x] **E2E safety belt**: prove flag-off = no change; flag-on fills missing; fail-open doesn’t break ingest
- [x] **Ingest summary (text + JSON)** with at least:
  - `total_seen`, `graded_filled`, `skipped_existing`, `skipped_disabled`, `scorer_errors`, `label_counts`
- [ ] Small before/after benchmark set (operator-rated precision on `must_remember` + spot-check `ignore`)
  - Pointers: `docs/thought-links.md` and `docs/rerank-poc-plan.md`

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

### 3) Provenance + trust tiers (defense-in-depth)

Goal: make retrieval and packing **trust-aware**, so “helpful but hostile” content doesn’t become durable state by accident.

Deliverables:
- A minimal provenance schema for each record (e.g., `source`, `producer`, optional `url`/`tool_name`, timestamps)
- A simple trust tier field (e.g., `trusted | untrusted | quarantined`) with sane defaults:
  - tool/web/skill captures start as `untrusted`
  - operator-authored notes/promotions can mark `trusted`
- Promotion/quarantine rules that are explicit and auditable (receipts)

Acceptance criteria:
- Default packing/retrieval can prefer `trusted` without breaking existing flows.
- Operators can explain *why* a record was included (provenance + trust tier).

### 4) Context Packer (lean prompt build)

Goal: for each request, locally build a **small, high-signal context bundle** instead of shipping the whole session history.

Deliverables:
- A packing spec (inputs, budgets, citations, redaction rules) **including trust gating**
- `pack` CLI (or equivalent) that outputs:
  - a short “relevant state” section
  - bounded summaries of the top-K relevant durable facts/tasks
  - citations back to record ids / URLs (no private paths)
  - trust tier and provenance hints (enough for audits; not noisy)
- **Layer contract (L0/L1/L2)** for pack inputs/outputs:
  - L0 abstract for fast filtering
  - L1 overview as the default bundle payload
  - L2 detail only on-demand + strictly bounded
- **Retrieval trajectory receipts** (`--trace`): pack must be debuggable (why included/excluded).
- A cheap retrieval baseline **without embeddings** (FTS + heuristics)
- Optional: embedding-based rerank as an opt-in layer

Hybrid upgrade (quality-first, later within this epic):
- Add a **retrieval router** that can combine multiple backends:
  - Lexical (SQLite FTS5/BM25; QMD-style)
  - Semantic (vector store; e.g. LanceDB)
- Default policy (quality-first):
  1) lexical anchors (fast + precise)
  2) semantic fallback (paraphrase recall)
  3) rerank only when needed + strict top-N candidate budgets
- Keep outputs auditable: every packed fact must carry provenance + citations/ids.

Acceptance criteria:
- For a sample of real requests, packing reduces prompt size materially while keeping answer quality stable.
- Output is deterministic enough to debug (receipts + JSON summary).

### 5) Graph semantic memory (idea → project matching)

Goal: represent projects/decisions/concepts as typed entities + edges so we can recommend work with **path justification**.

Deliverables:
- Minimal entity/edge schema (typed)
- Ingest adapter that builds a graph view from:
  - digests, scout reports, decisions
- Query path:
  - `idea/query → top projects → explanation path`
- Storage evaluation:
  - Start with a local typed graph option (Kuzu candidate) but keep the store behind an interface to mitigate longevity risk.

Acceptance criteria:
- Given an idea, we can point to 3–10 candidate projects/tasks with a human-readable justification path.

### 6) User/System separation (upgrade-safe operator state)

Deliverables:
- Clear boundary of **user-owned** vs **system-owned** files/config
- Schema versioning + migration notes (compat layer for old records)

Acceptance criteria:
- Upgrades do not rewrite operator state.
- Old DB/records remain readable.

### 7) Observability & hooks (receipts everywhere)

Deliverables:
- Standardized run summaries for ingest/harvest/triage
- Drift detection for label distribution (e.g., `must_remember` suddenly spikes)
- **Compaction receipts (future)**: capture `before_compaction/after_compaction` lifecycle events into the sidecar ledger so operators can audit “what got summarized” vs “what stayed hot”.
- **Manual `/compact` flush hook (upstream, future)**: when an operator triggers `/compact`, run a pre-compaction memory flush *first* (configurable), then compact. This reduces “oops I compacted before writing durable notes”.

Acceptance criteria:
- Any automated path can be validated via logs + JSON summary.

### 8) Feedback loop (operator corrections → better behavior)

Deliverables:
- Minimal manual override flow (mark/adjust importance)
- Track correction counts + scorer error counts

Acceptance criteria:
- Operators can correct mistakes and see the system behave differently afterward.

### 9) Pruning-safe capture profiles (future)

Goal: make OpenClaw session pruning safer by ensuring important tool outputs remain retrievable locally.

Deliverables:
- Capture profiles that are safe by default:
  - `metadata-only` (always safe)
  - `summary-only` (current default)
  - `head-tail` (bounded content)
- Explicit allowlist/denylist support per tool, with redaction on.

Acceptance criteria:
- Operators can enable aggressive pruning without losing the ability to recover key tool outcomes from `openclaw-mem`.

## Later (optional, higher ambition)

- Hybrid improvements: rerank / eval harnesses
- Additional scorers (LLM-assisted grading as **opt-in**, with strict cost caps)
- Optional protocol adapters (e.g., MCP-compatible surfaces) **without** losing local-first defaults

## Thought links (design references)

These are projects we referenced and **actually used** to shape features or architecture.

- Daniel Miessler — *Personal AI Infrastructure (PAI)*: <https://github.com/danielmiessler/Personal_AI_Infrastructure>
  - Used as an architectural checklist (memory tiers, hooks, user/system separation, continuous improvement).

- `tobi/qmd`: <https://github.com/tobi/qmd>
  - Used to shape our hybrid retrieval direction (FTS5/BM25 + vectors + fusion + rerank) and the benchmarking plan for a “retrieval router” arm.

- 1Password — *From magic to malware: How OpenClaw's agent skills become an attack surface*: <https://1password.com/blog/from-magic-to-malware-how-openclaws-agent-skills-become-an-attack-surface>
  - Used to motivate provenance + trust tiers and “trust-aware” context packing (helpful content can still be hostile).

- `thedotmack/claude-mem`: <https://github.com/thedotmack/claude-mem>
  - Strong early inspiration for an agent memory layer design; we credit it explicitly (see `ACKNOWLEDGEMENTS.md`).

- `volcengine/OpenViking`: <https://github.com/volcengine/OpenViking>
  - Used as a design reference for layered context loading (L0/L1/L2) and retrieval observability (trajectory/trace). Thought-link only; not a backend commitment.
