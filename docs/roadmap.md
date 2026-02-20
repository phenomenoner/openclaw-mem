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

## 2026-02 Pilot execution order (two pillars, incremental)

To keep scope controlled for the current pilot:

### Pillar A — build now (implementation + receipts)
- Harden `pack --trace` into an explicit contract (`openclaw-mem.pack.trace.v1`) with schema tests.
- Enforce citation/rationale coverage for included items (must stay at zero-missing).
- Keep budget policy minimal (single `budgetTokens` cap); track budget-driven exclusions.
- Run counterfactual benchmark arm `A0` (baseline pack behavior) vs `A1` (contract enforcement) in `openclaw-memory-bench`.
- Promotion gate to default behavior requires: schema pass, determinism pass, and reviewed real-run receipts.

### Pillar B — spec now, implement later
- Define learning-record schema, lifecycle states, and benchmark preregistration only.
- No runtime rollout before Pillar A promotion gate + soak evidence.

### Change-control guardrail
- This pilot step updates docs/specs and benchmark plans only.
- No live OpenClaw config or cron schedule changes are included in this step.

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

### 3) Memory lifecycle (reference-based decay + archive-first)

Goal: keep memory **high-signal** over long horizons by applying *use-based* retention (recency/frequency), not “age-based deletion”.

Core idea:
- Track **reference events** for durable records (when a record actually influences packed context).
- Apply **decay/archival** based on `last_used_at` (ref) and `priority` tiers.
- Default to **soft archive**, not hard delete (fail-safe while recall is imperfect).

Proposed fields (upgrade-safe; store in `detail_json.lifecycle` first):
- `priority`: `P0|P1|P2`
  - P0 = never auto-archive (identity/safety/operator invariants)
  - P1 = long-lived preferences/decisions
  - P2 = short-lived context
- `last_used_at`: timestamp of last *real* use (see definition below)
- `used_count`: optional, monotonic count of use events
- (optional) `archived_at` / `state=archived`

Definition: what counts as “used” (avoid gaming the signal)
- **Does NOT count**: bulk preload / “always include these memories”.
- **Counts (cheap default)**: a record is **selected into the final `pack` bundle** (has a citation like `obs:<id>`).
- Optional later: track a weaker `last_retrieved_at` for candidates vs `last_included_at` for final bundle inclusion.

Receipts (non-negotiable)
- `pack --trace` should be able to list which `recordRef`s were “refreshed” this run.
- Daily lifecycle job should emit an aggregate-only receipt (archived counts by tier/trust/importance).

Acceptance criteria:
- Ref updates are auditable (receipt + trace), and do not require guessing “importance at write time”.
- Archive is reversible; no hard delete in MVP.
- Trust tier remains independent: “used often” does **not** automatically become `trusted`.

## Next (engineering epics)

### 4) Provenance + trust tiers (defense-in-depth)

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

### 5) Context Packer (lean prompt build)

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
  - Include a minimal JSON schema (v0) so we can diff behavior over time and compare arms in benchmarks.
- A cheap retrieval baseline **without embeddings** (FTS + heuristics)
- Optional: embedding-based rerank as an opt-in layer

#### Trace receipt schema (v1, redaction-safe)

When `openclaw-mem pack --trace` is used, it should be able to emit a JSON receipt like:

```json
{
  "kind": "openclaw-mem.pack.trace.v1",
  "ts": "2026-02-15T00:00:00Z",
  "version": {
    "openclaw_mem": "1.x",
    "schema": "v1"
  },
  "query": {
    "text": "…",
    "scope": "(optional scope tag or project id)",
    "intent": "(optional: lookup|plan|debug|write|research)"
  },
  "budgets": {
    "budgetTokens": 1200,
    "maxItems": 12,
    "maxL2Items": 2,
    "niceCap": 100
  },
  "lanes": [
    {
      "name": "hot",
      "source": "session/recent",
      "searched": true,
      "notes": "recent turns only"
    },
    {
      "name": "warm",
      "source": "sqlite-ledger",
      "searched": true,
      "retrievers": [
        { "kind": "fts5", "topK": 50 }
      ]
    },
    {
      "name": "cold",
      "source": "curated-summaries",
      "searched": false
    }
  ],
  "candidates": [
    {
      "id": "rec:123",
      "type": "memory|resource|skill|decision|digest",
      "layer": "L0|L1|L2",
      "importance": "must_remember|nice_to_have|ignore|unknown",
      "trust": "trusted|untrusted|quarantined|unknown",
      "scores": { "fts": 12.3, "semantic": null, "rrf": null },
      "decision": {
        "included": true,
        "reason": ["high_score", "must_remember", "within_budget"],
        "caps": { "niceCapHit": false, "l2CapHit": false }
      },
      "citations": {
        "url": null,
        "recordRef": "(stable ref; no private paths)"
      }
    }
  ],
  "output": {
    "includedCount": 8,
    "excludedCount": 42,
    "l2IncludedCount": 1,
    "citationsCount": 2
  },
  "timing": {
    "durationMs": 83
  }
}
```

Notes:
- **Do not** include raw content, absolute local paths, or secrets.
- It must be stable enough to diff across versions and to support `openclaw-memory-bench` policy comparisons.

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

### 6) Graph semantic memory (idea → project matching)

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

### 7) User/System separation (upgrade-safe operator state)

Deliverables:
- Clear boundary of **user-owned** vs **system-owned** files/config
- Schema versioning + migration notes (compat layer for old records)

Acceptance criteria:
- Upgrades do not rewrite operator state.
- Old DB/records remain readable.

### 8) Observability & hooks (receipts everywhere)

Deliverables:
- Standardized run summaries for ingest/harvest/triage
- Drift detection for label distribution (e.g., `must_remember` suddenly spikes)
- **Compaction receipts (future)**: capture `before_compaction/after_compaction` lifecycle events into the sidecar ledger so operators can audit “what got summarized” vs “what stayed hot”.
- **Manual `/compact` flush hook (upstream, future)**: when an operator triggers `/compact`, run a pre-compaction memory flush *first* (configurable), then compact. This reduces “oops I compacted before writing durable notes”.

Acceptance criteria:
- Any automated path can be validated via logs + JSON summary.

### 9) Feedback loop (operator corrections → better behavior)

Deliverables:
- Minimal manual override flow (mark/adjust importance)
- Track correction counts + scorer error counts

- **Learning records (self-improvement loop; PAI-inspired, openclaw-mem-governed)**:
  - A structured record type (warm tier) that can store:
    - mistakes / incidents (what happened)
    - resolution / mitigation (what to do next time)
    - tags (tool/provider/project)
    - provenance + trust tier + redaction posture
  - Ingestion path (local-first, idempotent):
    - import from `.learnings/` markdown templates (or a JSONL variant)
    - emit a receipt: total imported, new vs duplicate, top recurring patterns
  - Retrieval path:
    - allow `pack` to include the top-N relevant learning records when the query matches an error/tool/workflow

Acceptance criteria:
- Operators can correct mistakes and see the system behave differently afterward.
- Import is **idempotent** (re-running doesn’t spam duplicates).
- Learning-record outputs are redaction-safe by default (aggregate receipts; content only on explicit request).

### 10) Pruning-safe capture profiles (future)

Goal: make OpenClaw session pruning safer by ensuring important tool outputs remain retrievable locally.

Deliverables:
- Capture profiles that are safe by default:
  - `metadata-only` (always safe)
  - `summary-only` (current default)
  - `head-tail` (bounded content)
- Explicit allowlist/denylist support per tool, with redaction on.

Acceptance criteria:
- Operators can enable aggressive pruning without losing the ability to recover key tool outcomes from `openclaw-mem`.

### 11) Contract hardening (interface-first) — stable schemas + fail-fast validation

Goal: reduce “silent drift” by treating CLI outputs + configs as **interfaces** with explicit contracts.

Deliverables:
- **Stable JSON output schemas (v0)** for key operator surfaces:
  - `harvest --json` summary (`total_seen`, `graded_filled`, `skipped_existing`, ...)
  - `triage --json` (`needs_attention`, `found_new`, ...)
  - `pack --trace` receipt (`openclaw-mem.pack.trace.v1`)
- **Schema tests** (unit-level) that verify:
  - required keys exist
  - types are stable
  - unknown keys are either rejected (strict) or explicitly tolerated (documented)
- **Strict config contract** where feasible:
  - plugin config schema uses `additionalProperties: false` (or equivalent) to surface misconfig early
- `profile` / stats surface (**DONE**):
  - `openclaw-mem profile --json` for deterministic ops snapshots (counts, importance distribution, recent rows, embedding stats)

Acceptance criteria:
- A breaking shape change fails tests before release.
- Cron/ops can rely on JSON outputs without regex-parsing or brittle prompt assumptions.

## Later (optional, higher ambition)

- Hybrid improvements: rerank / eval harnesses
- Additional scorers (LLM-assisted grading as **opt-in**, with strict cost caps)
- Optional protocol adapters (e.g., MCP-compatible surfaces) **without** losing local-first defaults

## Thought links (design references)

These are projects we referenced and **actually used** to shape features or architecture.

- Daniel Miessler — *Personal AI Infrastructure (PAI)*: <https://github.com/danielmiessler/Personal_AI_Infrastructure>
  - Used as an architectural checklist (memory tiers, hooks, user/system separation, continuous improvement).

- 好豪 — *MCP Tool Search：Claude Code 如何終結 Token 消耗大爆炸*: <https://haosquare.com/mcp-tool-search-claude-code/>
  - Used to justify the “**card → manual**” split and dynamic discovery pattern for SOP/skills (context-size friendly).

- `tobi/qmd`: <https://github.com/tobi/qmd>
  - Used to shape our hybrid retrieval direction (FTS5/BM25 + vectors + fusion + rerank) and the benchmarking plan for a “retrieval router” arm.

- 1Password — *From magic to malware: How OpenClaw's agent skills become an attack surface*: <https://1password.com/blog/from-magic-to-malware-how-openclaws-agent-skills-become-an-attack-surface>
  - Used to motivate provenance + trust tiers and “trust-aware” context packing (helpful content can still be hostile).

- `thedotmack/claude-mem`: <https://github.com/thedotmack/claude-mem>
  - Strong early inspiration for an agent memory layer design; we credit it explicitly (see `ACKNOWLEDGEMENTS.md`).

- `volcengine/OpenViking`: <https://github.com/volcengine/OpenViking>
  - Used as a design reference for layered context loading (L0/L1/L2) and retrieval observability (trajectory/trace). Thought-link only; not a backend commitment.

- Reference-based decay / archive-first lifecycle (trusted background + field note):
  - Cepeda et al. (2006) distributed practice / spaced repetition: <https://doi.org/10.1037/0033-2909.132.3.354>
  - ARC cache replacement (recency+frequency): <https://www.usenix.org/legacy/publications/library/proceedings/fast03/tech/full_papers/megiddo/megiddo.pdf>
  - X thread (untrusted inspiration): <https://x.com/ohxiyu/status/2022924956594806821>
