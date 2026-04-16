# About openclaw-mem

`openclaw-mem` is a **local-first context supply chain for OpenClaw**.

It gives operators a durable record of what the agent actually did and a practical recall surface they can inspect.
It also gives them a bounded packing surface they can inject, test, and roll back.

## What problem it solves

Most agent memory stories sound good until you need all of these in production:

- **fresh recall** of what happened recently
- **auditability** for tool outcomes, decisions, and ops breadcrumbs
- **cheap local lookup** before asking a remote semantic system again
- **bounded context assembly** that fits inside a prompt instead of flooding it
- **safe rollback** when a memory backend or embedding path gets weird

`openclaw-mem` exists to make memory and context assembly more operational, not more mystical.

## What it does today

- local recall with `search → timeline → get`
- compact memory packs with `pack`
- trace receipts that show what was included or excluded
- trust-policy controls for pack selection
- sidecar capture on top of an existing OpenClaw install
- optional promotion to `openclaw-mem-engine` later for hybrid recall and stronger policy controls

## How the product is split

### Store (default starting point)

This is the normal starting point.

- captures observations into JSONL
- ingests them into SQLite
- gives you a local recall and pack loop you can inspect
- does **not** replace your active OpenClaw memory backend

### Pack (shipped contract)

When you need a bounded, injection-ready result instead of another search result list, `openclaw-mem pack` emits a stable `ContextPack` object:

- short `bundle_text` for direct injection
- structured items with `recordRef` citations
- optional redaction-safe trace receipts for include/exclude debugging

This keeps recall, packing, and debugging on one auditable path.

When the optional mem-engine role is active, this same Pack posture extends into live turns as **Proactive Pack**: a bounded pre-reply recall mode with receipts, scope policy, and fail-open behavior.

### Memory engine (optional)

This is the controlled next step when sidecar mode already proved useful.

- can become the active OpenClaw memory backend
- adds hybrid recall and tighter policy controls
- exposes **Proactive Pack** for bounded pre-reply recall during prompt build
- keeps rollback explicit and configuration-driven

### Observe (cross-cutting)

Operators also need to see what the system kept, what it cut, and where large raw payloads went.

`openclaw-mem` therefore treats receipts and artifacts as first-class:

- retrieval traces explain pack decisions
- artifact handles keep raw payloads off-prompt but retrievable
- local files stay diffable and backup-friendly

## Why local-first matters

A lot of memory tooling gets harder to trust as soon as it becomes harder to inspect.

The local-first posture keeps the base layer simple:

- JSONL for append-only capture
- SQLite for local search and timeline inspection
- exportable artifacts you can diff, back up, and reason about

## Who it is for

- **OpenClaw operators** who want smaller, more inspectable memory packs
- **Agent builders** who want a practical memory layer without jumping straight to a hosted stack
- **Teams with decisions, notes, and specs to remember** who care about evidence and rollback, not just retrieval scores

## What it is not

- not a hosted SaaS memory product
- not a requirement to capture everything forever
- not a promise that embeddings alone solve retrieval quality
- not a requirement to replace OpenClaw native memory on day one

## Recommended way to adopt it

1. **Start local** — prove the recall loop on a sample or your own JSONL.
2. **Add the sidecar** — wire capture + harvest into your existing OpenClaw install.
3. **Promote the engine only if needed** — switch slot ownership when hybrid recall and policy controls justify it.

## Read next

- [Choose an install path](install-modes.md)
- [Proactive Pack](proactive-pack.md)
- [v2 blueprint](context-supply-chain-blueprint.md)
- [Quickstart](quickstart.md)
- [Reality check & status](reality-check.md)
- [Deployment guide](deployment.md)
- [Governed optimize assist lane](optimize-assist.md)
- [Ecosystem fit](ecosystem-fit.md)
- [Mem Engine reference](mem-engine.md)
