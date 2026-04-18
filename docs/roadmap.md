# Roadmap

This roadmap translates design principles from *personal AI infrastructure* into concrete, testable work items for `openclaw-mem`.

Guiding stance: ship early, stay local-first, and keep every change **non-destructive**, **observable**, and **rollbackable**.

Status tags used here: **DONE / PARTIAL / ROADMAP**.

## Principles (what we optimize for)

- **Sidecar-first, optional slot owner**: `openclaw-mem` remains the ops sidecar by default. We may additionally ship an optional slot backend (**openclaw-mem-engine**) to replace `memory-lancedb` when enabled — still rollbackable via a one-line slot switch.
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

### 0) OpenClaw Mem Engine (optional memory slot backend)

Status: **DONE (M1 shipped)**.

- Goal: replace `memory-lancedb` with a slot backend that supports **hybrid recall (FTS + vector)**, **scopes**, and **auditable policies**.
- Why: the official backend currently uses LanceDB mostly as a basic vector store; it doesn’t expose hybrid/FTS/index lifecycle/versioning.
- Design doc: [OpenClaw Mem Engine →](mem-engine.md)

Add-on (critical UX win, no local LLM):
- **Docs memory**: index operator-authored repos (DECISIONS / roadmaps / specs) as a recall surface and include it as a cold lane.
  - Spec: [Docs memory (hybrid search v0) →](specs/docs-memory-hybrid-search-v0.md)

Acceptance criteria:
- Slot switch + rollback is one line (`plugins.slots.memory`).
- `memory_store/memory_recall/memory_forget` emit JSON receipts (filters, latency, counts).
- M1 delivers a “concept → decisions/preferences” golden set where hybrid beats vector-only.

### 1.7) Graphic Memory consumption (triggered preflight → pack integration)

Status: **PARTIAL** (graph-aware synthesis preference now applies inside ordinary `pack`; broader triggered preflight integration remains additive).

- Problem: Graphic Memory has working auto-capture and `graph preflight`, but it is not yet **routinely consumed** in doc/decision/dependency lookup flows.
- Plan (two-step):
  1) Spec-level: add a deterministic, bilingual trigger policy for when to run `graph preflight` (soft + fail-open).
  2) Product-level: integrate the same trigger into `openclaw-mem pack` / `hybrid` via `--use-graph=auto` (default OFF).

Artifacts:
- Spec: `docs/specs/graphic-memory-preflight-trigger-policy.md`

Acceptance criteria:
- `pack` behavior unchanged when graph is OFF.
- In `--use-graph=auto`, trigger is deterministic + traceable (`--trace` shows trigger reason).
- Graph failures are fail-open and never break pack.
- Ordinary `pack` can prefer a covering synthesis card over raw covered refs without requiring `--use-graph=on`.
- Golden regression scenarios exist for pack policy, protected tail, and graph-auto trigger behavior.

### 1.7a) Graphic Memory query plane (operator-facing graph interface)

Status: **PARTIAL** (query-plane foundation + deterministic query CLI shipped; deeper provenance integration pending).

- Problem: operators need a practical query layer over stable topology + runtime drift + provenance, but today those relationships are scattered across YAML, cron state, and receipts.
- Decision: keep repo-backed topology as the source of truth; add a **derived query plane** under `openclaw-mem`.
- Target architecture:
  - source of truth = structured files (YAML / markdown / receipts)
  - derived cache = SQLite graph tables
  - first shippable slice = YAML-only query helper for one-hop operator questions
- Shipped slice (Unreleased):
  - deterministic query-plane foundation module + SQLite refresh contract
  - `graph query` commands for `upstream` / `downstream` / `lineage` / `writers` / `filter`
  - `graph query drift --live-json <path> --db <path>` for stable-topology vs runtime-state checks
- Initial operator questions:
  - what depends on this node?
  - what does this node feed/write?
  - which jobs write this artifact?
  - which jobs are background but not human-facing?
  - where does graph truth drift from live state?

Artifacts:
- Spec: `docs/specs/graphic-memory-query-plane-v0.md`

Acceptance criteria:
- YAML remains the editable truth; the derived graph is rebuildable/disposable.
- A-fast can ship bounded query value before SQLite lands.
- A-deep installs deterministic refresh + drift/provenance boundaries.
- Runtime graph failures remain fail-open and do not break baseline memory/pack flows.

### 1.7b) Automatic topology seed (repo map → topology YAML)

Status: **ROADMAP**.

- Problem: our topology surfaces are still curated/demo-first; new repos/jobs/artifacts don’t automatically appear unless a human updates topology files.
- Goal: ship a deterministic extractor that can generate a minimal, reviewable topology seed from the workspace + cron registry.
- Non-goals: no LLM extraction, no implicit trust promotion, and no silent overwrites of operator-authored topology.

Plan (v0):
1) Build a `topology-seed` from deterministic sources:
   - `/root/.openclaw/cron/jobs.json` (job ids, schedules, delivery targets)
   - playbook cron job specs (`openclaw-async-coding-playbook/cron/jobs/*.md`)
   - workspace repo roots (git + directory metadata only)
2) Output a small YAML/JSON file + receipt (counts, provenance groups).
3) Optional: “suggest-only” diff against a curated topology file.

Acceptance criteria:
- One command can regenerate the seed deterministically and produce a receipt.
- Seed output is provenance-first and safe to commit (no secrets, no raw content).

Artifacts:
- Spec: `docs/specs/topology-auto-extract-v0.md`

### 1.7c) Compiled synthesis layer (selected refs → maintained synthesis cards)

Status: **PARTIAL** (`graph synth compile` / `graph synth stale` / deterministic `graph lint` shipped; graph preflight and graph pack now prefer fresh synthesis cards; deterministic review/contradiction signals now surface in stale/lint; richer maintenance still pending).

- Problem: Graphic Memory can capture refs and build bounded preflight/query bundles, but it still has to re-derive many high-value cross-source conclusions from scratch.
- Goal: add a small, provenance-carrying **compiled synthesis layer** that turns selected refs into reusable synthesis cards with a stale/lint loop.
- Non-goals: no graph DB, no UI/Obsidian dependency, no automatic wiki-writing loop, and no topology-source-of-truth changes.

Plan (v0):
1) Reuse existing selection surfaces (`graph index` / `graph preflight` / explicit record refs) as inputs.
2) Add `graph synth compile` to emit a bounded synthesis-card receipt (+ optional Markdown materialization).
3) Add `graph synth stale` and deterministic `graph lint` checks.
4) Shipped in the graph-preflight lane: prefer fresh synthesis cards before replaying many covered raw refs.
5) Shipped in the graph-pack lane: when explicit refs are covered by a fresh synthesis card, prefer the card and surface the preference receipt.
6) Shipped in main `pack --use-graph`: record graph-consumption receipts and elide raw L1 lines already covered by preferred synthesis cards in the combined graph-aware bundle.
7) Shipped in `cmd_hybrid`: prefer fresh synthesis cards in top results when they cover multiple high-ranked raw hits, with explicit graph-consumption receipts.
8) Shipped in `graph synth refresh`: replay the old card selection, emit a fresh replacement card, and mark the old card as superseded with lifecycle receipts.
9) Shipped in `graph lint`: coverage pressure / `candidateCardSuggestions` using scope + repeated-keyword clusters for uncovered areas not yet covered by active synthesis cards.
10) Shipped in `search`: prefer fresh synthesis cards in top results when multiple matched raw hits are covered by the same card, with graph-consumption receipts.
11) Later, extend synthesis-card preference more broadly in other pack/retrieval lanes where it remains truthful.

Acceptance criteria:
- A user can compile a reusable synthesis card from bounded refs with provenance.
- Staleness is detectable without an LLM.
- Graph failures remain fail-open and do not break baseline preflight/pack flows.

Artifacts:
- Spec: `docs/specs/graphic-memory-compiled-synthesis-v0.md`

### 1.6) Sunrise rollout (Stage A→B→C)

Status: **PARTIAL** (Stage A running; Stage B/C pending).

- Stage A: background writeback cron (no slot switch)
- Stage B: daily canary slot switch + golden-set recall check
- Stage C: live switch with auto-downgrade guard

Acceptance criteria:
- Stage A runs stably for 3 days: `missingIds=0`, `error_count=0`.
- Stage B canary passes 3 consecutive days: engine recall returns receipts with `policyTier` + `ftsTop/vecTop` and no tool errors.
- Stage C is only enabled after A+B are green.

### 1.6a) Read-only lane enforcement ladder (sidecar-first deployments)

Status: **ROADMAP**.

- Problem: in sidecar-only deployments, “read-only lanes” are still mostly a prompt/runner discipline; `exec` is the main escape hatch.
- Goal: make read-only posture enforceable (tool surface + script-only exec + sandbox) so we can expand unattended coverage safely.

Phase plan (suggested):
- Phase 0: prompt-layer read-only card + silent-on-green (today)
- Phase 1: tool allowlists deny memory writes + file writes; scripts-first jobs
- Phase 2: sandbox `exec` (script-only wrapper + OS-level restrictions)
- Phase 3: widen coverage + add sunrise watchers for each new surface

Acceptance criteria:
- A cron lane can prove “read-only” via receipts (allowed scripts + expected state paths only).
- Rollback is one command (disable the job / remove profile) and restores baseline behavior.

Artifacts:
- Ops backlog (host): `/root/.openclaw/workspace/openclaw-async-coding-playbook/projects/openclaw-ops/ops/PRODUCT_GAPS_BACKLOG.md`

### 1.5) Writeback + recall policy loop (M1.5)

Status: **PARTIAL**.

- Add a bounded `openclaw-mem writeback-lancedb` path that pushes graded metadata from SQLite into LanceDB by row ID.
- Default recall policy for `memory_recall` is fail-open:
  1. must_remember + nice_to_have
  2. +unknown
  3. +ignore
- Receipt must expose `policyTier` used (`must+nice`, `must+nice+unknown`, `must+nice+unknown+ignore`) for diagnostics.

Acceptance criteria:
- A smoke writeback run updates `importance`, `importance_label`, `scope`, `trust_tier`, `category` only when missing.
- Empty-policy recall returns `ignore` tier and still yields results if any memory exists.
- receipts include both engine and writeback summaries.

### 1.5a) Self-optimizing memory loop (shadow/recommendation-first)

Status: **PARTIAL** (v0.1 recommendation observer shipped; apply path still roadmap).

- Problem: the memory layer can capture and recall, but does not yet systematically learn from repeated misses, user corrections, low-value recalls, or strong evidence that certain memories should be promoted/demoted/merged.
- Decision: add a conservative loop:
  - observe
  - propose
  - verify
  - optionally apply (later, low-risk only)
- v0 posture:
  - recommendation/shadow mode only
  - no autonomous prompt rewriting
  - no silent deletion
  - no hidden config mutation

Shipped v0.1 slice:
- `openclaw-mem optimize review` (zero-write observer/reporter)
- bounded source-of-truth scan (`observations`, default limit 1000)
- low-risk signals: staleness, duplication, bloat, weakly-connected candidates, repeated no-result `memory_recall` miss patterns
- outputs structured report `openclaw-mem.optimize.review.v0` with recommendations (no mutation)

Artifacts:
- Spec: `docs/specs/self-optimizing-memory-loop-v0.md`

Acceptance criteria:
- proposal generation does not mutate source truth by default
- proposal receipts are inspectable and bounded
- the loop is fail-open; disabling it preserves current behavior
- only low-risk metadata changes are even considered for future auto-apply

### 1) Importance grading rollout (MVP v1)

Status: **PARTIAL** (baseline shipped; benchmark pass pending).

- [x] Canonical `detail_json.importance` object + thresholds
- [x] Deterministic `heuristic-v1` + unit tests
- [x] Feature flag for autograde: `OPENCLAW_MEM_IMPORTANCE_SCORER=heuristic-v1`
- [x] Ingest wiring: only fill missing importance; never overwrite; fail-open
- [x] CLI override: `--importance-scorer {heuristic-v1|heuristic_v1|off}` for `ingest`/`harvest` (env fallback remains)
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

Add-on (debuggability + governance):
- **Episodic events ledger** (append-only session timeline; summary-first; scope-isolated)
  - Spec: [Episodic events ledger (v0) →](specs/episodic-events-ledger-v0.md)

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
- A stable **ContextPack** output contract (hybrid text + JSON) for injection + ops tooling:
  - `openclaw-mem.context-pack.v1`
  - See: `docs/context-pack.md`
  - Status: shipped baseline in `openclaw-mem pack` as `context_pack`; future changes should extend compatibly
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
  - Include a minimal JSON schema (v1) so we can diff behavior over time and compare arms in benchmarks.
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
  - Lexical (SQLite FTS5; BM25 scoring; QMD-style)
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

Status: **PARTIAL** (v0 graph surfaces exist; idea→project matching policy not yet shipped).

Goal: represent projects/decisions/concepts as typed entities + edges so we can recommend work with **path justification**.

Deliverables:
- Minimal entity/edge schema (typed)
- Ingest adapter that builds a graph view from:
  - digests, scout reports, decisions
- v0 automation surfaces (dev):
  - [x] `graph index` / `graph pack` / `graph export` (graph-first index + packing + export)
  - [x] `graph preflight` (deterministic recall pack preflight)
  - [x] `graph capture-git` (commit capture)
  - [x] `graph capture-md` (index-only markdown capture)
  - [x] `graph auto-status` and env toggles (`OPENCLAW_MEM_GRAPH_AUTO_RECALL`, `OPENCLAW_MEM_GRAPH_AUTO_CAPTURE`, `OPENCLAW_MEM_GRAPH_AUTO_CAPTURE_MD`)
- Next-value layer:
  - compiled synthesis cards + stale/lint loop over selected refs
  - Spec: `docs/specs/graphic-memory-compiled-synthesis-v0.md`
- Query path (target):
  - `idea/query → top projects → explanation path`
- Storage posture:
  - stay with portable / derived graph artifacts first (SQLite + receipts + optional Markdown materialization)
  - defer dedicated graph-store evaluation until compiled synthesis and query quality prove the need

Acceptance criteria:
- Given an idea, we can point to 3–10 candidate projects/tasks with a human-readable justification path.
- High-value repeated cross-source conclusions can be reused as fresh synthesis cards instead of being re-derived every time.

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
  - Used to shape our hybrid retrieval direction (FTS5 (BM25 scoring) + vectors + fusion + rerank) and the benchmarking plan for a “retrieval router” arm.

- 1Password — *From magic to malware: How OpenClaw's agent skills become an attack surface*: <https://1password.com/blog/from-magic-to-malware-how-openclaws-agent-skills-become-an-attack-surface>
  - Used to motivate provenance + trust tiers and “trust-aware” context packing (helpful content can still be hostile).

- `thedotmack/claude-mem`: <https://github.com/thedotmack/claude-mem>
  - Strong early inspiration for an agent memory layer design; we credit it explicitly (see `ACKNOWLEDGEMENTS.md`).

- `volcengine/OpenViking`: <https://github.com/volcengine/OpenViking>
  - Used as a design reference for layered context loading (L0/L1/L2) and retrieval observability (trajectory/trace). Thought-link only; not a backend commitment.

- `martian-engineering/lossless-claw` (LCM / lossless context engine): <https://github.com/martian-engineering/lossless-claw>
  - Used as a design reference for **fresh-tail protection**, provenance-first summarization, and “expand for details” tooling. Thought-link only; we are not committing to an engine fork.

- Reference-based decay / archive-first lifecycle (trusted background + field note):
  - Cepeda et al. (2006) distributed practice / spaced repetition: <https://doi.org/10.1037/0033-2909.132.3.354>
  - ARC cache replacement (recency+frequency): <https://www.usenix.org/legacy/publications/library/proceedings/fast03/tech/full_papers/megiddo/megiddo.pdf>
  - X thread (untrusted inspiration): <https://x.com/ohxiyu/status/2022924956594806821>
