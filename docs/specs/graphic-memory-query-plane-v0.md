# Spec — Graphic Memory Query Plane v0

## Status
- Stage: **DONE / operator query plane shipped on stable main** (closure revalidated 2026-03-31; initial stable-main landing 2026-03-19)
- Scope: bounded operator slice now lives in `openclaw-mem` repo truth: stage-1 topology-file helper + stage-2 refresh/drift/provenance substrate + stage-3 operator docs/receipts
- Recommendation: **keep implementing inside `openclaw-mem`**
- Delivery posture: **repo-backed truth, derived graph query layer**
- Implementation note: `graph query ... --topology <path>` answers `upstream` / `downstream` / `writers` / `filter` directly from structured topology files; `graph topology-refresh`, `graph query provenance`, and `graph query drift` provide the derived SQLite query plane. This host lane validated the operator path with JSON topology files; YAML continues to require `PyYAML` when `.yaml/.yml` files are used

## Why this belongs in openclaw-mem
Graphic Memory query / topology retrieval is a natural extension of `openclaw-mem`:
- `openclaw-mem` already owns structured memory, retrieval, context packing, and graph-adjacent specs.
- The desired operator experience is a **query layer over structured relationships**, not a separate product.
- Putting it outside `openclaw-mem` would add coordination/drift tax without reducing real complexity.

## Existing facts
- Repo-backed structured files are the source of truth.
- Graphic Memory already has specs for GraphRAG-lite and auto-capture / preflight.
- Playbook now has a canonical cron-topology YAML for stable cron/project/artifact relationships.
- Desired UX gaps are practical and bounded:
  1. one-hop upstream/downstream queries
  2. graph truth vs live-state drift checks
  3. typed edges + provenance
  4. stable topology vs runtime health separation
  5. simple operator queries (`depends on`, `writers`, `background-but-not-human-facing`)

## Decision
Adopt **Option B** as the target architecture:
- **source of truth**: human/agent-maintained structured files (YAML / markdown / receipts)
- **derived query plane**: SQLite graph cache rebuilt from the source of truth
- **first shippable slice**: YAML-only query helper (A-fast) before the SQLite layer lands

This gives us:
- immediate operator value
- zero new service dependency
- clear rollback path
- room to grow without making the graph the truth source

## Non-goals (v0)
- no external graph database
- no web UI requirement
- no multi-hop graph algorithms as a requirement for first ship
- no automatic promotion of graph artifacts to source-of-truth status
- no runtime hard dependency: graph failures must remain fail-open

## Architecture boundary

### 1) Stable topology (source of truth)
Human/agent-curated, slow-changing relationships.

Suggested content:
- nodes: `project`, `cron_job`, `artifact`, `script`, `target`
- edges: `belongs_to`, `reads`, `writes`, `depends_on`, `runs_before`, `runs_after`, `alerts_to`, `validates`, `feeds`, `blocks`
- node metadata: tags like `background`, `human_facing`, `receipt_style`, `deliverable`
- provenance fields pointing back to the file/receipt that justified the relation

### 2) Runtime state (derived, ephemeral)
Machine-collected health / freshness / drift facts.

Suggested content:
- node status: `ok|stale|error|missing`
- last verified / last seen / freshness windows
- drift report: expected vs actual

### 3) Receipts / provenance (append-only)
Execution and justification layer.

Suggested content:
- receipt records per run / refresh / validation
- source artifact or command that proved a relation
- success/fail and timestamp

## Proposed repo shape (target)

```text
openclaw_mem/
  graph/
    refresh.py          # ingest source-of-truth files -> SQLite derived graph
    query.py            # upstream/downstream/writers/filter/path queries
    drift.py            # compare stable topology vs live runtime facts
    schema.py           # SQLite schema + typed edge enums

docs/specs/
  graphic-memory-query-plane-v0.md

tests/
  test_graph_query.py
  test_graph_refresh.py
  test_graph_drift.py
```

## CLI / API sketch

### Stage-1 YAML-first CLI (fastest useful slice)
- `openclaw-mem graph query upstream --node <id> --topology <path>`
- `openclaw-mem graph query downstream --node <id> --topology <path>`
- `openclaw-mem graph query writers --artifact <id> --topology <path>`
- `openclaw-mem graph query filter --tag background --not-tag human_facing --topology <path>`

### Stage-2 derived SQLite CLI
- `openclaw-mem graph refresh --topology <path> --db <path>`
- `openclaw-mem graph query upstream --node <id> --db <path>`
- `openclaw-mem graph query drift --live-json <path> --db <path>`
- `openclaw-mem graph health --db <path> --stale-hours 24`

### Stage-3 provenance / receipts
- `openclaw-mem graph query provenance --node-id <id> --db <path>`
- `openclaw-mem graph query lineage <node_id> --db <path>`
- Query outputs should expose a normalized `provenance_ref` object (`kind`, `path/url`, optional line span/anchor) so provenance is machine-consumable instead of string-only.
- `openclaw-mem graph query subgraph <node_id> --require-structured-provenance` provides a bounded fail-open guard for pack-facing consumption.

## A-fast / A-deep split

### A-fast — narrow vertical slices, ship operator value early
1. **GQ-A1** — codify minimal topology query contract in docs/examples
   - acceptance: spec + examples are clear enough to test manually
2. **GQ-A2** — ship YAML-only query helper for one-hop operator questions
   - acceptance: upstream/downstream/writers/filter work on a small fixture
3. **GQ-A3** — add docs/examples and a tiny fixture so regressions are visible
   - acceptance: one command per common question; bounded output
4. **GQ-A4** — once SQLite exists, add small user-facing queries (`writers`, `background-only`, `depends-on`)
   - acceptance: thin queries, not schema work

### A-deep — foundations and drift/provenance layer
1. **GQ-D1** — define graph schema + refresh contract (`YAML -> SQLite`)
   - acceptance: schema doc + tests for deterministic refresh
2. **GQ-D2** — implement runtime-state / drift separation
   - acceptance: graph truth and live-state can be compared without mutating truth
3. **GQ-D3** — add provenance / receipt table and lineage query contract
   - acceptance: path/provenance is inspectable and redaction-safe
4. **GQ-D4** — integrate fail-open into pack / preflight later, behind flag
   - acceptance: graph OFF = no regression

## Suggested staged rollout

### Stage 0 — docs/spec alignment (now)
- land this spec
- link from `docs/index.md`
- mention the query-plane milestone in `docs/roadmap.md`

### Stage 1 — A-fast ships value without schema lock-in
- use topology YAML fixture(s)
- support the 4 operator questions:
  - `upstream`
  - `downstream`
  - `writers`
  - `background-but-not-human-facing`

### Stage 2 — A-deep installs durable structure
- SQLite schema + refresh command
- deterministic rebuild contract
- drift table separate from stable topology tables

### Stage 3 — receipts / provenance / lineage
- provenance queries
- drift checks
- optional captain-log / health-check integration

## 1-day acceptance check
- a spec reader can answer where truth lives and where derived state lives
- the first CLI questions are explicit and bounded
- A-fast / A-deep roles are non-overlapping enough to avoid stepping on each other
- rollback remains trivial: remove the query layer, keep topology truth

## Risks
- topology YAML rots without drift checks
- SQLite accidentally becomes the editable truth
- scope creep into full graph platform / graph DB work
- provenance becomes too noisy if every run writes low-value receipts

## Mitigations
- make refresh rebuildable + deterministic
- document "YAML is truth, SQLite is cache"
- keep v0 to one-hop operator questions + drift + provenance
- keep receipts aggregate-first and redaction-safe

## Rollback
- delete/disable the graph query layer
- keep source topology files untouched
- keep `pack` / baseline recall fail-open and unchanged when graph is disabled

## Recommendation on branching / promotion
- yes: **A-fast / A-deep should keep landing to `dev` branch** for this workstream
- promote to `main` only after:
  - deterministic query tests
  - drift behavior reviewed
  - operator docs are good enough that the feature is debuggable
