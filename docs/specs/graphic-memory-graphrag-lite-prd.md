# PRD — Graphic Memory (GraphRAG-lite) for openclaw-mem

## 1) Problem statement
Operators want **associative / analogical recall**:

> Given an input idea/data point A → find related context + linked items (within the same project and across projects) → inject a *bounded*, *traceable* context pack into the LLM so it can reason better (e.g., reuse a concept/workflow from Project X in Project Y).

Today, `openclaw-mem` has strong **progressive disclosure** on *rows* (`search → timeline → get`) and a (dev) **Context Packer** (`pack --trace`), but it lacks a **graph neighborhood retrieval** layer that can justify “why these items are related” and support cross-project association without dumping raw text.

## 2) Evidence / provenance (facts only)
- `openclaw-mem` architecture explicitly calls out:
  - **Layer contract (L0/L1/L2)** for context loading, and
  - **Graph semantic memory** as a roadmap item (typed edges + path justification).
  - Source: `openclaw-mem/docs/architecture.md`
- `openclaw-mem` roadmap states `pack --trace` hardening is Pillar A, and graph semantic memory is not implemented yet.
  - Source: `openclaw-mem/docs/roadmap.md`
- `openclaw-mem` already supports `pack` with a redaction-safe trace receipt (dev), but it is not auto-wired as the default per-request feeder.
  - Source: `openclaw-mem/README.md` + `openclaw-mem/docs/automation-status.md`
- We already curate “thought-links” that connect design references (Observational Memory / LongMemEval / OpenViking L0-L2 patterns) into actionable constraints.
  - Source: `openclaw-mem/docs/thought-links.md`
- GitHub Expedition command-center has identified viewer/schema-extraction directions and optional KG MCP references for future exploration.
  - Source: `openclaw-async-coding-playbook@0e13ca5` (`projects/github-expedition/*`)

## 3) Goals (outcomes)
- G1: Provide an **index-first** graph retrieval lane that can answer: “what related context exists?” with minimal tokens.
- G2: Provide a **progressive disclosure** injection mechanism (L0 → L1 → L2) that stays within hard budgets and is safe-by-default.
- G3: Provide **path justification + provenance** so every injected item is explainable and debuggable.
- G4: Keep the system **non-destructive, observable, and rollbackable** (disable the graph lane without breaking base recall).

## 4) Non-goals (explicitly out of scope)
- NG1: Full KG extraction (entity canonicalization / alias resolution / ontology design) in v1.
  - Why: large scope + high risk of wrong merges and hallucinated edges.
- NG2: Introducing a dedicated graph database (Neo4j/Kuzu/etc.) as a hard dependency in v1.
  - Why: premature coupling; start with a portable representation.
- NG3: Auto-wiring into OpenClaw runtime as default memory for all requests.
  - Why: `pack` promotion gate + privacy/ops confidence must come first.

## 5) Users / personas
- Primary: **OpenClaw agent runtime / packer** (needs a deterministic, bounded context pack).
- Secondary: **Operator (CK / engineers)** (needs observability, debugging, and governance controls).

## 6) User stories (priority order)
1) As an agent/runtime, I want to request a **Graph IndexPack (L0)** so I can decide whether deeper context is needed.
2) As an agent/runtime, I want to request a **Graph ContextPack (L1)** for a chosen set of nodes so I can reason with relevant summaries.
3) As an operator, I want to see **why** a node/edge was included (path + provenance) so I can trust the injection and fix bad edges.
4) As an operator, I want the system to be safe-by-default (no raw sensitive dumps) and easy to disable.

## 7) Requirements

### P0 (must-have)

#### R0.1 Project-scoped graphs + controlled cross-project edges
- Default: **one graph per project**.
- Cross-project edges are allowed but must be **explicitly gated** (see acceptance).
  - Acceptance:
    - Given `project=finlife`, When `graph_index` is called, Then results are limited to finlife graph unless `allow_cross_project=true`.
    - Cross-project edges must carry an explicit `edge_reason` and provenance.

#### R0.2 Stable, portable graph artifact
- Provide a deterministic export artifact:
  - `graph.json` (or equivalent) with:
    - nodes: `id`, `type`, `title`, `project`, `l0_abstract`, `l1_summary_ref`, `provenance`, `tags`
    - edges: `src`, `dst`, `type`, `weight(optional)`, `reason`, `provenance`
- Acceptance:
  - Export is reproducible from the same inputs (stable ordering + stable ids).

#### R0.3 Index-first retrieval API (L0)
- Implement `graph_index(query, project_scope, k)` that returns an **IndexPack**:
  - `top_candidates[]` (id/title/type/project/score/why_relevant)
  - `suggested_next_expansions[]` (node ids + reasons)
- Default L0 budget target: **800–1000 tokens**.
  - Acceptance:
    - Output must include a `budget` field and never exceed configured caps.

#### R0.4 Progressive disclosure packing (L1/L2)
- Implement `graph_pack(node_ids, depth, budget_tokens, mode=safe)` that returns:
  - L1 summaries with provenance (default)
  - Optional L2 snippets (only when explicitly requested)
- Budgets:
  - L1 typical: 800–2000 tokens
  - L2 ceiling: 3000 tokens total; per-snippet hard cap.
- Acceptance:
  - In safe mode, raw content is excluded by default.
  - Every item includes provenance + why-included.

#### R0.5 Trace receipts (debuggability)
- Extend the existing `pack --trace` concept to cover graph lane decisions:
  - lanes searched
  - candidates considered
  - include/exclude reasons
  - path justification for graph expansions
- Acceptance:
  - Trace output is **redaction-safe** and machine-readable.

#### R0.6 Kill-switch and failure posture
- Provide a configuration switch to disable graph lane (or cross-project edges) without breaking base recall.
- Failure must be **fail-open**: graph errors do not break `pack`.
  - Acceptance: if graph build/query fails, `pack` still produces a baseline bundle and marks graph lane as failed in trace.

### P1 (nice-to-have)

#### R1.1 Viewer for operators (debug/QA)
- A local viewer that loads exported graph artifacts and supports:
  - filter by project/type/tag
  - inspect node provenance
  - view the path that caused inclusion
  - diff two exports (added/removed nodes/edges)

#### R1.2 Graph-aware `pack` integration
- Add `--use-graph` (or similar) option to `openclaw_mem pack`:
  - stage 1: base retrieval
  - stage 2: graph neighborhood expansion
  - stage 3: budgeted inclusion

### P2 (future considerations)
- Entity/KG extraction lane (concept ids, aliases, conflict handling)
- Stronger cross-project recommendation engine with evaluation harness
- Optional graph backend interface (SQLite adjacency vs Kuzu) behind a trait

## 8) Acceptance criteria (system-level)
- [ ] Given an input query A and a project scope, the system produces an IndexPack (L0) within the budget target.
- [ ] Given selected node_ids, the system produces a ContextPack (L1) with provenance and include/exclude rationale.
- [ ] Cross-project expansions are gated and always justified.
- [ ] Trace receipts are redaction-safe and sufficient to debug why something was injected.
- [ ] Disabling the graph lane restores baseline `pack` behavior (no regression).

## 9) Success metrics
### Leading (days–weeks)
- Metric: % of packs with complete provenance coverage (baseline=TBD, target=TBD, window=2 weeks)
- Metric: operator-rated “relevance of injected context” on a small labeled set (baseline=TBD, target=TBD)
- Metric: average pack size vs budget (baseline=TBD, target=TBD)

### Lagging (weeks–months)
- Metric: reduction in “context thrash” incidents (cases where the agent re-asks already-known context) (baseline=TBD)
- Metric: improved idea→project matching quality on a benchmark task set (baseline=TBD)

## 10) Risks & mitigations (ROAM)
- Risk: Graph expansions introduce low-signal context and distract reasoning.
  - Status: Mitigated
  - Mitigation: index-first; explicit budget caps; include/exclude rationale; cross-project gating.
- Risk: Privacy leaks via snippets.
  - Status: Mitigated
  - Mitigation: safe-by-default pack; per-snippet hard caps; redaction rules.
- Risk: Over-commit to a graph backend.
  - Status: Accepted
  - Mitigation: v1 uses portable export + minimal in-memory adjacency.

## 11) Dependencies / constraints
- Depends on existing `pack --trace` contract direction (Pillar A).
- Must remain local-first and usable without external services.
- Must not require new long-lived daemons.

## 12) Rollout / launch considerations
- Rollout: dev-only first (behind feature flags), then promotion gate to main after:
  - deterministic export, trace schema tests, and operator sign-off.
- Kill-switch: `--no-graph` or config flag to disable graph lane / cross-project edges.

## 13) Open questions
- (Blocking) What is the minimal **project scope identifier** (repo path? tag? explicit project id)?
- (Blocking) What are the initial node types we commit to (Project/Decision/Task/Report/ThoughtLink/etc.)?
- (Non-blocking) Do we want graph export to be derived from SQLite only, or also from curated markdown (playbook) as first-class inputs?
- (Non-blocking) Cross-project edge gating: should it be allowlist-driven (only a few edge types)?

## 14) Assumptions (explicit)
- A1: A link-graph (typed links + provenance) is sufficient to deliver useful association before full entity-KG work.
- A2: Operators prefer **progressive disclosure** over large one-shot context dumps, even when the model can technically ingest larger packs.

## 15) Handoff payload (for marketing)
- Target audience: operators building always-on OpenClaw agents.
- Primary value prop: associative recall with bounded, traceable context packs (debuggable, safe-by-default).
- Key objections: “graphs are hype”, “will this leak private data?”, “will it bloat prompts?”
- Available proof points (with sources): existing `pack --trace` + L0/L1/L2 design and receipts (`docs/architecture.md`, `docs/roadmap.md`).
- CTA: try IndexPack + ContextPack locally; inspect trace receipts.
