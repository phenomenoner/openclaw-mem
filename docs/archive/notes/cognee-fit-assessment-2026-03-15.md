# Cognee fit assessment for openclaw-mem

Date: 2026-03-15
Target repo: `openclaw-mem`
Upstream repo: `topoteretes/cognee`
Status: docs-only analysis
Topology check: no topology change proposed in this document

## Executive summary

Decision: **selective absorption is worth it; full-stack adoption is not.**

`cognee` is strongest as a reference for retrieval orchestration, enrichment pipelines, and graph-aware recall. `openclaw-mem` should borrow the parts that tighten recall quality, lifecycle signals, and query routing, while avoiding a heavyweight knowledge-engine rewrite that would cut against its local-first, sidecar-first, receipts-first posture.

## What Cognee is actually building

Cognee behaves like a general knowledge engine built around a reusable loop:

- `add -> cognify -> search` as the primary pipeline
- dual retrieval substrate: vector + graph retrieval
- composable enrichment / memify pipelines
- session and feedback hooks that can affect retrieval behavior
- pipeline run states, telemetry, and tenant-aware authorization edges
- advanced lanes such as temporal retrieval and ontology resolution

That makes Cognee broader than a memory plugin. It is an extensible ingestion and retrieval platform.

## Overlap vs gap

### Overlap

- local-first memory and operator control matter in both projects
- hybrid retrieval is already present in `openclaw-mem`
- graph-aware surfaces already exist in `openclaw-mem`
- both care about session continuity and recall quality

### Gap

- Cognee has deeper, first-class KG extraction pipelines
- Cognee has a clearer retrieval mode registry and mode selection surface
- Cognee has an explicit feedback-to-weighting loop
- Cognee has tenant / ACL concerns that are broader than current `openclaw-mem` scope
- Cognee has more mature temporal and ontology lanes than `openclaw-mem` today

## Top 5 absorbable features and designs

### 1) Real usage-stamp updates from retrieval inclusion

- **What it is**: update a record-level usage signal such as `last_used_at` when a memory item is actually selected into recall results, not just when it was created or shadow-touched.
- **Why it matters**: gives lifecycle policy a real notion of live usefulness.
- **Fit**: High
- **Implementation difficulty**: Small
- **Likely touchpoints**:
  - `openclaw_mem/cli.py`
  - lifecycle / pack / recall receipt paths
  - `docs/archive/notes/lifecycle-ref-decay.md`
  - `docs/roadmap.md`
- **Risks / non-fits**:
  - write amplification if naively updated per item
  - should remain batched, reversible, and fail-open

### 2) Feedback-weighted recall signal loop

- **What it is**: let operator or assistant feedback influence future retrieval weighting without rewriting the original memory payload.
- **Why it matters**: closes the loop between recall quality and real user usefulness.
- **Fit**: High
- **Implementation difficulty**: Medium
- **Likely touchpoints**:
  - `openclaw_mem/optimization.py`
  - recall / scoring paths in `openclaw_mem/cli.py`
  - `docs/specs/self-optimizing-memory-loop-v0.md`
- **Risks / non-fits**:
  - sparse or noisy feedback can overfit
  - aggregation must respect scope and operator boundaries

### 3) Retrieval strategy registry and router

- **What it is**: formalize retrieval strategies behind a small policy / enum surface such as lexical, hybrid, graph-assisted, and temporal.
- **Why it matters**: makes recall behavior easier to test, trace, and version.
- **Fit**: High
- **Implementation difficulty**: Medium
- **Likely touchpoints**:
  - `openclaw_mem/cli.py`
  - `openclaw_mem/pack_trace_v1.py`
  - `docs/context-pack.md`
  - `docs/roadmap.md`
- **Risks / non-fits**:
  - avoid turning the router into a vague LLM-only classifier
  - keep deterministic fallback simple and explicit

### 4) Temporal-intent retrieval lane

- **What it is**: detect queries like “since last week”, “between X and Y”, or “what changed” and bias / filter episodic recall accordingly.
- **Why it matters**: many memory tasks are really time-bounded change-detection tasks.
- **Fit**: Medium-High
- **Implementation difficulty**: Medium
- **Likely touchpoints**:
  - `openclaw_mem/cli.py`
  - `cmd_timeline`, episodic query, and pack flows
  - `docs/specs/episodic-events-ledger-v0.md`
- **Risks / non-fits**:
  - time parsing ambiguity
  - must degrade cleanly into ordinary retrieval

### 5) Lightweight ontology / alias grounding

- **What it is**: maintain a practical alias and type-normalization layer for recurring entities such as repos, tools, projects, and decisions.
- **Why it matters**: reduces entity duplication and improves graph / provenance coherence.
- **Fit**: Medium
- **Implementation difficulty**: Medium
- **Likely touchpoints**:
  - `openclaw_mem/docs_memory.py`
  - `openclaw_mem/graph/topology_extract.py`
  - `openclaw_mem/graph/query.py`
  - a new spec under `docs/specs/`
- **Risks / non-fits**:
  - full ontology stacks are likely overkill for current scope
  - taxonomy maintenance can sprawl if not tightly bounded

## Design principles worth borrowing

- Keep advanced behavior behind composable pipelines with explicit task boundaries
- Preserve fail-open behavior for non-critical enrichments
- Treat retrieval observability as a stable contract, not best-effort logging
- Separate the fast core path from optional enrichment paths
- Keep authorization and scope checks at the edges, even without full multi-tenant complexity

## Recommended adoption order

1. Real usage-stamp updates from retrieval inclusion
2. Retrieval strategy registry and router
3. Temporal-intent retrieval lane
4. Feedback-weighted recall signal loop
5. Lightweight ontology / alias grounding

Rationale: the first three are foundation upgrades that improve lifecycle truth, query behavior, and observability quickly. The latter two are valuable, but they depend more heavily on data quality, governance, and longer-tail tuning.

## What not to copy

- a full knowledge-graph-first platform rewrite
- heavyweight multi-tenant ACL machinery
- broad ontology infrastructure before practical alias pain is proven
- enrichment complexity that compromises deterministic local-first fallback paths

## Suggested next-step implementation slices

### Slice A: lifecycle truth
- add batched `last_used_at` updates on actual retrieval inclusion
- expose the mutation in trace / receipt output
- document decay / archive policy implications

### Slice B: routing contract
- define a small retrieval-strategy enum and router contract
- record the chosen strategy in pack traces
- keep deterministic fallback behavior explicit

### Slice C: time-aware recall
- add a minimal temporal-intent detector
- bias / filter episodic recall by extracted interval
- fall back to ordinary hybrid retrieval on parse failure

## Final recommendation

Borrow **design discipline and narrow feature slices**, not Cognee’s full stack. The right move for `openclaw-mem` is to improve lifecycle truth, routing clarity, and time-aware recall while staying faithful to local-first governance and receipts.
