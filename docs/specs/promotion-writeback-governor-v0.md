# Promotion / Writeback Governor v0

Status: **draft contract / public-facing product doc**  
Date: 2026-05-25  
Companion:
- `docs/specs/memory-strata-boundary-map-v0.md`
- `docs/specs/working-set-backbone-contract-v0.md`
- `docs/specs/graph-topology-governance-contract-v0.md`
- `docs/receipts/memory-strata-ws8-stop-loss-wal-2026-05-25.md`

Topology impact: **none** — documentation contract only.

## 1. Purpose

Define the only allowed ways information may move from derived/activation lanes back into durable state.

This governor exists to prevent silent dual-truth, accidental durable mutation, and low-confidence/uncited writeback.

## 2. Default prohibition

By default, the following are **not allowed** to write durable truth automatically:

- Pack / Proactive Pack
- Working Set / Backbone
- graph/topology cache
- episodic semantic retrieval
- docs cold-lane retrieval
- route-auto / graph-match / heuristic selectors

They may recommend, stage, or cite candidates. They may not silently promote them into durable memory.

## 3. Allowed durable-write entrypoints

A durable write may happen only through one of these governed entrypoints:

1. explicit operator/user-approved memory store or edit,
2. governed promotion review flow,
3. approved lifecycle/writeback flow with bounded target fields,
4. explicit maintenance/repair flow with receipts and rollback.

If a path cannot name its entrypoint, it is not allowed to write.

## 4. Promotion classes

| Class | Source lane | Example | Default |
|---|---|---|---|
| P1 | authored durable rule | manually approved preference/decision | allow with approval |
| P2 | derived but cited | docs/spec -> durable summary with citations | review required |
| P3 | episodic evidence | repeated stable behavior inferred from sessions | blocked unless reviewed |
| P4 | activation residue | Pack/Working Set lifecycle or usage counts | field-bounded only, never truth promotion |
| P5 | graph relationship synthesis | derived relationship claim | blocked unless provenance + review |

## 5. Minimum requirements for promotion

Any governed promotion must include:

- source lane and source artifact ids/paths,
- target durable field/category,
- confidence/reason code,
- privacy/scope label,
- duplicate/conflict check,
- rollback method,
- reviewer/approval receipt,
- machine-readable promotion receipt.

## 6. Pack lifecycle writeback rule

`--pack-lifecycle-write on` is not truth promotion. It is a field-bounded lifecycle mutation.

Even so, it is governed because it mutates durable rows.

Requirements:

- off by default,
- bounded to selected records only,
- explicit receipt listing affected record refs,
- pre-snapshot or fixture DB,
- rollback plan,
- no authority claim derived from usage alone.

Usage counts and last-used timestamps must never be treated as proof of truth importance.

## 7. Conflict / duplicate guard

Promotion is blocked if:

- source lacks provenance,
- target scope is ambiguous,
- new durable candidate conflicts with an existing higher-trust record,
- evidence is single-episode / low-repeat / privacy-sensitive,
- reviewer receipt missing,
- write path depends on stale graph authority.

## 8. Receipt shape

A promotion/writeback receipt should minimally contain:

- `kind`
- `ts`
- `source_lane`
- `source_refs`
- `target_kind`
- `target_refs`
- `action` (`promote`, `writeback`, `blocked`, `rollback`)
- `reason_codes`
- `approved_by`
- `rollback_refs`
- `result`

## 9. Non-goals

This governor must not:

- authorize autonomous truth growth from Pack or graph,
- reclassify usage telemetry as truth,
- bypass scope/privacy boundaries,
- treat stale caches as durable evidence,
- hide blocked promotions.

## 10. Acceptance criteria for WS9

- Contract written.
- WS8 lifecycle-write incident integrated as governing case.
- Explicit default prohibition stated.
- Allowed entrypoints and promotion classes stated.
- Receipt shape and block conditions stated.
- No runtime write-path enabled by this document alone.
