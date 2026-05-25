# Graph / Topology Governance Contract v0

Status: **draft contract / public-facing product doc**  
Date: 2026-05-25  
Companion receipts:
- `docs/receipts/memory-strata-ws7-graph-inventory-readonly-2026-05-25.md`
- `docs/specs/memory-strata-boundary-map-v0.md`

Topology impact: **none** — documentation contract only.

## 1. Purpose

Graph/topology is a derived relationship layer. It may help Pack and Recall navigate dependencies, provenance, and lineage, but it does not own durable truth.

## 2. Ownership model

| Surface | Role | Truth owner? |
|---|---|---:|
| Durable memory / Store | facts/preferences/decisions | yes |
| Docs/specs/receipts | authored long-form source | yes for their own content |
| Episodic ledger | event/session evidence | yes for event rows |
| Graph/topology DB | derived relationship/query cache | no |
| Pack / Working Set | activation/assembly | no |

## 3. Current posture from WS7 inventory

The existing graph cache is non-empty but stale:

- nodes: 557
- edges: 915
- last refresh: 2026-04-09T23:15:54Z
- latest source path: `/tmp/openclaw-mem-activation/topology-extract-full.json`
- source path exists now: false
- readiness verdict: red
- auto recall/capture flags: disabled

This means graph output may be useful as advisory context, but it must not be treated as fresh authority.

## 4. Accepted source forms

A topology source may be accepted only if it is one of:

1. A committed repository artifact under `docs/`, `docs/specs/`, or another reviewed source dir.
2. A generated extraction artifact with:
   - generation command,
   - timestamp,
   - source root allowlist,
   - digest,
   - node/edge counts,
   - receipt path.
3. A copied fixture artifact for testing/rebuild counterfactuals.

`/tmp/...` topology sources are not acceptable as durable source-of-truth paths unless copied into a durable receipt/artifact location.

## 5. Refresh / rebuild rule

Production graph refresh is a durable derived-cache mutation. It requires:

- source artifact exists and is durable,
- pre-refresh health/readiness receipt,
- proposed refresh command recorded,
- post-refresh health/readiness receipt,
- rollback/degrade plan,
- second-brain review before treating refreshed graph as default/runtime authority.

Counterfactuals and development tests should use fixture outputs or copied DBs unless an explicit production mutation window is approved.

## 6. Provenance requirements

Graph query or Pack use must preserve at least one of:

- source node id / record ref,
- source document path + heading,
- source observation id,
- source receipt id,
- topology extraction receipt.

A graph candidate without provenance is advisory-only and must not cause durable writes or promotion.

## 7. Drift and stale handling

Graph readiness is red if any of these hold:

- graph cache stale beyond configured threshold,
- source artifact missing,
- source digest differs from latest refresh receipt,
- source cannot be parsed,
- graph query support missing,
- node/edge count unexpectedly zero.

Red readiness blocks autonomous graph-match/default activation. It does not block read-only inventory or fixture rebuild experiments.

## 8. Product API / receipt requirements

Graph health/readiness receipts should expose:

- cache age / stale threshold,
- node and edge count,
- latest refresh timestamp,
- latest source path and digest,
- source existence and parser status,
- blockers and warnings,
- auto-recall/capture env flags,
- provenance support status.

## 9. Non-goals

Graph/topology must not:

- become a second Store,
- silently promote relationships into durable memory,
- hide stale/missing source state,
- refresh production DB from `/tmp` without durable copy + receipt,
- enable graph-auto recall/capture by default without review.

## 10. Acceptance criteria for WS7

- Read-only inventory completed.
- Stale/missing source state recorded.
- Topology-source contract written.
- No production graph refresh or enablement performed.
- Next refresh/rebuild step is gated by fixture/copy or explicit mutation window.
