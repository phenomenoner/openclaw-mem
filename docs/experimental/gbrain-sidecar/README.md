# GBrain sidecar experimental lane

Status: experimental rollout surface.

This lane is **not enabled by default** and does **not** carry stability guarantees yet.
Use it as an experimental integration surface when you want to test whether GBrain can help with read-only Pack lookup or one tightly bounded helper lane.

Plain-language summary:

- Phase 1 = **read-only lookup** from GBrain during Pack assembly
- Phase 2 = **restricted background jobs** for one deterministic helper family
- Phase 3 = **gated refresh apply** through the existing governor path

## Verdict

`openclaw-mem` stays the memory governor and `ContextPack` owner.
`gbrain` is consulted as an external retrieval/helper substrate, not promoted into a second truth owner.

## Relation to `gbrainMirror`

This experimental sidecar is **not** the same thing as `gbrainMirror`.

- `gbrain sidecar` = optional experimental lookup + bounded helper bridge during Pack/maintenance workflows
- `gbrainMirror` = optional mem-engine write-through mirror that copies successful `memory_store` writes into a dedicated GBrain import root

They can coexist, but they solve different problems.
If you are looking for engine-side write mirroring, read [`docs/mem-engine.md`](../../mem-engine.md) and [`extensions/openclaw-mem-engine/README.md`](../../../extensions/openclaw-mem-engine/README.md).

## Phase 1 shipped here

Read-only consult adapter:

- `openclaw-mem pack --use-gbrain on`
- `openclaw-mem gbrain-sidecar consult --query ...`

Guardrails:

- baseline `bundle_text` and `context_pack` stay schema-stable
- gbrain output is normalized into a source-labeled additive payload
- trace receipts expose `trace.extensions.gbrain`
- failures are fail-open and do not break Pack

Additive payloads:

- `gbrain`: normalized consult receipt
- `bundle_text_with_gbrain`: optional combined text for operator-controlled injection

## Phase 2 shipped here

Bounded Minions bridge:

- `openclaw-mem gbrain-sidecar jobs-smoke`
- `openclaw-mem gbrain-sidecar jobs-submit`
- `openclaw-mem gbrain-sidecar jobs-list`
- `openclaw-mem gbrain-sidecar jobs-retry`

Current lane is intentionally narrow:

- allowed job family: `embed`

Runtime note:
- durable worker execution depends on a PostgreSQL-backed GBrain engine
- `pglite` can still support bounded inline work, but not the persistent `gbrain jobs work` daemon posture

Why this narrow:

- proves the queue bridge without giving gbrain broad execution authority
- keeps phase 2 on deterministic helper work
- widens only after receipts show net value

## Phase 3 shipped here

Governed refresh canary:

- `openclaw-mem gbrain-sidecar recommend-refresh`
- `openclaw-mem optimize governor-review --approve-refresh`
- `openclaw-mem gbrain-sidecar refresh-canary`

Current posture:

- recommendation packet is additive and read-only
- governor packet is still mandatory
- canary defaults to dry-run
- actual apply is bounded to one `refresh_card` candidate per run
- receipts and rollback artifact are always written

Why this shape:

- proves the governed write bridge without opening broad mutation authority
- reuses the existing governor ladder instead of inventing a bypass lane
- keeps gbrain in the evidence role while `openclaw-mem` remains writer-of-record

## Operator notes

- default binary: `gbrain`
- override with `--gbrain-bin` when needed
- consult timeout and job timeout are explicit flags
- if `gbrain` is missing or slow, Pack degrades to baseline behavior

Repo-local operator card:

- [`skills/gbrain-sidecar.ops.md`](../../../skills/gbrain-sidecar.ops.md)

## Non-goals in this slice

- direct writes from gbrain into Store
- `ContextPack` schema changes tied to gbrain internals
- broad unrestricted job submission
- treating gbrain as truth owner
