# OpenClaw-mem Graph Skill Usage

Status: public-safe operator reference for agent skill cards.

This page summarizes how agents should use the shipped `openclaw-mem graph`
surface without turning graph output into a competing source of truth.

## Rule Of Ownership

- Store remains the canonical local ledger.
- Pack remains the context product surface.
- Observe remains the receipt and provenance layer.
- Graph remains derived, rebuildable evidence linked back to source paths,
  receipts, or records.

Do not treat graph output as authorization to change live harness memory-owner
configuration, post external messages, or route unattended autonomous work.

## Safe Read-Only / Local Artifact Flow

Use this when the question is about repo impact, symbol lookup, topology, or
codebase relationships.

```powershell
openclaw-mem --json graph health
openclaw-mem --json graph readiness
openclaw-mem --json graph extract --repo <repo> --out <graph.json>
openclaw-mem --json graph query symbol --graph <graph.json> --symbol <name>
openclaw-mem --json graph impact --graph <graph.json> --path <repo-relative-file>
```

`graph extract` writes the requested portable graph artifact. Keep generated
graphs under a task-scoped temp or evidence directory and remove throwaway files
before closure.

## Topology Flow

Use this when comparing extracted topology evidence against curated topology.

```powershell
openclaw-mem --json graph topology-extract --harness-home <harness-home> --workspace <workspace>
openclaw-mem --json graph topology-diff --seed <seed.yaml> --curated <topology.yaml>
```

`topology-diff` is suggest-only. Curated docs remain human-reviewed.

## Capture Flow

The capture commands write index observations. Use them only with a deliberate
scope and state path.

```powershell
openclaw-mem --json graph capture-git --help
openclaw-mem --json graph capture-md --help
```

`capture-md` is index-only and should store structural pointers rather than
large body excerpts. `capture-git` should record commit metadata and changed
paths, not raw diff hunks.

## Graph-Aware Pack Flow

Graph-aware Pack ranking is opt-in and fail-open.

```powershell
openclaw-mem pack --query <query> --graph-aware --graph-aware-path <graph.json> --trace
```

Do not make graph-aware ranking the default until A/B receipts show it improves
selection without adding noise.

## Fact Guard Flow

The guard surface is advisory and fail-open. It can highlight correction,
constraint, and regression-risk facts before an edit, but it must not become a
second memory owner or hard edit blocker.

```powershell
openclaw-mem --json graph fact guard --facts <facts.jsonl> --target <path-or-symbol> --intent <text>
openclaw-mem --json graph fact guard-lint --facts <facts.jsonl>
```

## Autonomous Matching Gate

`graph match` is available for manual idea-to-project lookup, but autonomous
matching stays gated until topology, support-plane, provenance, and freshness
checks are green.

```powershell
openclaw-mem --json graph readiness
openclaw-mem --json graph match "<idea or query>"
```

When using `graph match`, report readiness/freshness limits and fall back to
ordinary recall or repo inspection if graph evidence is stale or incomplete.
