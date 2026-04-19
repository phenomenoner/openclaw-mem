# gbrain side-car experimental lane

Status: Phase 1 and Phase 2 bounded implementation slice.

## Verdict

`openclaw-mem` stays the memory governor and `ContextPack` owner.
`gbrain` is consulted as an external brain and used as a bounded deterministic worker substrate.

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

Why this narrow:

- proves the queue bridge without giving gbrain broad execution authority
- keeps phase 2 on deterministic helper work
- widens only after receipts show net value

## Operator notes

- default binary: `gbrain`
- override with `--gbrain-bin` when needed
- consult timeout and job timeout are explicit flags
- if `gbrain` is missing or slow, Pack degrades to baseline behavior

## Non-goals in this slice

- direct writes from gbrain into Store
- `ContextPack` schema changes tied to gbrain internals
- broad unrestricted job submission
- treating gbrain as truth owner
