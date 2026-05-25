# Memory Strata + Boundary Map v0

Status: **draft / operator architecture review**  
Date: 2026-05-25  
Scope: `openclaw-mem` product architecture + CK/Lyria workspace governance boundary  
Topology impact: **unchanged** — this document changes no runtime config, cron, slot backend, schema, or write path.

## 0. Executive verdict

`openclaw-mem` should be understood as a **layered context supply chain**, not a single memory bucket.

The current-known / target architecture contains multiple memory strata. Some are shipped product surfaces, some are opt-in or operator-governed lanes, and WS1 in the companion TODO should verify exact enablement before any runtime change:

1. **Durable / long-term memory** — canonical remembered facts and preferences served by `openclaw-mem-engine` when it owns the OpenClaw memory slot.
2. **Episodic memory** — append-only session/event evidence for replay, audit, and raw-trail recovery.
3. **Verbatim semantic lane** — hybrid/vector retrieval over bounded episodic evidence; a retrieval tactic, not a new truth store.
4. **Working Set / Backbone lane** — pinned activation layer for current durable constraints and active goal state.
5. **Docs cold lane** — operator-authored specs, decisions, receipts, and long-form evidence.
6. **Graph / topology layer** — structured relationship, dependency, provenance, and drift query layer.
7. **Pack / Proactive Pack** — bounded context assembly layer that consumes the other strata but must not become an ungoverned truth owner.

The critical design principle:

> **Truth ownership, retrieval, and activation are separate concerns.**

Confusing them creates memory bloat, stale injections, double-write paths, and hard-to-debug context contamination.

## 1. Product-level doctrine

### 1.1 Store / Pack / Observe split

`openclaw-mem` product direction remains:

- **Store**: durable records, episodic events, docs indexes, governed ingest, recall substrates.
- **Pack**: bounded `ContextPack` / Proactive Pack assembly with budgets, citations, include/exclude reasons, and trace receipts.
- **Observe**: receipts, traces, drift reports, replay, audit artifacts, and operator-readable reports.

This review does not replace that doctrine. It refines how each memory stratum maps into it.

### 1.2 Sidecar governs; engine serves

When `openclaw-mem-engine` owns the OpenClaw memory slot, it should remain the **single canonical durable-memory write path** for slot-level memory tools:

- `memory_store`
- `memory_recall`
- `memory_forget`
- `memory_import`
- `memory_export`
- `memory_docs_ingest` where configured as engine-owned durable ingest

The sidecar remains responsible for governance, capture, review, receipts, and optional enrichment. Helper lanes may improve retrieval or packing, but must not silently become competing durable truth owners.

### 1.3 Retention is not activation

A record can be worth preserving without deserving prompt space on every turn.

- **Retention priority** answers: should this survive decay/archive?
- **Activation priority** answers: should this be injected now?

`must_remember` should be a retention and selection prior, not an unconditional hot-context slot claim.

## 2. Layer inventory

| Layer | Product role | Truth owner | Write path | Retrieval path | Activation role | Retention / decay | Main risk |
|---|---|---|---|---|---|---|---|
| Durable / long-term memory | Stable facts, preferences, decisions | `openclaw-mem-engine` when slot owner | `memory_store`, import, governed promotion | `memory_recall`, engine hybrid search, pack | Hot recall candidate; sometimes backbone source | Importance, use-based decay, soft archive | Must pool saturates prompt; stale facts outrank relevant ones |
| Episodic memory | Append-only evidence timeline | Episodic events ledger | sidecar spool, extractor, `episodes append/ingest` | `episodes query/search/replay` | Evidence retrieval; replay; audit | Type-based GC, redaction, scope isolation | Raw transient content mistaken for truth |
| Verbatim semantic lane | Semantic retrieval over episodic evidence | Episodic ledger remains truth owner | `episodes embed` over bounded/redacted `search_text` | `episodes search --mode hybrid/vector` | Find raw trails; evidence support | Embedding freshness + episodic retention | Treated as a new memory type or auto-promoted |
| Working Set / Backbone | Pinned current-state activation | Derived artifact; not source of truth | deterministic synthesis from governed sources | injected by autoRecall / pack | Stable active constraints and goal state | high churn; replace/update, not archive like durable memory | Becomes stale static prefix or competing memory |
| Docs cold lane | Operator-authored long-form truth/evidence | Markdown/docs repo owners | docs ingest/index, repo allowlist | docs search / pack cold lane | Background evidence and specs | Git/history/operator curation | Docs treated as prompt dump instead of cited cold lane |
| Graph / topology | Relationship, dependency, provenance, drift | Curated topology/docs as source; SQLite graph as derived cache | graph refresh / topology extraction | graph query, graph-aware pack, drift/provenance | Relationship expansion and impact analysis | drift checks, provenance freshness | Graph cache mistaken for source of truth |
| Pack / Proactive Pack | Context assembly | None; consumes sources | no durable write by default | pack/search orchestration | Final bounded context injection | trace-based lifecycle refresh may update use signals | Pack decisions become opaque or over-broad |

## 3. Boundary matrix

Legend:

- **Allowed**: normal architecture path.
- **Review-gated**: allowed only through explicit review/apply, receipt, or human approval.
- **No direct write**: must not write directly; may cite or suggest.
- **Derived only**: output is cache/projection, not source of truth.

| From → To | Durable | Episodic | Verbatim semantic | Working Set | Docs cold lane | Graph | Pack |
|---|---|---|---|---|---|---|---|
| Durable | — | No direct write | May be cited as comparison corpus | Allowed as backbone source | May be documented manually | May provide stable node facts | Allowed |
| Episodic | **Review-gated promotion only** | — | Allowed: embed/search bounded evidence | May inform active summary if reviewed/bounded | May be summarized into receipt docs manually | May provide evidence refs | Allowed as evidence lane |
| Verbatim semantic | No direct write | Derived only | — | No direct write | No direct write | No direct write | Allowed as evidence candidate |
| Working Set | No direct write | No direct write | No direct write | — | No direct write | No direct write | Allowed / injected first |
| Docs cold lane | Review-gated ingest/promotion | No direct write | Separate docs substrate | May inform backbone if cited | — | May define topology source | Allowed |
| Graph | No direct write | No direct write | No direct write | May suggest activation context | No direct write | Derived/cache unless topology file | Allowed for relationship expansion |
| Pack | No durable write by default | May emit Observe receipts | No direct write | May refresh use-signal only if policy says so | No direct write | No direct write | — |

Hard boundary:

> **Only governed promotion writes stable durable memory. Retrieval hits, graph paths, episodic matches, and pack selections are evidence — not automatic truth.**

## 4. Product vs CK/Lyria ops boundary

### 4.1 Product-grade surfaces

These belong in `openclaw-mem` product design, tests, docs, or CLI/API contracts:

- Durable memory slot ownership and single-write-path rules.
- `autoRecall` selection policy, quota mixing, repeat suppression, backbone dedupe, and receipts.
- Episodic event schema, auto-capture, retention, replay, search, redaction, and GC.
- Verbatim semantic lane behavior over episodic evidence.
- Docs cold lane search, allowlist, scope pushdown, and pack integration.
- Graph query/refresh/drift/provenance contracts.
- Pack / Proactive Pack trace schema, budget enforcement, citation coverage, and failure posture.
- Generic audit tools: stale/conflict/orphan checks, recall regression harness, promotion review packets.

### 4.2 CK/Lyria ops-only policy

These are local workspace governance unless later generalized:

- What CK/Lyria persona/operator rules stay in `MEMORY.md` vs `AGENTS.md` vs appendices.
- Local promotion thresholds for CK preferences, relationship tone, active projects, and self-journal lanes.
- Naming conventions for this workspace's project/person/system/decision nodes.
- Weekly/monthly maintenance cadence and `五氣朝元` closure hygiene.
- Local bootstrap slimming targets and what counts as high-frequency context.
- Which private relationship or narrative materials are excluded from default graph/doc indexing.

### 4.3 Mixed zone: ops first, product later

These should first run as local governance, then graduate only if they prove reusable:

- Memory/graph routing decision table.
- Local retrieval regression question set.
- Workspace graph v0 ontology.
- Curator review checklist.
- Promotion/demotion review packets.

Graduation test:

1. Is it useful for operators beyond CK/Lyria?
2. Can it be represented as a stable contract, CLI, schema, or receipt?
3. Can it fail open and roll back?
4. Can tests distinguish good behavior from broken behavior?

## 5. Retrieval chain by user intent

| User intent | First lane | Secondary lane | Avoid |
|---|---|---|---|
| Stable preference / decision | Durable memory | Docs cold lane / receipts | Episodic raw text as truth |
| What happened in a session/run | Episodic replay/query | Verbatim semantic search | Durable memory unless promoted |
| Find exact/raw wording trail | Verbatim semantic over episodic | Replay selected session | Graph as evidence source |
| Current active goal/state | Working Set / backbone | Durable + recent docs | Re-searching all must memories every turn |
| Specs/decisions/runbooks | Docs cold lane | Durable summary | Bootstrap stuffing |
| Dependencies / impact / owners | Graph/topology | Docs provenance | Free-text-only recall |
| Final context injection | Pack / Proactive Pack | All relevant lanes with budgets | Unbounded raw dumps |

## 6. Anti-corruption rules

1. **No raw episodic-to-durable auto-promotion.** Episodic evidence may propose a durable memory candidate, but apply must be governed.
2. **Graph cache is not graph truth.** Source topology/docs/receipts own truth; SQLite graph is derived.
3. **Working Set is activation, not memory.** It may be persisted as a derived artifact, but it must cite or derive from governed sources.
4. **Docs cold lane should not become bootstrap.** It is searchable/citable, not a prompt prelude.
5. **Pack must stay inspectable.** Every included item should have source, why-included, and budget impact when trace is requested.
6. **Importance is not enough.** Activation selection must include relevance, recency, novelty, repeat suppression, and scope.
7. **Scope boundaries beat convenience.** No fallback across scopes unless explicitly configured and receipted.
8. **External/untrusted content needs trust policy.** Web/social/tool outputs are evidence until promoted.

## 7. Gaps / questions to evaluate

### Product gaps

- Is `tier_quota_v1` still non-default, and what evidence is required to promote it?
- Are Working Set records traceably derived from source records with enough citation coverage?
- Does `pack --use-graph=auto` have a stable evaluation set showing real recall-quality lift?
- Are episodic embeddings refreshed often enough for the verbatim semantic lane to be reliable?
- Is there a clean operator command for memory-strata status in one report?
- Are graph orphan/stale-provenance checks productized or still ad hoc?
- Is docs cold lane query-language mismatch handled well enough for bilingual CK/Lyria use?

### Ops gaps

- `MEMORY.md` is close to the local per-file bootstrap cap and needs slimming.
- `memory/` currently mixes daily logs, topical notes, schemas, and project notes.
- CK/Lyria-specific graph ontology is not yet written as a local contract.
- Current retrieval regression set is implicit; it needs 10–20 real questions.
- Promotion rules for relationship/private/self-journal content need privacy-aware gates.

## 8. Proposed artifact split

### Product docs / specs

- `docs/specs/memory-strata-boundary-map-v0.md` — this document.
- `docs/specs/memory-strata-todo-v0.md` — follow-up backlog.
- Future candidate: `docs/specs/memory-strata-status-command-v0.md`.
- Future candidate: `docs/specs/curator-review-workflow-v0.md`.

### Workspace ops docs

Suggested outside product repo or under operator canon:

- `workspace-memory-governance-v0.md`
- `workspace-graph-ontology-v0.md` — local CK/Lyria ontology only; not a product default
- `memory-retrieval-regression-questions-v0.md`

These should describe CK/Lyria local usage without hard-coding private policy into product defaults.

## 9. Verification plan

For this review artifact:

- Check both markdown files exist.
- Check they mention all required strata: durable, episodic, verbatim semantic, working set, docs cold lane, graph, pack.
- Check they explicitly state topology/runtime impact is unchanged.
- If this artifact is committed, keep the change scoped to these documentation files and preserve pre-existing working tree changes.

For future product work:

- Every feature candidate needs a schema/CLI contract, fixture, failure-mode test, and trace receipt.
- Any runtime/default behavior change requires dry-run, readback, rollback note, and stale-rule retirement review.
