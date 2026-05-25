# Memory Strata WS9 Promotion / Writeback Governor — 2026-05-25

Status: **completed / documentation contract**  
Companion: `docs/specs/promotion-writeback-governor-v0.md`  
Topology/data impact: **unchanged** — docs only; no runtime write-path enabled.

## Goal

Define the generic governor that decides when any derived lane may write back into durable state.

## Evidence

- Contract: `docs/specs/promotion-writeback-governor-v0.md`
- Boundary map: `docs/specs/memory-strata-boundary-map-v0.md`
- WS8 stop-loss: `docs/receipts/memory-strata-ws8-stop-loss-wal-2026-05-25.md`
- WS5 Working Set contract: `docs/specs/working-set-backbone-contract-v0.md`
- WS7 graph governance: `docs/specs/graph-topology-governance-contract-v0.md`

## Decisions

- Default prohibition: Pack, Working Set, graph, episodic semantic, docs cold lane, and heuristic selectors do not auto-write durable truth.
- Durable writes need a named governed entrypoint.
- Promotion classes distinguish authored truth, cited derived summaries, episodic evidence, lifecycle residue, and graph synthesis.
- Pack lifecycle writeback is field-bounded lifecycle mutation, not truth promotion, but still governed.
- Missing provenance, scope ambiguity, stale graph authority, conflict, or absent reviewer receipt block promotion.

## Verifier

- Contract names default prohibition, allowed entrypoints, promotion classes, minimum requirements, lifecycle-write rule, conflict guard, receipt shape, and non-goals.
- No config/code/runtime write path was enabled.

## Closure

WS9 is complete as a governance contract. Any future promotion/writeback implementation must satisfy this governor and still pass second-brain review.
