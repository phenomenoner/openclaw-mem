# Topology knowledge (L3) blueprint v0

Status: **blueprint** (designed to be deterministic + provenance-first).

This spec defines **L3 topology knowledge**: a maintained map of “what exists” and “how it connects” across a repo/system (entrypoints, ownership, dependencies, impact).

It is intentionally **not** durable memory (L1) and not operator docs/manuals (L2).

---

## 0) Why L3 exists

Most agent memory failures come from layer collapse:
- storing repo maps as “facts” in durable memory,
- treating retrieved text as authority,
- or stuffing long docs into prompts.

L3 fixes the common question class:
- “Where does X live?”
- “What breaks if I change Y?”
- “Who owns this lane?”
- “Which cron job writes this artifact?”

…without polluting L1.

---

## 1) Definitions (hard boundary)

### L1 — Durable memory (hot, write-rare)
- user preferences, explicit decisions, standing rules
- must be compact, scoped, attributable

### L2 — Docs knowledge (operator-authored reference)
- contracts, SOPs, runbooks, canonical wording
- maintained like code/docs; ingested into docs cold lane

### L3 — Topology knowledge (system/repo map)
- deterministic graph of entities + relationships
- designed for **navigation + impact analysis**, not “truth claims”
- refreshable and auditable via provenance

Key property: **topology is rebuildable**.

---

## 2) Data model (v0)

Represent topology as a small graph:

- `nodes[]`: `{ id, type, tags?, metadata? }`
  - `id` is a stable string (namespaced, e.g. `cron.job.daily_ingest`)
  - `type` is an enum-like string (e.g. `project|cron_job|artifact|script|target|service`)
  - `tags` are short classifiers (e.g. `background`, `deliverable`, `human_facing`)

- `edges[]`: `{ src, dst, type, provenance, metadata? }`
  - `type` examples: `depends_on`, `writes`, `alerts_to`, `owns`, `reads_from`
  - `provenance` is required (file/line, URL, receipt id)

### Trust posture
Topology rows are only as trustworthy as their sources.
Treat topology as **reference with provenance**, not a blanket authority.

Suggested trust tiers:
- `operator_authored` (curated YAML/JSON)
- `deterministic_extract` (generated from config/files)
- `runtime_reported` (status snapshots)

---

## 3) Sources of truth (inputs)

Topology should be built from **curated + deterministic sources**, for example:

1) **Curated topo file** (preferred seed)
   - `docs/topology.json` (or `.yaml` when YAML parsing is available)
   - hand-maintained, reviewed like docs

2) **Deterministic extraction** (optional)
   - cron job registries
   - repo file structure / entrypoints
   - CI pipelines

3) **Runtime snapshots** (optional, used for drift)
   - healthcheck outputs
   - deployment status dumps

Never use L1 durable memory as the source of truth for topology.

---

## 4) Maintenance loop (how it stays fresh)

A minimal v0 loop:

1) Operator updates `docs/topology.json` when structure changes.
2) Refresh the topology store deterministically:

```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem graph topology-refresh --file docs/topology.json --json
```

3) Query via deterministic graph queries (no LLM required).

Receipts are stored so you can audit when topology changed and from what source.

---

## 5) Query contract (what L3 answers)

Topology queries should return:
- bounded results
- stable ordering
- provenance strings

Core query shapes:
- upstream/downstream/lineage of a node
- filter nodes by type/tag
- list refresh receipts / provenance groups
- drift vs runtime snapshot

Example:

```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem graph query upstream artifact.daily-mission --json
```

---

## 6) How L3 feeds ContextPack + eval safely

### Packing rule
When a task needs navigation/impact, pack **only the minimal subgraph**:
- a few nodes/edges around the target
- plus provenance strings

Do not pack:
- entire repo trees
- long code blobs
- raw logs

### Provenance-first
Every injected topology statement must carry provenance (file/line/receipt) so:
- humans can verify quickly
- the agent can avoid “topology hallucination”

### Eval fixtures
Add routing scenarios that distinguish:
- topology questions → `topology_search`
- policy wording → `docs_search`
- continuity preferences → `recall`

---

## 7) Read-only lanes (watchdog/healthcheck/lint/smoke)

Monitoring lanes should treat topology + docs as reference, but avoid writing L1:
- recall/docs/topology: ✅
- store: 🚫 by default

Use `skills/agent-memory-skill.readonly.md` to make this enforceable at the prompt layer.

---

## 8) Open questions / v1 candidates

- deterministic extractors (cron/jobs/config → topology)
- a `graph pack-topology` subcommand that emits a bounded L3 injection bundle
- stable node-id conventions and type registry
- mapping topology trust tiers into ContextPack trace
