# GBrain sidecar ops lane

Experimental surface only: not enabled by default and no stability guarantee yet.

Use this card when you need the repo-local operator summary for the experimental `gbrain` integration lane.

## What it is

The GBrain sidecar is an **experimental** `openclaw-mem` surface for:

1. **read-only GBrain lookup** during Pack assembly
2. **restricted background-job bridging** for one deterministic helper family
3. **gated refresh apply** through the existing governor review path

It is **not enabled by default** and does **not** replace `openclaw-mem-engine` or `ContextPack` ownership.

## What it is not

- not a backend replacement
- not a second truth store
- not a broad unrestricted jobs runner
- not the same thing as `gbrainMirror`

## Current bounded surfaces

### Phase 1, read-only lookup

- `openclaw-mem pack --use-gbrain on`
- `openclaw-mem gbrain-sidecar consult --query ...`

### Phase 2, restricted helper jobs

- `openclaw-mem gbrain-sidecar jobs-smoke`
- `openclaw-mem gbrain-sidecar jobs-submit --name embed ...`
- `openclaw-mem gbrain-sidecar jobs-list`
- `openclaw-mem gbrain-sidecar jobs-retry`

Current allowed helper family:
- `embed`

Runtime note:
- persistent worker execution for this lane needs PostgreSQL-backed `gbrain`
- if the host is still on `pglite`, treat the jobs bridge as non-daemon / bounded-only

### Phase 3, gated refresh canary

- `openclaw-mem gbrain-sidecar recommend-refresh`
- `openclaw-mem optimize governor-review --approve-refresh`
- `openclaw-mem gbrain-sidecar refresh-canary`

## Boundary rules

- `openclaw-mem-engine` remains durable-memory slot owner
- `openclaw-mem` remains Store / Pack / Observe governor
- `gbrain` stays a retrieval/helper substrate
- failures fail open on the Pack side unless the specific command says otherwise

## Related docs

- `docs/experimental/gbrain-sidecar/README.md`
- `docs/mem-engine.md`
- `extensions/openclaw-mem-engine/README.md`
