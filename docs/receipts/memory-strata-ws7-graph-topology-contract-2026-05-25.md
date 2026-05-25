# Memory Strata WS7 Graph / Topology Governance Contract — 2026-05-25

Status: **completed / documentation contract**  
Companion: `docs/specs/graph-topology-governance-contract-v0.md`  
Topology/data impact: **unchanged** — docs only; no graph refresh, capture, config write, cron change, or runtime enablement.

## Goal

Define how graph/topology may participate in memory strata without becoming a truth owner or stale default authority.

## Evidence

- Inventory: `docs/receipts/memory-strata-ws7-graph-inventory-readonly-2026-05-25.md`
- Machine inventory: `docs/receipts/artifacts/memory-strata-ws7-graph-inventory-readonly-2026-05-25.json`
- Contract: `docs/specs/graph-topology-governance-contract-v0.md`

## Decisions

- Graph/topology is a derived relationship/query cache, not Store.
- Current graph cache is non-empty but stale and source-missing; readiness is red.
- `/tmp/...` topology sources are not durable source-of-truth paths.
- Production graph refresh is a derived-cache mutation and requires source receipt + pre/post health + rollback/degrade plan.
- Graph candidates without provenance are advisory-only.
- Red readiness blocks autonomous graph-match/default activation.

## Verifier

- Contract references the WS7 inventory facts.
- Contract names accepted source forms, refresh rules, provenance requirements, drift/stale handling, API/receipt requirements, and non-goals.
- No production refresh or enablement was run.

## Closure

WS7 is complete as graph/topology governance. The graph remains advisory until freshness/source/provenance gates are satisfied.
