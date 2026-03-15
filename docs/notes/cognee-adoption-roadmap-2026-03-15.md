# Cognee selective-adoption roadmap for openclaw-mem

Date: 2026-03-15
Basis: `docs/notes/cognee-fit-assessment-2026-03-15.md`
Status: planning / backlog only
Topology check: no topology change proposed in this document

## Decision

Adopt Cognee-inspired improvements as **narrow, receipts-first slices**.
Do **not** attempt a full knowledge-engine transplant.

The right adoption order is:
1. lifecycle truth (`last_used_at` on real retrieval inclusion)
2. retrieval strategy registry + router
3. temporal-intent retrieval lane
4. feedback-weighted recall loop
5. lightweight alias grounding

## Why this order

- The first three improve correctness and observability without changing the product thesis.
- They fit `openclaw-mem`'s local-first and fail-open posture.
- The last two are valuable but introduce more governance, tuning, and quality-drift risk.

## Backlog

### OCM-CG-01 — retrieval inclusion refreshes lifecycle usage
**Priority:** P1
**Goal:** update lifecycle metadata when a record is actually selected into recall results.

**Scope**
- batch `last_used_at` updates for records actually included in recall / pack results
- expose the refresh in trace / receipt output
- keep writes fail-open and low-amplification

**Likely touchpoints**
- `openclaw_mem/cli.py`
- recall / pack selection paths
- trace / receipt fields
- `docs/notes/lifecycle-ref-decay.md`

**Acceptance**
- selected recall items can refresh usage timestamps
- receipt shows refreshed record refs or count
- failure to refresh does not break recall

**Risks**
- per-item write amplification
- ambiguity between candidate seen vs item truly selected

---

### OCM-CG-02 — retrieval strategy registry + router
**Priority:** P1
**Goal:** formalize recall behavior into explicit strategies instead of scattered branching.

**Scope**
- define a small strategy surface: `lexical`, `hybrid`, `graph_assisted`, `temporal`
- route queries via deterministic policy / heuristics
- record the chosen strategy in pack / recall traces

**Likely touchpoints**
- `openclaw_mem/cli.py`
- `openclaw_mem/pack_trace_v1.py`
- `docs/context-pack.md`

**Acceptance**
- retrieval traces show selected strategy
- fallback path is explicit and testable
- no LLM-only hidden routing in v1

**Risks**
- heuristics too clever too early
- router sprawl without trace discipline

---

### OCM-CG-03 — temporal-intent retrieval lane
**Priority:** P1.5
**Goal:** make time-bounded questions behave like time-bounded questions.

**Scope**
- detect simple temporal intent: since / between / recently / what changed
- bias or filter episodic recall by interval when parse succeeds
- degrade to ordinary retrieval when parse confidence is low

**Likely touchpoints**
- `openclaw_mem/cli.py`
- timeline / episodes query flows
- `docs/specs/episodic-events-ledger-v0.md`

**Acceptance**
- time-bounded queries prefer interval-consistent results
- parse failure remains fail-open
- receipt can show interval extraction when used

**Risks**
- ambiguous dates
- overfiltering recent-but-relevant older evidence

---

### OCM-CG-04 — feedback-weighted recall loop
**Priority:** P2
**Goal:** let real operator usefulness affect recall weighting over time.

**Scope**
- define a small positive / negative recall feedback surface
- update retrieval priors or secondary weights, not original memory text
- keep aggregation scope-aware

**Likely touchpoints**
- `openclaw_mem/optimization.py`
- scoring / recommendation logic
- `docs/specs/self-optimizing-memory-loop-v0.md`

**Acceptance**
- feedback can shift subsequent ranking behavior measurably
- feedback is scoped and reversible
- sparse feedback does not destabilize baseline retrieval

**Risks**
- noisy labels
- overfitting to one recent session

---

### OCM-CG-05 — lightweight alias grounding
**Priority:** P2
**Goal:** reduce duplicate-entity drift without importing a heavyweight ontology stack.

**Scope**
- add a practical alias / canonical-name map for common repos, tools, projects, and recurring entities
- normalize a small bounded set first
- improve graph / docs memory consistency

**Likely touchpoints**
- `openclaw_mem/docs_memory.py`
- `openclaw_mem/graph/topology_extract.py`
- `openclaw_mem/graph/query.py`

**Acceptance**
- known aliases map to the same canonical entity
- duplicate graph nodes decrease on the seeded set
- no broad taxonomy system is required for v1

**Risks**
- taxonomy maintenance burden
- normalization mistakes that merge distinct concepts

## Suggested implementation sequence

### Phase 1 — foundation
- OCM-CG-01
- OCM-CG-02

### Phase 2 — time-aware recall
- OCM-CG-03

### Phase 3 — adaptive ranking
- OCM-CG-04

### Phase 4 — entity hygiene
- OCM-CG-05

## What to avoid

- full KG-platform ambitions before routing / lifecycle basics are tight
- heavy ontology work before duplicate-entity pain is measured
- any feature that compromises deterministic fallback behavior

## Recommended first execution slice

Start with **OCM-CG-01 + OCM-CG-02** as a paired milestone:
- better lifecycle truth
- better recall strategy observability
- low conceptual risk
- high leverage for later temporal / feedback features
